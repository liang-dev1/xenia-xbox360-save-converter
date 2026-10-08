"""Xenia extracted save discovery; sidecar identity is evidence, not ownership."""
from dataclasses import dataclass, field
from pathlib import Path
import re
import stat
import zipfile

from .errors import FormatError
from .paths import MAX_BYTES, is_link, read_file, read_tree, safe_component, safe_path

LEGACY_HEADER_SIZES = (0x134, 0x138, 0x148, 0x14C)
FULL_METADATA_END = 0x971A
FULL_FILENAME_END = 0x9744
FULL_HEADER_SIZE = 0xA000
PNG_MAGIC = b'\x89PNG\r\n\x1a\n'


def integer(blob: bytes, offset: int, size: int = 4) -> int:
    return int.from_bytes(blob[offset:offset + size], 'big')


@dataclass
class XeniaHeader:
    device_id: int
    content_type: int
    display_name: str
    package_name: str
    title_id: int | None = None
    aggregate_value: int = 0
    license_mask: int = 0
    kind: str = 'aggregate'
    raw: bytes = b''
    profile_id: bytes | None = None
    console_id: bytes | None = None
    full_device_id: bytes | None = None
    metadata_version: int = 0
    thumbnail: bytes | None = None

    @classmethod
    def parse(cls, blob: bytes, *, title_hint: int | None = None,
              package_name_hint: str | None = None):
        if FULL_METADATA_END <= len(blob) <= FULL_HEADER_SIZE:
            return cls._parse_full(blob, package_name_hint=package_name_hint)
        if len(blob) not in LEGACY_HEADER_SIZES:
            raise FormatError('Unsupported XCONTENT sidecar size')
        try:
            display = blob[8:0x108].decode('utf-16-be').split('\0', 1)[0]
            name = blob[0x108:0x132].split(b'\0', 1)[0].decode('ascii')
        except UnicodeError as exc:
            raise FormatError('Invalid XCONTENT name encoding') from exc
        safe_component(name, 42)
        title, aggregate, license_mask, kind = None, 0, 0, 'basic'
        if len(blob) == 0x138:
            title, kind = integer(blob, 0x134), 'manager_cross_title'
        elif len(blob) >= 0x148:
            aggregate = integer(blob, 0x134, 8)
            title, kind = integer(blob, 0x13c), 'aggregate'
            alternate = integer(blob, 0x140)
            # Old internal-prefix sidecars coexist with packed aggregate headers.
            # Do not reinterpret arbitrary padding as a trusted XUID.
            if title in (0, 0xffffffff) and alternate not in (0, 0xffffffff):
                title, kind = alternate, 'legacy_internal_prefix'
            elif title_hint is not None and alternate == title_hint and title != title_hint:
                title, kind = alternate, 'legacy_internal_prefix'
            elif title in (0, 0xffffffff) and alternate == 0xffffffff:
                title, kind = None, 'legacy_ambiguous'
            if len(blob) == 0x14c:
                license_mask = integer(blob, 0x148)
        if title in (0, 0xffffffff):
            title = None
        return cls(integer(blob, 0), integer(blob, 4), display, name, title,
                   aggregate, license_mask, kind, bytes(blob))

    @classmethod
    def _parse_full(cls, blob: bytes, *, package_name_hint: str | None):
        if blob[:4] not in (b'CON ', b'LIVE', b'PIRS'):
            raise FormatError('Invalid full XContent sidecar magic')
        version = integer(blob, 0x348)
        if version not in (1, 2):
            raise FormatError('Unsupported full XContent metadata version')
        capacity = 0x3D00 if version >= 2 else 0x4000
        thumbnail_size = integer(blob, 0x1712)
        if thumbnail_size > capacity:
            raise FormatError('Invalid full XContent thumbnail size')
        try:
            display = blob[0x411:0x511].decode('utf-16-be').split('\0', 1)[0]
        except UnicodeError as exc:
            raise FormatError('Invalid full XContent display name') from exc
        raw_name = blob[FULL_METADATA_END:FULL_FILENAME_END] if len(blob) >= FULL_FILENAME_END else b''
        try:
            name = raw_name.split(b'\0', 1)[0].decode('ascii')
        except UnicodeError as exc:
            raise FormatError('Invalid full XContent package name') from exc
        if not name:
            name = package_name_hint or ''
        safe_component(name, 42)
        profile = bytes(blob[0x371:0x379])
        return cls(1, integer(blob, 0x344), display, name,
                   integer(blob, 0x360), 0, 0, 'canary_full', bytes(blob),
                   profile if any(profile) else None, bytes(blob[0x36C:0x371]),
                   bytes(blob[0x3FD:0x411]), version,
                   bytes(blob[0x171A:0x171A + thumbnail_size]))

    @classmethod
    def from_container(cls, data: bytes, package_name: str):
        """Copies XContent metadata into a non-STFS Canary sidecar.

        The signature, content ID and STFS data are deliberately omitted: a
        `.header` is metadata only and must never masquerade as a container.
        """
        if len(data) < FULL_METADATA_END:
            raise FormatError('Container header is too short for XContent metadata')
        sidecar = bytearray(FULL_HEADER_SIZE)
        sidecar[:4] = b'CON '
        sidecar[0x340:0x344] = FULL_METADATA_END.to_bytes(4, 'big')
        sidecar[0x22C:0x32C] = data[0x22C:0x32C]
        sidecar[0x344:FULL_METADATA_END] = data[0x344:FULL_METADATA_END]
        sidecar[FULL_METADATA_END:FULL_FILENAME_END] = safe_component(package_name, 42).encode('ascii').ljust(42, b'\0')
        return cls.parse(bytes(sidecar), package_name_hint=package_name)

    def to_bytes(self, *, size: int = 0x14c) -> bytes:
        if size not in LEGACY_HEADER_SIZES:
            raise FormatError('Unsupported XCONTENT header size')
        safe_component(self.package_name, 42)
        name = self.package_name.encode('ascii')
        display = self.display_name.encode('utf-16-be')
        if len(display) > 254:
            raise FormatError('Display name exceeds 127 UTF-16 code units')
        data = bytearray(self.raw if len(self.raw) == size else bytes(size))
        data[0:4] = self.device_id.to_bytes(4, 'big')
        data[4:8] = self.content_type.to_bytes(4, 'big')
        data[8:0x108] = display.ljust(256, b'\0')
        data[0x108:0x132] = name.ljust(42, b'\0')
        if size == 0x138:
            data[0x134:0x138] = (self.title_id if self.title_id is not None else 0xffffffff).to_bytes(4, 'big')
        elif size >= 0x148:
            if self.kind != 'legacy_internal_prefix':
                data[0x134:0x13c] = self.aggregate_value.to_bytes(8, 'big')
                if self.kind != 'legacy_ambiguous':
                    data[0x13c:0x140] = (self.title_id if self.title_id is not None else 0xffffffff).to_bytes(4, 'big')
            else:
                data[0x140:0x144] = (self.title_id if self.title_id is not None else 0xffffffff).to_bytes(4, 'big')
            if size == 0x14c:
                data[0x148:0x14c] = self.license_mask.to_bytes(4, 'big')
        return bytes(data)

    def to_full_bytes(self) -> bytes:
        """Returns Canary's current 0xA000 metadata-only directory sidecar."""
        safe_component(self.package_name, 42)
        display = self.display_name.encode('utf-16-be')
        if len(display) > 254:
            raise FormatError('Display name exceeds 127 UTF-16 code units')
        data = bytearray(self.raw if len(self.raw) == FULL_HEADER_SIZE else bytes(FULL_HEADER_SIZE))
        data[:4] = b'CON '
        # A sidecar has XContent metadata, but no STFS data/hash tree/signature.
        data[4:0x22C] = b'\0' * (0x22C - 4)
        data[0x32C:0x340] = b'\0' * 20
        data[0x340:0x344] = FULL_METADATA_END.to_bytes(4, 'big')
        data[0x344:0x348] = self.content_type.to_bytes(4, 'big')
        version = self.metadata_version if self.metadata_version in (1, 2) else 2
        data[0x348:0x34C] = version.to_bytes(4, 'big')
        data[0x360:0x364] = (self.title_id if self.title_id is not None else 0xffffffff).to_bytes(4, 'big')
        profile = self.profile_id if self.profile_id is not None else b'\0' * 8
        if len(profile) != 8:
            raise FormatError('Full XContent profile ID must be 8 bytes')
        data[0x371:0x379] = profile
        if self.console_id is not None:
            if len(self.console_id) != 5:
                raise FormatError('Full XContent console ID must be 5 bytes')
            data[0x36C:0x371] = self.console_id
        if self.full_device_id is not None:
            if len(self.full_device_id) != 0x14:
                raise FormatError('Full XContent device ID must be 20 bytes')
            data[0x3FD:0x411] = self.full_device_id
        data[0x411:0x511] = display.ljust(0x100, b'\0')
        capacity = 0x3D00 if version >= 2 else 0x4000
        thumbnail = self.thumbnail or b''
        if len(thumbnail) > capacity:
            raise FormatError('Full XContent thumbnail exceeds metadata capacity')
        data[0x1712:0x1716] = len(thumbnail).to_bytes(4, 'big')
        data[0x171A:0x171A + capacity] = thumbnail.ljust(capacity, b'\0')
        data[FULL_METADATA_END:FULL_FILENAME_END] = self.package_name.encode('ascii').ljust(42, b'\0')
        return bytes(data)


@dataclass
class XeniaSave:
    title_id: int
    content_type: int
    xuid: int | None
    package_name: str
    display_name: str
    files: dict[str, bytes]
    directories: set[str]
    thumbnail: bytes | None = None
    header: XeniaHeader | None = None
    warnings: list[str] = field(default_factory=list)
    input_paths: tuple[Path, ...] = ()
    container_validation: dict | None = None


def _zip_tree(path: Path):
    files, directories, seen, total = {}, set(), set(), 0
    try:
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                name = info.filename.rstrip('/')
                safe_path(name)
                if name.casefold() in seen:
                    raise FormatError('Duplicate/colliding ZIP member')
                seen.add(name.casefold())
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise FormatError('ZIP symbolic links are not supported')
                if info.flag_bits & 1:
                    raise FormatError('Encrypted ZIP is not supported')
                total += info.file_size
                if total > MAX_BYTES or len(seen) > 100000:
                    raise FormatError('ZIP exceeds resource limits')
                if info.is_dir():
                    directories.add(name)
                else:
                    files[name] = archive.read(info)
                for parent in Path(name).parents:
                    if parent.as_posix() != '.':
                        directories.add(parent.as_posix())
    except (zipfile.BadZipFile, RuntimeError) as exc:
        raise FormatError('Invalid/unsupported ZIP input') from exc
    folded_directories = {name.casefold() for name in directories}
    if len(folded_directories) != len(directories) or folded_directories & {name.casefold() for name in files}:
        raise FormatError('ZIP file/directory or case-insensitive parent collision')
    return files, directories


def _normalise_directories(directories: set[str], files: dict[str, bytes]) -> set[str]:
    """Represent parent directories explicitly so round-trip comparisons agree."""
    result = set(directories)
    for path in result | set(files):
        for parent in Path(path).parents:
            if parent.as_posix() != '.':
                result.add(parent.as_posix())
    return result


def _source_xuid(observed, supplied):
    if observed is not None and supplied is not None and observed != supplied:
        raise FormatError('Explicit source XUID conflicts with observed identity')
    return observed if observed is not None else supplied


def _from_container(data, name, *, xuid=None, path_xuid=None, inputs=()):
    from .stfs import StfsPackage
    package = StfsPackage(data)
    if package.metadata.content_type != 1:
        raise FormatError('Only Saved Game content type 00000001 is supported')
    header = XeniaHeader.from_container(data, name)
    header.kind = 'container_header'
    profile_xuid = int.from_bytes(package.metadata.profile_id, 'big')
    observed_xuid = profile_xuid if path_xuid is None else path_xuid
    result = XeniaSave(package.metadata.title_id, 1,
                       _source_xuid(observed_xuid, xuid),
                       safe_component(name, 42), package.metadata.display_name,
                       package.files, _normalise_directories(package.directories, package.files), package.thumbnail,
                       header=header, input_paths=inputs, container_validation=package.validate())
    result.warnings.append('container_input_requires_integrity_validation')
    if path_xuid is not None and path_xuid != profile_xuid:
        result.warnings.append('container_profile_id_differs_from_path_xuid')
    return result


def discover(path: Path, *, title_id: int | None = None,
             xuid: int | None = None) -> list[XeniaSave]:
    path = Path(path).absolute()
    if any(is_link(p) for p in (path, *path.parents)):
        raise FormatError('Link inputs are not supported')
    inputs = (path,)
    selected = None
    if path.is_file():
        if path.stat().st_size > MAX_BYTES:
            raise FormatError('Input exceeds 256 MiB limit')
        with path.open('rb') as stream:
            magic = stream.read(4)
        if magic in (b'CON ', b'LIVE', b'PIRS'):
            result = _from_container(read_file(path), path.name, xuid=xuid, inputs=inputs)
            if title_id is not None and title_id != result.title_id:
                raise FormatError('Explicit Title ID conflicts with package metadata')
            return [result]
        if magic[:2] != b'PK':
            raise FormatError('Raw payload file needs an extracted package folder and explicit Title ID')
        files, directories = _zip_tree(path)
    elif path.is_dir():
        # A selected package directory is a request to inspect only that package,
        # never neighbours under the same title/profile content root.
        if path.parent.name.upper() == '00000001' and re.fullmatch(r'[0-9a-fA-F]{8}', path.parent.parent.name):
            observed_title = int(path.parent.parent.name, 16)
            if title_id is not None and observed_title != title_id:
                raise FormatError('Title path conflicts with explicit Title ID')
            observed_xuid = None
            if re.fullmatch(r'[0-9a-fA-F]{16}', path.parent.parent.parent.name):
                observed_xuid = int(path.parent.parent.parent.name, 16)
            header_path = path.parent.parent / 'Headers' / '00000001' / (path.name + '.header')
            if header_path.is_file():
                inputs += (header_path,)
            header = (XeniaHeader.parse(read_file(header_path, FULL_HEADER_SIZE), title_hint=observed_title,
                                        package_name_hint=path.name)
                      if header_path.is_file() else None)
            if header and header.content_type != 1:
                raise FormatError('XCONTENT content type conflicts with package path')
            if header and header.package_name != path.name:
                raise FormatError('XCONTENT filename conflicts with package path')
            if header and header.title_id not in (None, observed_title):
                raise FormatError('XCONTENT Title ID conflicts with package path')
            selected_xuid = observed_xuid
            warnings = []
            if header and header.profile_id is not None:
                profile_xuid = int.from_bytes(header.profile_id, 'big')
                if selected_xuid is None:
                    selected_xuid = profile_xuid
                    warnings.append('full_header_profile_id_used_as_xuid_evidence')
                elif profile_xuid != selected_xuid:
                    warnings.append('full_header_profile_id_differs_from_path_xuid')
            selected_xuid = _source_xuid(selected_xuid, xuid)
            game, dirs = read_tree(path)
            loose_thumbnail = game.pop('__thumbnail.png', None)
            if loose_thumbnail is not None and not loose_thumbnail.startswith(PNG_MAGIC):
                raise FormatError('Ambiguous non-PNG __thumbnail.png; refuse to drop potential game data')
            thumbnail = loose_thumbnail if loose_thumbnail is not None else (header.thumbnail if header else None)
            if loose_thumbnail is not None and header and header.thumbnail and loose_thumbnail != header.thumbnail:
                warnings.append('loose_thumbnail_overrides_full_header_thumbnail')
            return [XeniaSave(observed_title, 1, selected_xuid, safe_component(path.name, 42),
                              header.display_name if header else path.name, game,
                              _normalise_directories(dirs, game),
                              thumbnail, header, warnings, inputs)]
        root = path
        files, directories = read_tree(root)
        # Prefix the explicitly selected title-root / package-root path as needed.
        if re.fullmatch(r'[0-9a-fA-F]{8}', root.name) and any(n.startswith('00000001/') for n in files):
            prefix = root.name + '/'
            files = {prefix + n: b for n, b in files.items()}
            directories = {prefix + n for n in directories}
    else:
        raise FormatError('Input path does not exist')
    found = []
    # Discover by structural path positions and corroborate with XCONTENT fields.
    candidates = set()
    for name in set(files) | directories:
        parts = name.split('/')
        for i, part in enumerate(parts):
            if part.upper() == '00000001' and i and re.fullmatch(r'[0-9a-fA-F]{8}', parts[i - 1]) and i + 1 < len(parts):
                candidates.add(('/'.join(parts[:i + 2]), i))
    package_prefixes = set()
    for prefix, i in sorted(candidates, key=lambda item: (item[0].count('/'), item[0])):
        if any(parent.as_posix() in package_prefixes for parent in Path(prefix).parents):
            continue
        parts = prefix.split('/')
        package_name = parts[-1]
        if selected is not None and package_name != selected:
            continue
        if parts[i - 1] == 'Headers':
            continue
        observed_title = int(parts[i - 1], 16)
        if title_id is not None and observed_title != title_id:
            raise FormatError('Title path conflicts with explicit Title ID')
        observed_xuid = None
        if i >= 2 and re.fullmatch(r'[0-9a-fA-F]{16}', parts[i - 2]):
            observed_xuid = int(parts[i - 2], 16)
        selected_xuid = observed_xuid
        if prefix in files and files[prefix][:4] in (b'CON ', b'LIVE', b'PIRS'):
            save = _from_container(files[prefix], package_name, xuid=xuid, path_xuid=observed_xuid, inputs=inputs)
            if save.title_id != observed_title:
                raise FormatError('STFS Title ID conflicts with content path')
            found.append(save)
            package_prefixes.add(prefix)
            continue
        head_path = '/'.join(parts[:i]) + '/Headers/00000001/' + package_name + '.header'
        header = (XeniaHeader.parse(files[head_path], title_hint=observed_title,
                                    package_name_hint=package_name)
                  if head_path in files else None)
        warnings = []
        if header:
            if header.package_name != package_name or header.content_type != 1:
                raise FormatError('XCONTENT filename/content type conflicts with package path')
            if header.title_id is not None and header.title_id != observed_title:
                raise FormatError('XCONTENT Title ID conflicts with package path')
            if header.kind in ('manager_cross_title', 'legacy_internal_prefix', 'legacy_ambiguous'):
                warnings.append('legacy_header_normalized_on_export')
            if header.title_id is None:
                warnings.append('header_title_resolved_from_path')
            if header.aggregate_value and observed_xuid is not None and header.aggregate_value != observed_xuid:
                warnings.append('header_aggregate_value_differs_from_path_xuid')
            if header.profile_id is not None:
                profile_xuid = int.from_bytes(header.profile_id, 'big')
                if selected_xuid is None:
                    selected_xuid = profile_xuid
                    warnings.append('full_header_profile_id_used_as_xuid_evidence')
                elif profile_xuid != selected_xuid:
                    warnings.append('full_header_profile_id_differs_from_path_xuid')
        else:
            warnings.append('xcontent_header_missing')
        selected_xuid = _source_xuid(selected_xuid, xuid)
        game = {name[len(prefix) + 1:]: value for name, value in files.items() if name.startswith(prefix + '/')}
        dirs = {name[len(prefix) + 1:] for name in directories if name.startswith(prefix + '/')}
        thumb = game.pop('__thumbnail.png', None)
        if thumb is not None and not thumb.startswith(PNG_MAGIC):
            raise FormatError('Ambiguous non-PNG __thumbnail.png; refuse to drop potential game data')
        if thumb is None and header is not None:
            thumb = header.thumbnail
        elif thumb is not None and header is not None and header.thumbnail and thumb != header.thumbnail:
            warnings.append('loose_thumbnail_overrides_full_header_thumbnail')
        if not game and prefix not in directories:
            continue  # Orphan header / non-package file: no payload to manufacture.
        found.append(XeniaSave(observed_title, 1, selected_xuid, safe_component(package_name, 42),
                               header.display_name if header else package_name, game,
                               _normalise_directories(dirs, game),
                               thumb, header, warnings, inputs))
        package_prefixes.add(prefix)
    if not found and path.is_dir() and title_id is not None:
        files, dirs = read_tree(path)
        if not files:
            raise FormatError('No game files in explicit extracted folder')
        thumb = files.pop('__thumbnail.png', None)
        if thumb is not None and not thumb.startswith(PNG_MAGIC):
            raise FormatError('Invalid Xenia thumbnail')
        found.append(XeniaSave(title_id, 1, xuid, safe_component(path.name, 42), path.name,
                               files, _normalise_directories(dirs, files), thumb,
                               warnings=['metadata_supplied_explicitly'], input_paths=inputs))
    if not found:
        raise FormatError('No recognizable Xenia saves; specify an extracted package folder and --title-id if metadata is absent')
    return found


def _full_header_for_save(save: XeniaSave, xuid: int) -> XeniaHeader:
    source = save.header
    return XeniaHeader(
        1, save.content_type, save.display_name, save.package_name, save.title_id,
        kind='canary_full', raw=(source.raw if source and source.kind in ('canary_full', 'container_header') else b''),
        profile_id=xuid.to_bytes(8, 'big'),
        console_id=source.console_id if source else None,
        full_device_id=source.full_device_id if source else None,
        metadata_version=source.metadata_version if source else 2,
        thumbnail=save.thumbnail if save.thumbnail is not None else (source.thumbnail if source else None),
    )


def _legacy_header_for_save(save: XeniaSave) -> XeniaHeader:
    source = save.header
    if source is not None and len(source.raw) == 0x14C:
        return XeniaHeader(1, save.content_type, save.display_name, save.package_name,
                           save.title_id, source.aggregate_value, source.license_mask,
                           source.kind, source.raw)
    return XeniaHeader(1, save.content_type, save.display_name, save.package_name,
                       save.title_id, kind='aggregate')


def write_save(save: XeniaSave, root: Path, *, layout: str | None = None) -> Path:
    """Write an extracted save as current Canary or legacy Xenia layout.

    `None` preserves the old convenient behaviour: profile-aware saves become
    Canary output, while profile-less synthetic/legacy saves use title-root.
    """
    if save.content_type != 1 or save.title_id in (0, 0xffffffff):
        raise FormatError('Output requires a Saved Game and a concrete Title ID')
    if layout is None:
        layout = 'canary' if save.xuid is not None else 'legacy'
    if layout not in ('canary', 'legacy'):
        raise FormatError("Xenia output layout must be 'canary' or 'legacy'")
    if layout == 'canary' and save.xuid is None:
        raise FormatError('Current Canary output requires a target XUID')
    name = safe_component(save.package_name, 42)
    prefix = Path(f'{save.xuid:016X}') if layout == 'canary' else Path()
    base = Path(root) / prefix / f'{save.title_id:08X}'
    package = base / '00000001' / name
    if package.exists():
        raise FormatError('Refuse to overwrite an existing Xenia package')
    seen = set()
    directories = _normalise_directories(save.directories, save.files)
    for path in sorted(directories | set(save.files)):
        safe_path(path)
        if path.casefold() in seen:
            raise FormatError('Case-insensitive output path collision')
        seen.add(path.casefold())
    if '__thumbnail.png' in save.files:
        raise FormatError('Payload collides with reserved Xenia thumbnail filename')
    package.mkdir(parents=True)
    for directory in sorted(directories):
        (package / directory).mkdir(parents=True, exist_ok=True)
    for path, data in save.files.items():
        dest = package / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open('xb') as stream:
            stream.write(data)
    hdir = base / 'Headers' / '00000001'
    hdir.mkdir(parents=True, exist_ok=True)
    with (hdir / (name + '.header')).open('xb') as stream:
        if layout == 'canary':
            stream.write(_full_header_for_save(save, save.xuid).to_full_bytes())
        else:
            if save.thumbnail is not None:
                if not save.thumbnail.startswith(PNG_MAGIC):
                    raise FormatError('Legacy Xenia thumbnail must be PNG')
                (package / '__thumbnail.png').write_bytes(save.thumbnail)
            stream.write(_legacy_header_for_save(save).to_bytes(size=0x14C))
    return package
