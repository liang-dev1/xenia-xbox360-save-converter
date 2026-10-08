# STFS/XContent format audit

This is a reference for the generic container layer. A valid STFS filesystem
does not establish that a game payload or a retail Xbox 360 will accept it.
Implementation claims below were cross-checked against the pinned `stfschk`
source, not only historical pseudocode.

## Boundary and signing

XContent begins with big-endian `CON `, `LIVE`, or `PIRS`. STFS is its
filesystem, separate from a game's save payload. Game payloads may carry their
own encryption, checksum, version and profile/XUID binding.

`CON ` is writable console-signed content. `LIVE` and `PIRS` are read-only
Microsoft-signed content. Rehashing STFS or recomputing Content ID cannot
produce a retail-accepted CON signature: changing signed data requires private
material matching the certificate in the header. LIVE/PIRS require Microsoft's
private signing material. A donor/template gives compatible metadata/layout;
it does not retain a valid signature after mutation.

References: [Free60 STFS](https://free60.org/System-Software/Formats/STFS/),
[Free60 source pinned at 29d8bef](https://github.com/Free60Project/wiki/blob/29d8bef83a6f948641bd2723d2c7dc72e403d392/docs/System-Software/Formats/STFS.md),
[stfschk README pinned at 521d58b](https://github.com/emoose/xbox-reversing/blob/521d58be84ef3c855239c1e2be855e1bc215a995/stfschk/README.md).

## Header and metadata

Multibyte XContent metadata fields are big-endian unless called out. Round
`HeaderSize` up to `0x1000` for the backing-block base; never hard-code
`0xC000`.

| Offset | Size | Meaning |
| --- | ---: | --- |
| `0x000` | 4 | magic |
| `0x004` | `0x228` | CON certificate/signature region; LIVE/PIRS signature plus padding |
| `0x22C` | `0x100` | 16 license descriptors (`u64 id`, `u32 bits`, `u32 flags`) |
| `0x32C` | `0x14` | Content ID SHA-1 over `[0x344, round_up(HeaderSize,0x1000))` |
| `0x340` | 4 | HeaderSize |
| `0x344` | 4 | ContentType; Saved Game=`1` |
| `0x348` | 4 | metadata version |
| `0x34C` | 8 | ContentSize; do not confuse with embedded file total |
| `0x354..0x36B` | 24 | execution ID, including Title ID |
| `0x36C` | 5 | Console ID |
| `0x371` | 8 | Creator/Profile ID (normally XUID) |
| `0x379` | `0x24` | STFS descriptor |
| `0x39D` | 4 | `DataFiles` metadata field; do not treat as the STFS file-table count |
| `0x3A1` | 8 | `DataFilesSize` metadata field; do not treat as the STFS payload-byte sum |
| `0x3A9` | 4 | VolumeType (`0` STFS, `1` SVOD) |
| `0x3FD` | `0x14` | Device ID |
| `0x411` / `0xD11` | `0x900` each | nine UTF-16BE display name/description slots |
| `0x1611` / `0x1691` | `0x80` each | UTF-16BE publisher/title slots |
| `0x1712` / `0x1716` | 4 each | thumbnail byte sizes |

Metadata v1 has thumbnail slots `0x4000` at `0x171A` and `0x571A`. V2 has
slots `0x3D00` at those offsets, plus `0x300` extended-name and description
regions at `0x541A` and `0x941A`. Writers must bound image size to the active
metadata-version slot. The Content ID range/SVOD gate is independently
implemented in [stfschk lines 156-200](https://github.com/emoose/xbox-reversing/blob/521d58be84ef3c855239c1e2be855e1bc215a995/stfschk/StfsFileSystem.cs#L156-L200).

## Volume descriptor

At `0x379`, descriptor length must be `0x24`.

| Relative offset | Encoding | Meaning |
| --- | --- | --- |
| `0x00` | byte | descriptor length |
| `0x01` | byte | version |
| `0x02` | byte | bit 0 ReadOnlyFormat, bit 1 RootActiveIndex; bits 2/3 reserved directory/index flags |
| `0x03` | u16 LE | directory/file-table block count |
| `0x05` | u24 LE | first directory/file-table data-block number |
| `0x08` | 20 bytes | root hash-table SHA-1 |
| `0x1C` | u32 BE | total logical data blocks |
| `0x20` | u32 BE | free logical data blocks |

The native NGII sample has bytes `01 00` at this descriptor's directory-count
field, proving the count is little-endian. The first-block u24 is documented
as little-endian by Free60; test it against the actual package because the
included NGII sample's first directory block is zero and cannot independently
distinguish byte order. The total/free counts are big-endian. See
[stfschk descriptor struct](https://github.com/emoose/xbox-reversing/blob/521d58be84ef3c855239c1e2be855e1bc215a995/stfschk/StfsStructs.cs#L83-L143).

### Writable/read-only and male/female layouts

The usual `female`/`male` labels refer to hash-table copy count, not payload
format:

| ReadOnlyFormat | class | physical table copies | L0/L1 table steps |
| --- | --- | ---: | --- |
| 1 | LIVE/PIRS read-only | 1 | `0xAB`, `0x718F` |
| 0 | CON writable | 2 | `0xAC`, `0x723A` |

Writable tables are transactional. Begin at descriptor `RootActiveIndex`; on
each L2/L1 entry use bit 6 (`ActiveIndex`) to choose that child table's primary
or secondary physical copy (`+0x1000`). Read-only packages always use the
primary copy. This is corroborated by [Xenia's STFS reader](https://github.com/xenia-project/xenia/blob/95a5c3ee250f80c3b9d139658649d9ffb6db3eec/src/xenia/vfs/devices/stfs_container_device.cc) and [stfschk's active-copy traversal](https://github.com/emoose/xbox-reversing/blob/521d58be84ef3c855239c1e2be855e1bc215a995/stfschk/StfsFileSystem.cs#L609-L635).

## Hash tree and addressing

A logical data block and every hash table are `0x1000` bytes. A table has 170
entries: `0xAA * 0x18 = 0xFF0`, then u32 BE committed count and 12 padding
bytes. An entry is SHA-1[20], flag byte, u24 BE.

* L0 u24 is the next logical data block; `0xFFFFFF` is end of chain. Its state
  field is `0x00` unused, `0x40` free, `0x80` used, `0xC0` newly allocated.
* At L1/L2, flag bit 6 is ActiveIndex. Do not parse their trailing u24 as an
  L0 data chain pointer.
* Capacities: L0=`0xAA`, L1=`0x70E4` (`0xAA²`), L2=`0x4AF768` (`0xAA³`).

Let `c = ReadOnlyFormat ? 1 : 2` and `base = round_up(HeaderSize,0x1000)`.
Data block `n` maps to backing block `n + sum(c * floor((n+b)/b))`, for
`b = 0xAA, 0x70E4, 0x4AF768`, stopping after the first `n < b`. Offset is
`base + backing * 0x1000`.

Hash backing mapping:

* L0: `0` if `n/0xAA==0`; otherwise `(n/0xAA)*step0 +
  ((n/0x70E4)+1)*c`, return it if `n<0x70E4`, else add `c`.
* L1: `step0` if `n/0x70E4==0`; otherwise `(n/0x70E4)*step1+c`.
* L2: `step1`.

Record index is `n%0xAA` (L0), `(n/0xAA)%0xAA` (L1), or
`(n/0x70E4)%0xAA` (L2). Write hashes bottom-up: full padded data → selected
L0 → selected L1 → selected L2/root hash, then recompute Content ID. Exact
formulae: [stfschk lines 456-635](https://github.com/emoose/xbox-reversing/blob/521d58be84ef3c855239c1e2be855e1bc215a995/stfschk/StfsFileSystem.cs#L456-L635), [hash structs](https://github.com/emoose/xbox-reversing/blob/521d58be84ef3c855239c1e2be855e1bc215a995/stfschk/StfsStructs.cs#L146-L193).

## Directory/file table

The descriptor first block is a logical data block and directory blocks follow
the selected L0 next-block chain. Each is 64 entries × `0x40`; all-zero entries
end the listing.

| Offset | Encoding | Meaning |
| --- | --- | --- |
| `0x00` | ASCII[40] | null-padded name |
| `0x28` | byte | low 6 name length; bit 6 contiguous; bit 7 directory |
| `0x29` | u24 LE | valid data blocks |
| `0x2C` | u24 LE | allocated blocks |
| `0x2F` | u24 LE | first data block |
| `0x32` | u16 BE | parent entry index; `0xFFFF` root |
| `0x34` | u32 BE | byte size / directory child-index union |
| `0x38`,`0x3C` | u32 BE | FAT-style creation/write timestamps |

A contiguous file uses successive logical blocks; an unflagged one follows L0
next pointers to `0xFFFFFF`. Require `ceil(byte_size/0x1000)` blocks and trim
the final read. Reconstruct paths by recursive parent **entry index**, never
by byte offset. `AllocationBlocks` and `ValidDataBlocks` are per-entry; header
`DataFiles`/`DataFilesSize` are not a trustworthy mirror of the STFS file
table: the native NGII CON sample contains an embedded payload while both are
zero. Do not derive or enforce them from the directory listing in v1; preserve
template values unless a separately verified content-type rule requires them.
Sources:
[Free60 listing](https://free60.org/System-Software/Formats/STFS/#file-listing),
[stfschk entry struct](https://github.com/emoose/xbox-reversing/blob/521d58be84ef3c855239c1e2be855e1bc215a995/stfschk/StfsStructs.cs#L612-L736),
[chain traversal](https://github.com/emoose/xbox-reversing/blob/521d58be84ef3c855239c1e2be855e1bc215a995/stfschk/StfsFileSystem.cs#L637-L649).

## Signature modes

CON has its console certificate at `0x004..0x1AB` and a 128-byte package
signature at `0x1AC`; LIVE/PIRS use a 256-byte signature at `0x004` over the
Content ID. Design modes must report signature state independently:

1. extract/Xenia: parse and verify container; no retail CON creation claim;
2. donor/template: use only with an approved signing path; mutation makes an
   original signature stale;
3. key-backed: invoke user-supplied external signer, do not store keys; and
4. no key: report structurally valid but `retail signature unverified/invalid`,
   never `console-ready`.

## stfschk independent validation and licensing

`emoose/xbox-reversing` tag `stfschk-0.2` is
`521d58be84ef3c855239c1e2be855e1bc215a995`, BSD-3-Clause. It verifies
Content ID, hash tables/data, directory chains, size and selected metadata;
it supports XContent but not PEC/STFC and is read-only. Use it as a process
level integration validator, avoiding source copying. Release 0.2 declares a
.NET Framework 4.7.2 binary. This workspace has .NET Framework 4.8
(`Release=533509`) but no .NET SDK, so `dotnet build` cannot run; GitHub asset
retrieval initially failed with TLS/authentication errors. On 2026-10-08 the
official asset was fetched through the release API and executed against 13
packages. See [VALIDATION.md](VALIDATION.md) for the binary hash, zero-invalid
hash/tree results and retained nonfatal diagnostics.

* [release](https://github.com/emoose/xbox-reversing/releases/tag/stfschk-0.2)
* [BSD-3 license](https://github.com/emoose/xbox-reversing/blob/521d58be84ef3c855239c1e2be855e1bc215a995/LICENSE)
* [project target netcoreapp3.1](https://github.com/emoose/xbox-reversing/blob/521d58be84ef3c855239c1e2be855e1bc215a995/stfschk/STFSChk.csproj)

Velocity/XboxInternals is GPL-3.0 according to its
[pinned README](https://github.com/hetelek/Velocity/blob/cf0b84cc8bbfad09c655476c6a3c762836ce1246/README.md); treat it as format
reference only unless the project intentionally adopts GPL-3.0. Free60 is
documentation. Check Xenia's own license before copying its code; agreement on
an algorithm does not itself authorize copying implementation.

The previously downloaded `ngii_save_update_source.zip` was also inspected as
an input-only reference: it contains only `ncg_main.cpp` and `ncg_main.h`, with
no `LICENSE`, `COPYING`, or README. Its licence is therefore **unknown** from
the supplied material; do not copy it into this project. Treat any resulting
NGII checksum support as independently authored code checked against observed
binary sums and synthetic test vectors; no supplied utility code was copied.

## Required writer tests

For each output, reparse and assert: header/metadata bounds and IDs; exact
paths and payload bytes; preserved/explicitly modelled DataFiles metadata;
exact non-looping chains;
selected L0/L1/L2 and root SHA-1; Content ID; and separately reported signing
state. Then validate game-specific payload integrity through an adapter. A
hardware load remains required unless it has actually been observed.
