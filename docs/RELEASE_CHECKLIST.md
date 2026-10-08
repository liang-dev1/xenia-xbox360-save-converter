# First-release checklist — 2026-10-08

Completed local boxes mean local evidence exists. Remote checks are listed separately.
See [VALIDATION.md](VALIDATION.md) for actual test scope.

## Completed locally

- [x] Generic STFS core and separate adapter registry; no NGII rule in container code.
- [x] Xenia legacy/Canary and Manager ZIP import; both conversion directions.
- [x] Same-title CON donor required; unsigned/key-backed/unchanged modes documented.
- [x] Identity metadata, payload SHA-256 provenance and unsafe-conversion reporting.
- [x] Verified backups, overlap/overwrite refusal, staging, changing-input checks.
- [x] Synthetic round trips/negative tests and real NGII integration tests executed.
- [x] Independent stfschk executed; nonfatal diagnostics retained and documented.
- [x] Full GPL-3.0 license text; authored code declared GPL-3.0-or-later.
- [x] Reference/dependency license inventory; no reference implementation vendored.
- [x] Tested optional dependency version pins; source-only release allowlist.
- [x] README, compatibility, validation, security and issue guidance.
- [x] Windows/Linux Python 3.11/3.12 CI configuration, including stdlib-only testing.

## Before public release

- [ ] Run GitHub CI from a clean checkout; Linux/Python 3.11 remain locally untested.
- [x] Enable private vulnerability reporting; identify the repository maintainer in SECURITY.md.
- [ ] Final maintainer secret/copyright/license review of source, history and
  archives. Allowlisting is not a complete semantic secret scan.
- [ ] If dependencies are later bundled as binaries, generate their complete
  OpenSSL/Rust/transitive binary SBOM. Current artifacts do not bundle them.
- [ ] Create repository/tag/release and publish final artifact hashes after review.

## Before runtime or retail-compatibility claims

- [ ] Actual receiving Xenia/Canary load/re-save with matching profile/configuration.
- [ ] Retail Xbox 360 load/save cycle using authorized suitable signing material,
  correct account/device and matching game/region/Title Update.
- [ ] Game/version-specific results; do not generalize NGII coverage to all games.
- [ ] Adapters for newly observed private encryption/checksum/binding; replay and
  unknown payloads remain opaque.
- [ ] Resolve independent-validator metadata/size diagnostics before claiming
  conformance beyond the tested hash/tree behavior.

The project can be published as an explicitly experimental converter while
retaining these boundaries. No unchecked hardware/runtime result is invented.
