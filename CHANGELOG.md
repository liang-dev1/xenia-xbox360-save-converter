# Changelog

## 0.3.0 — experimental batch conversion

- GUI all/multiple-package selection and CLI `--batch` with repeated `--package`.
- Shared same-title CON template and standard Xbox Content output; merged Xenia
  content output. Individual backup, identity, signing and validation remain shared.
- Per-item reports, partial failure exit code 2, no output for all-failed batches,
  and guards for ambiguous names, overlaps and input changes between items.
- Synthetic batch regressions and seven private NGII package round trips.


## 0.2.0 — experimental Windows GUI

- Native Tkinter interface for inspection, verification and both conversions,
  sharing CLI backup, path, identity and signing checks.
- Responsive background work, explicit signing modes, safe close guard and
  Chinese summary/full JSON views; no saved file/key selections.
- Portable Windows x64 EXE ZIP with optional signing dependencies, dependency
  notices and SHA-256 bundle inventory; no Python installation needed.
- Pinned build environment, extracted-EXE smoke checks and source GUI regression
  tests. Authenticode signing and actual game/runtime loading remain unverified.

## 0.1.1 — experimental

- Preserve NGII embedded XUID/checksum when the observed outer account is unchanged,
  including native CON → Xenia → unchanged signed donor round trips.
- Reject conflicting `--source-xuid` hints instead of bypassing identity safety.
- Keep content-shaped directories inside game payloads from becoming new packages.
- Reject ZIP implicit file/directory and case-insensitive parent collisions.
- Reject output/backup overlaps before creating any backup or output.
- Report source CON integrity/signature separately on Xbox → Xenia conversion.
- Add eight regression tests; 45 opt-in local tests pass.

## 0.1.0 — experimental

- Generic STFS Saved Game parsing, donor-based rebuilding and L0/L1/L2 integrity
  validation, separate from game payload logic.
- Xenia legacy/Canary metadata and extracted-layout import/export; Manager ZIP
  import; mandatory verified backups and SHA-256 file provenance.
- Optional explicit key-backed CON signing, unsigned drafts and byte-identical
  donor preservation. Certificate trust and hardware loading remain unverified.
- First adapter: NGII observed story/system checksum and system XUID rebinding.
- Synthetic tests, opt-in private fixture tests, source artifact allowlist audit.

Runtime loading and retail Xbox 360 acceptance remain unverified.
