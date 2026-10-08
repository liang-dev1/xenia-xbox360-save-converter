# Validation evidence — 2026-10-08

Actual local environment: Windows, Python 3.12.14, cryptography 50.0.2.
Dependency versions/licenses are in [DEPENDENCIES.json](DEPENDENCIES.json).

| Check | Actual result |
| --- | --- |
| Default unittest discovery | 45 discovered: 44 passed, private-fixture test skipped |
| Discovery with `XSAVE_SAMPLE_ROOT` | All 45 passed |
| `python -S` stdlib-only discovery | 42 passed; two optional signing tests and private-fixture test skipped |
| Container coverage | L0/L1/L2, single/double tables, active copies, fragmentation, nesting, empty files/directories, multiblock file table, v2 metadata, corruption |
| Signing coverage | Synthetic keyvault/RSA material, content signature and mutation rejection, signed conversion, unchanged donor preservation |
| Conversion safety | Verified backups, overlap/overwrite refusal, changed-input detection, title mismatch, key outside backed-up input tree |
| Xenia coverage | Legacy/full headers, license preservation, sidecar/container distinction, layout/ZIP discovery, orphan headers and hostile paths |
| Installed distribution | Offline wheel install; isolated `-I -S` installed CLI completed a bidirectional byte-preserving conversion |
| Packaging | Wheel/sdist/source ZIP inventories checked; local Git stage includes only 40 allowlisted source files |
| GitHub CI | Windows/Linux Python 3.11/3.12 stdlib matrix and Linux signing job all passed; [initial run](https://github.com/liang-dev1/xenia-xbox360-save-converter/actions/runs/37787085052) at commit `9cdde56` |

## Real NGII samples

- **66 original files unchanged**, proved by before/after SHA-256.
- **26 original CON packages** parsed; selected hashes/content IDs and content RSA
  signatures valid. Replay container validity does not prove replay compatibility.
- **7 actual Xenia packages** (six story, one system) completed Xenia → unsigned
  CON → Canary tree round trips. Sidecar-only slots were not turned into saves.
- Title ID remains `544307D5`; Content Type remains `00000001`.
- Six story payloads remain byte-identical. The system adapter changes only the
  known XUID/checksum; reversing those changes restores the original bytes.
- Converted payloads differ from donor payloads, proving Xenia provenance.
- A native system CON with distinct outer/embedded identities exports without
  payload changes and returns to its identical, originally signed donor bytes.
- A slot without a same-name donor uses a same-title donor selected by actual
  payload size/header. The generic writer rebuilds the source filename.

The system donor's outer Profile ID differs from its embedded XUID and directory
identity. Default conversion uses the outer Profile ID; choose the receiving
profile explicitly when necessary. These identities are not assumed equal.
If the observed outer identity is unchanged, the adapter preserves the embedded
XUID and reports its mismatch. Default native extraction does not rebind it.

## Post-publication review

Independent code and architecture reviews of v0.1.0 found two high-priority
identity defects and three input/output validation defects. v0.1.1 adds regression
coverage for default NGII byte preservation, originally signed donor restoration,
conflicting source-XUID hints, nested payload content paths, ZIP implicit directory
collisions and output/backup overlaps. Source CON signature status is now reported
separately during extraction. Passing tests do not replace hardware validation.

Real outputs are **unsigned drafts, not console-ready**. Synthetic signing tests
do not provide authorized retail credentials. Private runs, backups and reports
are only under ignored `.local/ngii/`, with `.local/ngii-latest.json` pointing to
the latest run. No sample or account ID is distributed.

## Independent validation

Official [stfschk 0.2](https://github.com/emoose/xbox-reversing/releases/tag/stfschk-0.2),
BSD-3-Clause source pin `521d58be84ef3c855239c1e2be855e1bc215a995`, was executed
from ignored `.research/`. Downloaded executable SHA-256:
`4ce12a6d5e7f816f011b4e7be6534b85e1a49b83b23b66c991968314951170d5`.

**13 packages report No errors detected:** six synthetic L0/L1/L2 single/double
cases plus seven NGII drafts. Hash tables, data blocks, directory entries and
missing-block checks show zero invalid. Logs remain in `.local/independent/`.

Nonfatal diagnostics are retained: zero ContentSize differs from a computed
expectation; writable packages may be reported 4096 bytes oversized; synthetic
fixtures produce padded-header/read-only-CON-layout warnings. Native donor values
are preserved, and our parser requires the final mapped block. This is not a
perfect metadata/size conformance certificate. stfschk reports CON signature
**unknown (console signed)**; separate content-RSA checks are necessary.

## Not verified

No Xenia executable loaded these exports; pinned-source conformance and our
rediscovery establish structure only. No retail Xbox 360 load/save cycle or
certificate issuer trust check occurred. Region/Title Update, other NGII versions,
replay binding and arbitrary games' encryption/checksum/binding remain unknown.
Remote CI uses synthetic fixtures; private NGII samples remain local. The
dependency inventory is not a full binary SBOM of optional third-party wheel internals.
