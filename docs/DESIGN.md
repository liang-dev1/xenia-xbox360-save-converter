# Xenia ↔ Xbox 360 Save Converter, v0.1 design

Goal: convert Saved Game file trees with provable byte provenance, STFS integrity,
explicit identity handling and honest console-acceptance limitations.

Python 3.11+, standard-library CLI/files/backup/testing; cryptography for private
RSA signing. GPL-3.0-or-later for this authored implementation. Reference projects
are inspected rather than vendored. No SDK, copyrighted payload or signing key is
distributed. All operations and generated evidence for this project stay here.

## Modules

- `xsave/stfs.py`: bounded hostile-input parser, file tree, metadata, L0/L1/L2
  hash validation and deterministic fresh writer from a donor header. Understands
  single/double hash tables and active copies. No game identifiers here.
- `xsave/signing.py`: CON public-signature check and explicit decrypted keyvault
  signing; match certificate to key, use cryptography, no keys shipped. Issuer
  certificate trust is a separate unknown, never equated with content RSA validity.
- `xsave/xenia.py`: discover known extracted layouts and STFS package saves,
  read/write actual XCONTENT headers, keep emulator auxiliaries separate from game
  files. Unknown/ambiguous trees fail with actionable metadata requirements.
- `xsave/adapters/`: plain game adapter registry; NGII is the first adapter,
  registered by Title ID. Validate and rebind only identified game structures.
  The generic adapter keeps bytes unchanged and reports unknown payload integrity.
- `xsave/converter.py`: backup inputs, enforce paths/identity, convert in staging,
  verify before publishing locally, emit SHA-256 provenance and explicit statuses.
- `xsave/cli.py`: inspect, verify, to-xenia and to-xbox commands, JSON results.

## Modes and limits

Xbox → Xenia extracts verified Saved Game STFS to a chosen Xenia content root with
profile/title/content/package paths, XCONTENT metadata and thumbnail. Read-only
LIVE/PIRS identification must not imply their signatures can be regenerated.

Xenia → Xbox requires a same-title Saved Game CON donor. Payload sizes, number of
files and nested directories may change; rebuild the file tree/hash tree rather
than overwriting fixed offsets. Explicit key-backed mode re-signs. Donor-only mode
may preserve an existing valid package only when unchanged; otherwise explicit
unsigned draft mode clears stale signature and reports it unusable on retail.
Key-only creation without an execution-info donor is intentionally not v0.1.

Generic payloads are opaque. Exact preservation needs no game adapter; changing
identity for an unrecognized game requires explicit unsafe acknowledgement and
reports a game-adapter warning. Known adapters validate/rebind own game checksum.
XUID in emulator paths/header is not automatically the same as STFS Profile ID.
Unknown identity stays unknown until explicitly supplied; never fabricate it.

Memory bounded parser/writer limits are explicit. Unsupported PEC/SVOD, malformed
chains, unsafe names, links, oversized archives and conflicting metadata fail.
Metadata v2 extended display fields and thumbnail capacity must be preserved.

Backups are mandatory, content-addressed and verified; outputs cannot overlap
inputs. Outputs are staged and verified before publication without replacing an
existing destination. Windows uses rename; POSIX files use exclusive hard links
and directories use exclusive creation/moving children, which may leave a partial
new tree on interruption. Explicit signing keys must be outside backed-up inputs.
Reports distinguish hashes, content signature, issuer trust, game checksum
and hardware load. Real-console load is always `not_tested` unless independently
performed; this project does not make that claim.

## Acceptance

Synthetic L0/L1/L2 single/double-table round trips, nesting/empty files, fragmented
input, corrupt hashes/metadata/paths, private-key mismatch, mutation rejection,
Xenia header variants and bidirectional file-tree round trips. A local-only real
NGII integration test reads previous inputs without modifying them; unsigned mode
and explicit external key-backed mode are tested separately. No real fixtures
enter the release archive. Independent parser checks complement self round trips.
