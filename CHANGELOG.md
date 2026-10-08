# Changelog

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
