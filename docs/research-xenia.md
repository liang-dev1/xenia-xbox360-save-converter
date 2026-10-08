# Xenia、Xenia Canary 与 Xenia Manager 存档布局调研

**调研日期：** 2026-10-07。以下结论以固定源码提交为准，而非 Wiki 或第三方工具对旧格式的描述。

| 项目 | 固定提交 | 许可证 |
| --- | --- | --- |
| Xenia master | `95a5c3ee250f80c3b9d139658649d9ffb6db3eec` | BSD 3-Clause |
| Xenia Canary `canary_experimental` | `cc4981a4659086acb1c25a485adebefc3f432ae1` | BSD 3-Clause |
| Xenia Manager | `a905dfe9bf0a1e2088f8ebcb660d2054e4d1602d` | BSD 3-Clause |

Source links are pinned to these revisions. Xenia's versioned source is the authority for what that emulator build reads; Xenia Manager is an interoperability consumer, not the authority for Xenia's binary ABI.

## Confirmed layouts

### Xenia master at the pinned revision

The master `ContentManager` mounts host directories and has no XUID namespace or sidecar-header discovery. Its package location is:

```text
<content-root>/<TITLE-ID-8-HEX>/<CONTENT-TYPE-8-HEX>/<PACKAGE-NAME>/
```

The directory name supplies `file_name` and display name during enumeration. Its thumbnail is a separate package-root file named `__thumbnail.png`.

Evidence: [content_manager.cc](https://github.com/xenia-project/xenia/blob/95a5c3ee250f80c3b9d139658649d9ffb6db3eec/src/xenia/kernel/xam/content_manager.cc) and [content_manager.h](https://github.com/xenia-project/xenia/blob/95a5c3ee250f80c3b9d139658649d9ffb6db3eec/src/xenia/kernel/xam/content_manager.h).

**Conversion implication:** an extracted save can be imported into this legacy layout only after choosing a title/content-type/package directory name. The emulator cannot recover original STFS metadata from this layout.

### Xenia Canary at the pinned revision

Canary uses an XUID namespace:

```text
<content-root>/<XUID-16-HEX>/<TITLE-ID-8-HEX>/<CONTENT-TYPE-8-HEX>/<PACKAGE-NAME>
<content-root>/<XUID-16-HEX>/<TITLE-ID-8-HEX>/Headers/<CONTENT-TYPE-8-HEX>/<PACKAGE-NAME>.header
```

For ordinary extracted saves, `<PACKAGE-NAME>` is a directory containing the game payload. `00000001` is `Saved Game`. Canary can also keep an actual CON/PIRS/LIVE/STFS file at `<PACKAGE-NAME>` and opens it as a container; a directory is opened as `ContentPackageDirectory` and obtains metadata from the parallel `.header` file. Thus a converter must classify **directory/extracted** and **file/container** inputs separately.

Canary's `ResolvePackagePath` uses the metadata XUID when it is non-zero, otherwise the caller's XUID. Marketplace content is forced to common XUID zero. During the built-in content-install flow, a Saved Game's destination XUID is explicitly replaced with the profile signed into slot 0, rather than retaining the donor package's `profile_id`.

Evidence: [Canary content manager](https://github.com/xenia-canary/xenia-canary/blob/cc4981a4659086acb1c25a485adebefc3f432ae1/src/xenia/kernel/xam/content_manager.cc), [content data types](https://github.com/xenia-canary/xenia-canary/blob/cc4981a4659086acb1c25a485adebefc3f432ae1/src/xenia/kernel/xam/xcontent/xcontent.h), [directory package handling](https://github.com/xenia-canary/xenia-canary/blob/cc4981a4659086acb1c25a485adebefc3f432ae1/src/xenia/kernel/xam/xcontent/xcontent_package_directory.cc), and [Canary's migration code](https://github.com/xenia-canary/xenia-canary/blob/cc4981a4659086acb1c25a485adebefc3f432ae1/src/xenia/emulator.cc).

### Canary sidecar header formats: actual reader behaviour

There are two relevant eras. The converter should parse both, but write the current format by default for Canary.

| Form | Byte size | Current Canary extracted-directory reader | Write recommendation |
| --- | ---: | --- | --- |
| `XCONTENT_DATA` | `0x134` | **Rejected**: below `sizeof(XCONTENT_DATA_AGGREGATE)` | Parse only as an external/legacy metadata fragment; do not emit for current Canary |
| “cross-title” fragment | `0x138` | **Rejected** for the same reason | Parse cautiously only; do not emit |
| `XCONTENT_DATA_AGGREGATE` | `0x148` | Passes the size threshold, but Canary then attempts to read a following `uint32` license mask | Do not emit by itself; use `0x14C` |
| legacy aggregate + license | `0x14C` | Accepted as the old-header path | Supported compatibility output |
| current `XContentContainerHeader` | `0x971A` exact, or its `0x1000` rounded form | Accepted | Prefer rounded `0xA000`, which Canary itself writes |

The often-cited `0x134`, `0x138`, `0x148`, `0x14C` layouts are **XAM request/response data structures**, not universal current disk-header versions. Current Canary's directory loader requires at least `0x148`; therefore treating a `0x134` header as a valid current Canary sidecar is a false compatibility claim.

#### Legacy aggregate offsets

All integer fields are big-endian.

```text
0x000..0x003  device_id (u32)
0x004..0x007  content_type (u32; Saved Game = 0x00000001)
0x008..0x107  display_name (128 UTF-16BE code units)
0x108..0x131  file_name (42 bytes)
0x132..0x133  padding
0x134..0x13B  XUID (u64)                 [aggregate only]
0x13C..0x13F  title_id (u32)             [aggregate only]
0x140..0x147  not part of aggregate; do not treat as title_id for Canary
0x148..0x14B  license mask (u32)         [legacy sidecar extension]
```

This follows Canary's `XCONTENT_DATA` / `XCONTENT_DATA_AGGREGATE` definitions. `XCONTENT_DATA_INTERNAL` is a different `0x200` in-memory structure: it has `category` at `0x134`, XUID at `0x138`, Title ID at `0x140`, and license mask at `0x144`. It must not be confused with the serialized legacy aggregate sidecar.

### Observed older `0x148` headers: do not reject them

The supplied earlier Xenia samples include 0x148-byte headers with a zero value at aggregate Title ID offset `0x13C` and `0xFFFFFFFF` at `0x140`. That is consistent with an `XCONTENT_DATA_INTERNAL` **prefix** rather than an aggregate header:

```text
0x134..0x137  category (u32)
0x138..0x13F  XUID (u64)
0x140..0x143  title_id (u32)
0x144..0x147  license_mask (u32)
```

It also explains why bytes at `0x134` may look unsuitable as the high half of an aggregate XUID. The format detector must retain raw bytes and score both interpretations. The title-directory path is the placement authority; `title@0x13C`, `title@0x140`, and the full-header execution Title ID are metadata evidence that may agree, conflict, or be absent. A conflict should produce a diagnostic, not an invented repair or a corrupt-file verdict.

Xenia Manager also serializes a `0x138` "cross-title" fragment with Title ID at `0x134`. This is supported by Manager's own serializer, but it is not accepted by the pinned current Canary directory reader. Parse it for Manager/legacy import compatibility only; do not emit it as a Canary-current target.

#### Current full sidecar

`XContentContainerHeader` is:

```text
0x0000..0x0343  XContentHeader: CON/PIRS/LIVE magic, signature, licenses,
                content ID, header size
0x0344..0x9719  XContentMetadata (0x93D6): content type, metadata version,
                size, execution info including title ID, console/profile/device
                fields, STFS/SVOD descriptor, localized metadata and thumbnails
0x971A..0x9743  Canary-only 42-byte file_name_raw extension
```

Canary's `ExtractContentHeader` writes `sizeof(XContentContainerHeader)` and expands the file to `round_up(..., 0x1000)`, currently `0xA000`. This is an extracted-content metadata sidecar, **not** an STFS container and not evidence that its signature can be used on a retail Xbox 360.

For Saved Game metadata, Canary gives a nonempty sidecar `file_name_raw` precedence over the host directory basename. The extension exists specifically to preserve awkward save names such as names with trailing spaces. It is set only when the header magic is `CON `, despite the data being in an extracted directory. A converter must preserve raw names when exporting/reimporting and must not normalize trailing spaces, casing, or 42-byte truncation silently.

#### Thumbnail behaviour

Legacy Xenia master reads and writes `<package>/__thumbnail.png`. Current Canary stores the thumbnail in `XContentMetadata`. Its extracted-directory reader also recognizes a temporary/legacy `__thumbnail.png`: on `GetThumbnail` it reads that file, copies it into metadata, and removes the loose file. A lossless intermediate model should keep the thumbnail bytes separately and map them to the selected target form:

* master legacy target: `__thumbnail.png`;
* Canary current extracted target: metadata thumbnail in the full sidecar;
* retail STFS target: embedded STFS metadata thumbnail.

## Package versus extracted install modes

Canary first opens a source as an `XContentPackageContainer` when it is a file, or `ContentPackageDirectory` when it is a directory. Its install code selects either:

1. extract the container into a directory and write a full `.header` sidecar if the package is not read-only (or extraction is forced); or
2. copy the original container file intact for read-only STFS, retaining STFS/SVOD package mode (and associated `.data` fragments for SVOD).

Therefore “Canary save” is not a single file format. Import detection must report both the *storage representation* and *metadata source*: raw CON/PIRS/LIVE/STFS, extracted payload with legacy sidecar, extracted payload with full Canary sidecar, or legacy master title-root data with inferred metadata.

## Xenia Manager archive behaviour

The current Manager documentation says `.zip` and `.xsave` use this archive tree:

```text
<TITLE-ID>/
  00000001/
    <save package directory or file>
  Headers/                         # optional in published format
    00000001/
      <package-name>.header
```

The implementation confirms that `.xsave` is not a distinct binary format: `SaveManager.ImportSave` calls `ZipFile.ExtractToDirectoryAsync`, selects the first root directory as the title ID, then copies all content-type directories and `Headers` below a caller-selected destination base. Export uses `ZipFile.CreateFromDirectoryAsync` for the same tree. The selected XUID comes from the Manager UI/destination, not from an archive-root XUID directory.

Evidence: [Manager FAQ](https://github.com/xenia-manager/xenia-manager/wiki/FAQ), [SaveManager](https://github.com/xenia-manager/xenia-manager/blob/a905dfe9bf0a1e2088f8ebcb660d2054e4d1602d/source/XeniaManager.Core/Manage/SaveManager.cs), and [Manager header implementation](https://github.com/xenia-manager/xenia-manager/blob/a905dfe9bf0a1e2088f8ebcb660d2054e4d1602d/source/XeniaManager.Files/HeaderFile.cs).

**Compatibility warning:** Manager's `HeaderFile` is an old-sidecar helper. It documents and serializes `0x134..0x14C`; it is not evidence that current Canary consumes `0x134`, and it cannot faithfully parse a current `0xA000` full sidecar as that type. Its current source writes Title ID at both `0x13C` and `0x140` for interop. A converter should use the actual Canary aggregate offset (`0x13C`) for legacy output and treat the duplicate Manager field as Manager-specific tolerance, not a formal on-disk ABI.

## Required metadata for viable round trips

### Xenia extracted → canonical intermediate

Capture without guessing:

* source family and representation (master directory, Canary directory+sidecar, raw container);
* XUID path, title ID, content type, package name as raw bytes/name, and payload tree;
* source header form and every available XContent field, including profile, device/console IDs and licenses;
* thumbnail bytes and all game files exactly; and
* warnings for absent or conflicting sidecar/container/path values.

For a `0x14C` legacy sidecar, the minimum meaningful tuple is `device_id`, `content_type`, UTF-16BE display name, 42-byte package name, XUID, title ID, and license mask. For an `0xA000` sidecar or raw STFS, preserve complete metadata rather than reducing it to this tuple.

### Canonical intermediate → Xenia

* **Current Canary extracted target:** require XUID, title ID, content type, raw package name and payload; write a valid full `0xA000` sidecar. If only legacy metadata exists, generate a legacy `0x14C` sidecar only as an explicitly selected compatibility target.
* **Master legacy target:** require title ID, content type, package name and payload; emit the title-root layout. XUID/header metadata cannot be represented by the pinned master path.
* **Raw package target:** only copy a validated original container. This project must not label a reconstructed CON as raw-package-compatible without separate STFS/hash/signature validation.

For a real Xbox 360 Saved Game, the familiar content-store placement is `<profile-or-XUID>/<TITLE-ID>/00000001/<CON filename>`. Current Canary's raw-container mode has the same title/content-type/file arrangement under its XUID root, but this similarity does not make the container profile field, target path XUID, or game-private binding interchangeable. Model each separately.

### Xenia → retail Xbox 360

The Xenia sidecar cannot become a retail CON by renaming. It lacks the STFS block/hash tree and does not confer a trusted CON signature. Use it only as metadata input while constructing/replacing files in an STFS donor/template under the project's separately verified signing/template policy. Game payload integrity, per-game account binding, encryption, and checksums remain outside this Xenia-container research.

## Design handoff

1. Implement a versioned `XeniaLayoutDetector` with independent readers for legacy master directories, Canary legacy sidecars, Canary full sidecars, and raw containers.
2. Make `0xA000` full Canary sidecars the default extracted output; gate legacy `0x14C` behind an explicit compatibility profile. Reject `0x134`/`0x138` as current-Canary writer targets.
3. Preserve raw package names and thumbnails as opaque values in the intermediate model.
4. Treat Manager `.xsave` as ZIP after magic validation, never by extension alone. Require one validated title-ID root and reject archive path traversal before extraction.
5. Keep Xenia representation conversion separate from retail STFS construction/signing and from game adapters.

## Source and version caveats

* The Canary project changes rapidly; all precise statements above are scoped to `cc4981a4659086acb1c25a485adebefc3f432ae1`.
* The Canary game-saves repository and Manager wiki demonstrate archive conventions, but neither defines the current Canary sidecar ABI; source code does.
* No claim here establishes a retail Xbox 360 acceptance path. That requires STFS validation and a legitimate signature/template workflow.
