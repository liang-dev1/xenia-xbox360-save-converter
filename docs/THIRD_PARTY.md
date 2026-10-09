# Third-party sources and licensing

Reviewed: 2026-10-07. This is a source and license inventory, not legal
advice. A reference is not a dependency and does not mean that its code,
assets, test data, keys, or binaries are distributed by this project.

## Project policy

The intended project license is `GPL-3.0-or-later`. New project code must be
authored in this repository or imported only after a file-level provenance and
license review. Preserve required copyright and license notices for every
copied or modified file. Do not vendor a reference implementation merely to
avoid writing a small, independently-tested implementation.

The repository must not contain Xbox SDK material, retail or development
private keys, KeyVaults, CPU keys, certificate/private-key pairs, user saves,
game payloads, copyrighted icons/artwork, or compiled tools obtained from a
third party. Test fixtures must be synthetic or supplied under an explicit
redistribution permission.

## Reviewed references

| Reference | Review pin / retrieval state | License reported by upstream | Permitted current use | Inclusion rule |
| --- | --- | --- | --- | --- |
| [xenia-project/xenia](https://github.com/xenia-project/xenia) | `95a5c3ee250f80c3b9d139658649d9ffb6db3eec`; `LICENSE` | BSD-3-Clause | Study of Xenia content behavior and documentation | If code is copied, retain its BSD notices and audit its `third_party/` origin separately. |
| [xenia-canary/xenia-canary](https://github.com/xenia-canary/xenia-canary) | `cc4981a4659086acb1c25a485adebefc3f432ae1`; `LICENSE` | BSD-3-Clause | Study of Canary behavior | Same notice and per-file provenance rule as Xenia. |
| [xenia-manager/xenia-manager](https://github.com/xenia-manager/xenia-manager) | `a905dfe9bf0a1e2088f8ebcb660d2054e4d1602d`; `LICENSE` | BSD-3-Clause | Study of its documented extracted-header layout | Do not copy code unless the originating file and any dependencies are audited. |
| [hetelek/Velocity](https://github.com/hetelek/Velocity) and its `XboxInternals` tree | `cf0b84cc8bbfad09c655476c6a3c762836ce1246`; `COPYING` | GPL-3.0 (upstream says GPLv3) | Format research and independent tests | GPL-3.0-or-later is the intended project license, but copied files still require attribution, source availability, and a file-level audit. Do not treat the upstream tree as a permissively licensed library. |
| [emoose/xbox-reversing](https://github.com/emoose/xbox-reversing) / `stfschk` | `5f85b9ec8c771577532ca1cfa20c691e9033f2c2`; `LICENSE` | BSD-3-Clause unless otherwise stated | Independent validator/reference behavior and format research | Check the specific file before copying; retain notice and record it here. Do not bundle `stfschk` binaries without a separate packaging decision. |
| [Free60Project/wiki STFS documentation](https://github.com/Free60Project/wiki/blob/29d8bef83a6f948641bd2723d2c7dc72e403d392/docs/System-Software/Formats/STFS.md) | `29d8bef83a6f948641bd2723d2c7dc72e403d392` | No repository-wide license file was found during this review | Factual reference only | Do not copy documentation, diagrams, or code excerpts until the copyright/license status is confirmed. Cite the URL in project docs instead. |
| [GoobyCorp/Xbox-360-Crypto](https://github.com/GoobyCorp/Xbox-360-Crypto) | Public repository; exact commit could not be pinned from this environment | BSD-3-Clause as reported by GitHub | Cryptographic behavior research only | Do not copy or vendor until a future review records a full commit SHA, file path, and its license. Never import keys or binaries from this reference. |
| [ike9000e/ngii-save-update-util](https://github.com/ike9000e/ngii-save-update-util) | `ff3fb1506ce0f5b94a66f61b3e8e038900bc2010` | License status not verified in this review | Ninja Gaiden II checksum behavior research only | Treat as reference-only. Obtain a verified license and audit individual files before copying any code. |

The commit IDs were obtained with `git ls-remote` on 2026-10-07, except the
two rows explicitly marked unpinned. That command establishes the ref-to-commit
mapping only; the license conclusions above are from the exact `LICENSE` or
`COPYING` paths linked below. The pins identify a review snapshot, not a
promise that an upstream version remains unchanged.

## What this project currently incorporates

The source repository vendors no third-party implementation, binary, fixture,
or signing material. References above are not runtime dependencies themselves.
The separately built Windows portable ZIP bundles audited runtime dependencies;
its own notices and file manifest are described below.

`xsave/signing.py` lazily imports `cryptography` only for CON public-signature
verification or caller-supplied private-key operations. The planned distribution
constraint is `cryptography>=43` in an optional `signing` group; the ordinary
parser/converter must remain usable without installing it. The local development
resolution originally recorded for this review was `cryptography 50.0.1`;
2026-10-08 validation used installed `50.0.2`, recorded in `DEPENDENCIES.json`.
Its published
metadata declares `Apache-2.0 OR BSD-3-Clause`.

`cryptography`'s CPython packaging brings in `cffi`, which in turn brings in
`pycparser`; neither is directly imported by this project or vendored here.
Their inspected installed metadata declares `MIT-0` for `cffi 2.1.1` and
`BSD-3-Clause` for `pycparser 3.0`. The tested resolution is pinned in
`requirements-signing.txt`; `DEPENDENCIES.json` records the local snapshot.
A complete binary SBOM for optional wheel internals and CI platform results
remain release review tasks; the local inventory does not claim them.

## Windows 0.2.0 binary inventory

The Windows GUI uses official CPython 3.14.4 / Tcl-Tk 8.6.15, PyInstaller 6.22.3
and hooks-contrib 2026.8; build dependency resolutions are fixed in
`requirements-build.txt`. The standard upstream cryptography hook collects its
Rust and CFFI backends without collecting the CFFI development API, pycparser or
setuptools. The normal source installation remains dependency-free.

The ZIP includes the project GPL license, `BUILD.json`, SHA-256 `FILES.json`, and
75 license/notice texts under `THIRD_PARTY/`. The collector validates exact
upstream source archives, all 32 registry-crate checksums in cryptography's
Cargo.lock, and pinned notice hashes before writing a manifest. It includes
CPython's complete license (with Microsoft redistribution conditions, libffi,
zlib and stdlib notices), Tcl/Tk terms, PyInstaller bootloader/runtime-hook
notices and bootloader zlib, crypto/CFFI/pycparser notices, and both OpenSSL
versions: stdlib 3.0.19 and cryptography's static 4.0.3. Pycparser notices are a
conservative build-environment inclusion, rather than a runtime dependency.

Crate declarations include permissive MIT/Apache/BSD, LLVM exception and Unicode
terms; where upstream provides an Apache/GPL choice, Apache terms can be used.
All supplied texts are retained rather than replacing attribution with SPDX
labels. `THIRD_PARTY/manifest.json` records their sources and checksums.

This is a **conservative Cargo.lock superset**, not a precise compiled-crate
SBOM or a legal certificate. The project cannot attest the precompiled upstream
wheel's exact build graph. Exact compiler/standard-library attestation and final
maintainer legal review remain open; this limitation is published rather than
claiming a complete SBOM. No reference emulator, Xbox tool, console key or save
data is bundled.

The dependency statements in this section are provenance for package
distribution, not permission to copy their source into this repository.

## Release gate for copied material

Before merging an imported file or vendored tool:

1. Record upstream URL, immutable commit/tag, paths, author/copyright notices,
   and SPDX identifier here.
2. Record whether the source is copied, modified, generated from, or only
   consulted.
3. Keep required notices with the distributed source and in the release
   artifacts.
4. Review submodules, bundled binaries, generated output, and transitive
   dependencies separately; repository-level labels are insufficient.
5. Have a maintainer perform a legal review where the license is absent,
   ambiguous, nonstandard, or conflicts with the release plan.

## Sources

- Xenia's [LICENSE](https://github.com/xenia-project/xenia/blob/95a5c3ee250f80c3b9d139658649d9ffb6db3eec/LICENSE) and [contribution licensing note](https://github.com/xenia-project/xenia/blob/95a5c3ee250f80c3b9d139658649d9ffb6db3eec/.github/CONTRIBUTING.md).
- Xenia Canary's [LICENSE](https://github.com/xenia-canary/xenia-canary/blob/cc4981a4659086acb1c25a485adebefc3f432ae1/LICENSE).
- Xenia Manager's [LICENSE](https://github.com/xenia-manager/xenia-manager/blob/a905dfe9bf0a1e2088f8ebcb660d2054e4d1602d/LICENSE).
- Velocity's [COPYING](https://github.com/hetelek/Velocity/blob/cf0b84cc8bbfad09c655476c6a3c762836ce1246/COPYING) and [GPL-3.0 text](https://www.gnu.org/licenses/gpl-3.0.html).
- xbox-reversing's [LICENSE](https://github.com/emoose/xbox-reversing/blob/5f85b9ec8c771577532ca1cfa20c691e9033f2c2/LICENSE) and [stfschk release notes](https://github.com/emoose/xbox-reversing/releases/tag/stfschk-0.2).
- Free60's [STFS page](https://github.com/Free60Project/wiki/blob/29d8bef83a6f948641bd2723d2c7dc72e403d392/docs/System-Software/Formats/STFS.md).
- `cryptography` [50.0.1 package metadata](https://pypi.org/project/cryptography/50.0.1/) and [upstream source license](https://github.com/pyca/cryptography/blob/dc1125347f52b36b7070332910c680e68db0f478/LICENSE).
- `cffi` [package metadata](https://pypi.org/project/cffi/) and [upstream project metadata](https://github.com/python-cffi/cffi/blob/main/pyproject.toml); `pycparser` [package metadata](https://pypi.org/project/pycparser/) and [LICENSE](https://github.com/eliben/pycparser/blob/main/LICENSE).
- GitHub's [license API caveat](https://docs.github.com/en/rest/licenses/licenses): repository license detection does not cover dependencies and is not legal advice.
