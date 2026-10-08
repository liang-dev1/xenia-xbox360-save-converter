# Implementation plan

Goal: deliver a release-ready v0.1 source tree implementing docs/DESIGN.md.
Skills used: writing-plans, test-driven-development, subagent-driven-development.
User authorizes continuous implementation and routine design decisions.

1. Research primary sources and audit licenses → recorded source links/revisions,
   byte offsets and explicitly unresolved evidence in docs/research-*.md.
2. STFS/signing module → write failing synthetic tests, implement general parser
   and donor-based writer, run L0/L1/L2 and signing negative tests.
3. Xenia/adapter/conversion modules → failing header, identity, backup, CLI and
   round-trip tests; implement smallest modules satisfying them.
4. Real NGII integration → read original samples only, run both directions and
   checksum/provenance checks locally; no payload/key in repository or archive.
5. Independent review and parser validation → fix actionable findings and rerun
   affected tests; document any inability to run upstream emulator or hardware.
6. README, GPL license, CI, compatibility/release audit → build distribution,
   inspect every archive member, secret/data scan, installed CLI smoke test.

Ownership: STFS executor owns stfs.py/signing.py and their tests. Root owns
Xenia/converter/CLI/adapters and app tests. Research agents own their named docs.
No one edits previous conversion work. Fresh implementation, no donor/key shipped.

Core interface for integration:

`StfsPackage(data: bytes)`: `files: dict[str, bytes]`, `directories: set[str]`,
`metadata` with title_id/content_type/profile_id/device_id/console_id/display_name,
`validate() -> dict`, `build(files, template: bytes, directories=(), profile_id=None,
device_id=None, display_name=None, thumbnail=None, signer=None) -> bytes`.
`ConSigner.from_keyvault(bytes)` and `verify_con_signature(bytes) -> str`.
Parsing/validation errors use `xsave.errors.FormatError`.

Stop condition: all executable checks pass, local NGII integration and distribution
audit are recorded, README accurately bounds supported modes, and no required
local work remains. Publishing to a remote GitHub repository is outside this
request's publishing-preparation scope.
