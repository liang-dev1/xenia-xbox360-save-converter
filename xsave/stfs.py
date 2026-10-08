"""Bounded STFS Saved Game reader and fresh donor-header writer.

The 256 MiB package cap avoids unbounded allocation on hostile inputs. Payloads
remain opaque; this module makes no assertion about a game's own checksums.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
from math import ceil

from .errors import FormatError

BLOCK = 0x1000
MAX_PACKAGE = 256 * 1024 * 1024
END = 0xFFFFFF
L0 = 0xAA
L1 = 0x70E4
L2 = 0x4AF768


def _u24(raw: bytes) -> int:
    return int.from_bytes(raw, "little")


def _put24(value: int) -> bytes:
    if not 0 <= value <= END:
        raise FormatError("STFS block number exceeds 24 bits")
    return value.to_bytes(3, "little")


def _sha(raw: bytes) -> bytes:
    return sha1(raw).digest()


def _path(path: str) -> tuple[str, ...]:
    if not isinstance(path, str) or not path or "\\" in path:
        raise FormatError("unsafe STFS path")
    parts = tuple(path.split("/"))
    if len(parts) > 256 or any(p in ("", ".", "..") or len(p.encode("ascii", "ignore")) != len(p)
           or len(p) > 40 or any(ord(c) < 32 or c in '<>=?:;"*+,/\\|' for c in p)
           for p in parts):
        raise FormatError("unsafe STFS path")
    return parts


@dataclass(frozen=True)
class Metadata:
    title_id: int
    content_type: int
    profile_id: bytes
    device_id: bytes
    console_id: bytes
    display_name: str


class StfsPackage:
    def __init__(self, data: bytes):
        if not isinstance(data, bytes) or len(data) < 0x4000 or len(data) > MAX_PACKAGE:
            raise FormatError("invalid STFS package size")
        self.data = data
        if data[:4] not in (b"CON ", b"LIVE", b"PIRS"):
            raise FormatError("unknown STFS magic")
        self.magic = data[:4]
        header_size = int.from_bytes(data[0x340:0x344], "big")
        if header_size < 0x971A:
            raise FormatError("STFS metadata extends beyond declared header")
        self.base = (header_size + BLOCK - 1) // BLOCK * BLOCK
        if not 0xA000 <= self.base <= len(data) - BLOCK:
            raise FormatError("invalid STFS header size")
        desc = data[0x379:0x39D]
        if len(desc) != 0x24 or desc[0] != 0x24 or desc[1] not in (0, 1, 2):
            raise FormatError("unsupported STFS descriptor")
        if int.from_bytes(data[0x3A9:0x3AD], "big") != 0:
            raise FormatError("SVOD is unsupported")
        self.flags = desc[2]
        self.copies = 1 if self.flags & 1 else 2
        self.count = int.from_bytes(desc[0x1C:0x20], "big")
        self.dir_blocks = int.from_bytes(desc[3:5], "little")
        self.dir_start = _u24(desc[5:8])
        if not 1 <= self.count < L2 or not 1 <= self.dir_blocks <= self.count:
            raise FormatError("invalid STFS allocation count")
        if self.data_offset(self.count - 1) + BLOCK > len(data):
            raise FormatError("truncated STFS block area")
        self.metadata = Metadata(
            title_id=int.from_bytes(data[0x360:0x364], "big"),
            content_type=int.from_bytes(data[0x344:0x348], "big"),
            profile_id=data[0x371:0x379],
            device_id=data[0x3FD:0x411],
            console_id=data[0x36C:0x371],
            display_name=self._display_name(),
        )
        self.metadata_version = int.from_bytes(data[0x348:0x34C], "big")
        if self.metadata_version not in (1, 2):
            raise FormatError("unsupported STFS metadata version")
        self.thumbnail_capacity = 0x3D00 if self.metadata_version >= 2 else 0x4000
        size = int.from_bytes(data[0x1712:0x1716], "big")
        if size > self.thumbnail_capacity:
            raise FormatError("invalid thumbnail length")
        self.thumbnail = data[0x171A:0x171A + size]
        self._hash_cache: dict[tuple[int, int], bytes] = {}
        self._verify_hashes()
        self.files, self.directories = self._read_tree()

    def _display_name(self) -> str:
        slots = [0x411 + i * 0x100 for i in range(9)]
        if int.from_bytes(self.data[0x348:0x34C], "big") >= 2:
            slots += [0x541A + i * 0x100 for i in range(3)]
        for offset in slots:
            raw = self.data[offset:offset + 0x100]
            if len(raw) == 0x100 and raw.strip(b"\0"):
                return raw.decode("utf-16-be", "replace").split("\0", 1)[0]
        return ""

    def _backing(self, n: int) -> int:
        block = n
        for base in (L0, L0 * L0, L0 * L0 * L0):
            block += self.copies * ((n + base) // base)
            if n < base:
                break
        return block

    def data_offset(self, n: int) -> int:
        return self.base + self._backing(n) * BLOCK

    def _table_backing(self, n: int, level: int) -> int:
        s0, s1 = (0xAB, 0x718F) if self.copies == 1 else (0xAC, 0x723A)
        if level == 2:
            return s1
        if level == 1:
            q = n // L1
            return s0 if q == 0 else q * s1 + self.copies
        q = n // L0
        if q == 0:
            return 0
        result = q * s0 + (n // L1 + 1) * self.copies
        return result if n // L1 == 0 else result + self.copies

    def _table(self, n: int, level: int, secondary: bool, expected: bytes) -> bytes:
        backing = self._table_backing(n, level) + (int(secondary) if self.copies == 2 else 0)
        key = (backing, level)
        if key not in self._hash_cache:
            offset = self.base + backing * BLOCK
            table = self.data[offset:offset + BLOCK]
            if len(table) != BLOCK or _sha(table) != expected:
                raise FormatError(f"STFS level {level} hash mismatch at block {n}")
            self._hash_cache[key] = table
        return self._hash_cache[key]

    def _entry(self, table: bytes, index: int) -> bytes:
        offset = (index % L0) * 0x18
        return table[offset:offset + 0x18]

    def _hash_entry(self, n: int) -> bytes:
        if not 0 <= n < self.count:
            raise FormatError("STFS block outside allocation")
        expected = self.data[0x381:0x395]
        secondary = bool(self.flags & 2)
        if self.count > L1:
            entry = self._entry(self._table(n, 2, secondary, expected), n // L1)
            expected, secondary = entry[:20], bool(entry[20] & 0x40)
        if self.count > L0:
            entry = self._entry(self._table(n, 1, secondary, expected), n // L0)
            expected, secondary = entry[:20], bool(entry[20] & 0x40)
        return self._entry(self._table(n, 0, secondary, expected), n)

    def _verify_hashes(self) -> None:
        if _sha(self.data[0x344:self.base]) != self.data[0x32C:0x340]:
            raise FormatError("STFS content ID mismatch")
        for n in range(self.count):
            entry = self._hash_entry(n)
            if entry[20] & 0x80:
                offset = self.data_offset(n)
                if _sha(self.data[offset:offset + BLOCK]) != entry[:20]:
                    raise FormatError(f"STFS data hash mismatch at block {n}")

    def _chain(self, first: int, count: int, contiguous: bool = False) -> list[int]:
        if count == 0:
            if first not in (0, END):
                raise FormatError("empty file references a block")
            return []
        blocks, seen = [], set()
        n = first
        for _ in range(count):
            if n in seen or not 0 <= n < self.count:
                raise FormatError("invalid or cyclic STFS block chain")
            seen.add(n)
            blocks.append(n)
            entry = self._hash_entry(n)
            if not entry[20] & 0x80:
                raise FormatError("STFS chain references unallocated block")
            n = n + 1 if contiguous else int.from_bytes(entry[21:24], "big")
        if not contiguous and n != END:
            raise FormatError("STFS block chain longer than advertised")
        return blocks

    def _read_tree(self) -> tuple[dict[str, bytes], set[str]]:
        dir_bytes = b"".join(self.data[self.data_offset(n):self.data_offset(n) + BLOCK]
                             for n in self._chain(self.dir_start, self.dir_blocks))
        entries: list[tuple[str, bytes] | None] = []
        for off in range(0, len(dir_bytes), 0x40):
            row = dir_bytes[off:off + 0x40]
            if not row[0x28]:
                entries.append(None)
                continue
            length = row[0x28] & 0x3F
            if not 1 <= length <= 40:
                raise FormatError("invalid STFS filename length")
            try:
                name = row[:length].decode("ascii")
            except UnicodeDecodeError as exc:
                raise FormatError("non-ASCII STFS filename") from exc
            _path(name)
            entries.append((name, row))
        if len(entries) > 0xFFFE:
            raise FormatError("too many STFS entries")
        paths: dict[int, str] = {}

        def resolve(i: int, stack: frozenset[int] = frozenset()) -> str:
            if i in paths:
                return paths[i]
            if len(stack) >= 256 or i in stack or i >= len(entries) or entries[i] is None:
                raise FormatError("invalid STFS directory parent")
            name, row = entries[i]
            parent = int.from_bytes(row[0x32:0x34], "big")
            if parent == 0xFFFF:
                path = name
            else:
                if parent >= len(entries) or entries[parent] is None or not entries[parent][1][0x28] & 0x80:
                    raise FormatError("STFS parent is not a directory")
                path = resolve(parent, stack | {i}) + "/" + name
            _path(path)
            paths[i] = path
            return path

        files: dict[str, bytes] = {}
        dirs: set[str] = set()
        used_blocks = set(self._chain(self.dir_start, self.dir_blocks))
        for i, item in enumerate(entries):
            if item is None:
                continue
            _, row = item
            path = resolve(i)
            if path in files or path in dirs:
                raise FormatError("duplicate STFS path")
            if row[0x28] & 0x80:
                dirs.add(path)
                continue
            size = int.from_bytes(row[0x34:0x38], "big")
            blocks = _u24(row[0x29:0x2C])
            allocated = _u24(row[0x2C:0x2F])
            if blocks != ceil(size / BLOCK) or not blocks <= allocated <= self.count:
                raise FormatError("STFS file size/block count disagree")
            chain = self._chain(_u24(row[0x2F:0x32]), blocks, bool(row[0x28] & 0x40))
            if used_blocks.intersection(chain):
                raise FormatError("STFS files share an allocation block")
            used_blocks.update(chain)
            files[path] = b"".join(self.data[self.data_offset(n):self.data_offset(n) + BLOCK]
                                   for n in chain)[:size]
        if len({path.casefold() for path in files.keys() | dirs}) != len(files) + len(dirs):
            raise FormatError("case-insensitive STFS path collision")
        return files, dirs

    def validate(self) -> dict:
        from .signing import verify_con_signature

        signature = verify_con_signature(self.data)
        warnings = ["certificate issuer trust, game payload, and retail console acceptance are unverified"]
        if signature in ('missing', 'invalid', 'unavailable'):
            warnings.append(f'CON content signature: {signature}')
        return {"structural_valid": True, "hash_tree": "valid", "content_id": "valid",
                "signature": signature, "files": len(self.files), "warnings": warnings}


def build(files: dict[str, bytes], template: bytes, directories=(), *,
          profile_id: bytes | None = None, device_id: bytes | None = None,
          display_name: str | None = None, thumbnail: bytes | None = None,
          signer=None) -> bytes:
    donor = StfsPackage(template)
    if donor.magic != b"CON " or donor.metadata.content_type != 1:
        raise FormatError("same-title CON Saved Game donor required")
    files = dict(files)
    dirs = set(directories)
    for path, payload in files.items():
        _path(path)
        if not isinstance(payload, bytes):
            raise FormatError("STFS file payload must be bytes")
        for j in range(1, len(path.split("/"))):
            dirs.add("/".join(path.split("/")[:j]))
    for path in list(dirs):
        _path(path)
        parts = path.split('/')
        dirs.update('/'.join(parts[:j]) for j in range(1, len(parts)))
    if set(files) & dirs:
        raise FormatError("file/directory path collision")
    all_paths = set(files) | dirs
    if len({path.casefold() for path in all_paths}) != len(all_paths):
        raise FormatError("case-insensitive STFS path collision")
    paths = sorted(dirs, key=lambda p: (p.count("/"), p)) + sorted(files)
    if len(paths) > 0xFFFE:
        raise FormatError("too many STFS entries")
    index = {path: i for i, path in enumerate(paths)}
    dir_count = max(1, ceil(len(paths) / 64))
    block_map: dict[str, list[int]] = {}
    next_block = dir_count
    for path in paths:
        if path not in files:
            continue
        length = ceil(len(files[path]) / BLOCK)
        block_map[path] = list(range(next_block, next_block + length))
        next_block += length
    if next_block >= L2:
        raise FormatError("STFS writer exceeds supported L2 allocation")
    if donor.base + (donor._backing(next_block - 1) + 1) * BLOCK > MAX_PACKAGE:
        raise FormatError("STFS package exceeds 256 MiB limit")
    header = bytearray(template[:donor.base])
    if profile_id is not None:
        if len(profile_id) != 8:
            raise FormatError("Profile ID must be 8 bytes")
        header[0x371:0x379] = profile_id
    if device_id is not None:
        if len(device_id) != 0x14:
            raise FormatError("Device ID must be 20 bytes")
        header[0x3FD:0x411] = device_id
    if display_name is not None:
        encoded = display_name.encode("utf-16-be")
        if len(encoded) > 0xFE:
            raise FormatError("display name exceeds 127 UTF-16 code units")
        for off in [0x411 + i * 0x100 for i in range(9)] + (
                [0x541A + i * 0x100 for i in range(3)] if int.from_bytes(header[0x348:0x34C], "big") >= 2 else []):
            header[off:off + 0x100] = encoded.ljust(0x100, b"\0")
    if thumbnail is not None:
        if len(thumbnail) > donor.thumbnail_capacity:
            raise FormatError("thumbnail exceeds STFS capacity")
        header[0x1712:0x1716] = len(thumbnail).to_bytes(4, "big")
        header[0x171A:0x171A + donor.thumbnail_capacity] = thumbnail.ljust(donor.thumbnail_capacity, b"\0")
    header[0x37B] &= ~2
    header[0x37C:0x37E] = dir_count.to_bytes(2, "little")
    header[0x37E:0x381] = _put24(0)
    header[0x395:0x399] = next_block.to_bytes(4, "big")
    header[0x399:0x39D] = (0).to_bytes(4, "big")
    # ContentSize/DataFiles/DataFilesSize describe donor XContent metadata, not
    # necessarily this file tree: native Saved Games may set all three to zero.
    count = next_block
    last_backing = donor._backing(count - 1)
    out = bytearray(header + bytes((last_backing + 1) * BLOCK))
    directory = bytearray(dir_count * BLOCK)
    for i, path in enumerate(paths):
        name = path.rsplit("/", 1)[-1].encode("ascii")
        off = i * 0x40
        directory[off:off + len(name)] = name
        is_dir = path in dirs
        directory[off + 0x28] = len(name) | (0x80 if is_dir else 0)
        blocks = [] if is_dir else block_map[path]
        directory[off + 0x29:off + 0x2C] = _put24(len(blocks))
        directory[off + 0x2C:off + 0x2F] = _put24(len(blocks))
        directory[off + 0x2F:off + 0x32] = _put24(blocks[0] if blocks else END)
        parent = path.rpartition("/")[0]
        directory[off + 0x32:off + 0x34] = (index[parent] if parent else 0xFFFF).to_bytes(2, "big")
        directory[off + 0x34:off + 0x38] = (0 if is_dir else len(files[path])).to_bytes(4, "big")
    data_blocks: dict[int, bytes] = {i: directory[i * BLOCK:(i + 1) * BLOCK]
                                      for i in range(dir_count)}
    chains = {i: (i + 1 if i + 1 < dir_count else END) for i in range(dir_count)}
    for path, blocks in block_map.items():
        payload = files[path]
        for i, n in enumerate(blocks):
            data_blocks[n] = payload[i * BLOCK:(i + 1) * BLOCK].ljust(BLOCK, b"\0")
            chains[n] = blocks[i + 1] if i + 1 < len(blocks) else END
    for n, payload in data_blocks.items():
        offset = donor.base + donor._backing(n) * BLOCK
        out[offset:offset + BLOCK] = payload
    # Hash upward from data to L0, L1, L2. Both writable copies are identical;
    # active selectors are zero and future writers may switch copies atomically.
    level_hashes: list[list[bytes]] = []
    leaves = [_sha(data_blocks[n]) for n in range(count)]
    for level in range(3):
        if level > 0 and len(leaves) <= 1:
            break
        tables = []
        for group in range(ceil(len(leaves) / L0)):
            table = bytearray(BLOCK)
            for slot, digest in enumerate(leaves[group * L0:(group + 1) * L0]):
                off = slot * 0x18
                table[off:off + 20] = digest
                table[off + 20] = 0x80 if level == 0 else 0
                table[off + 21:off + 24] = (chains[group * L0 + slot] if level == 0 else END).to_bytes(3, "big")
            if level == 1:
                table[0xFF0:0xFF4] = min(L1, count - group * L1).to_bytes(4, "big")
            elif level == 2:
                table[0xFF0:0xFF4] = count.to_bytes(4, "big")
            tables.append(bytes(table))
            sample = group * (L0 if level == 0 else L1 if level == 1 else L2)
            offset = donor.base + donor._table_backing(sample, level) * BLOCK
            for copy in range(donor.copies):
                out[offset + copy * BLOCK:offset + (copy + 1) * BLOCK] = table
        level_hashes.append(tables)
        leaves = [_sha(table) for table in tables]
        if len(leaves) == 1:
            break
    out[0x381:0x395] = leaves[0]
    out[0x32C:0x340] = _sha(out[0x344:donor.base])
    out[0x1AC:0x22C] = bytes(0x80)
    if signer is not None:
        signer.sign(out)
    result = bytes(out)
    StfsPackage(result)
    if signer is not None:
        from .signing import verify_con_signature

        if verify_con_signature(result) != "valid":
            raise FormatError("CON signer did not produce a valid content signature")
    return result
