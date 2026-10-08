# Xenia ↔ Xbox 360 Save Converter

A local, backup-first converter for Xbox 360 **Saved Game** file trees. Python
3.11+, GPL-3.0-or-later. This first release uses a generic STFS/XContent core and a
small game-adapter registry. Ninja Gaiden II is a test case, not a container rule.

**Changed saves need a new CON signature. A donor is metadata, not signing
authority.** Without explicitly supplied signing material, changed exports are
unsigned drafts and are not usable as retail-console saves. Successful RSA
verification also does not prove certificate trust or that a game will load.

## Install and run

```sh
python -m pip install .
# Optional content-RSA verification and caller-supplied KeyVault signing:
python -m pip install '.[signing]'
python -m xsave --help
python -m xsave inspect /path/to/content
python -m xsave verify /path/to/console-save
```

For tested optional versions, use `pip install -r requirements-signing.txt`.
There is no SDK dependency, embedded console key, game data, cloud upload, or
automatic download. You can also run `python -m xsave` from the source checkout.

## Xbox 360 → Xenia

```sh
python -m xsave to-xenia /path/to/console-save --output /path/to/new-content
# Explicitly choose the receiving Canary account when needed:
python -m xsave to-xenia /path/to/console-save --output /path/to/new-content \
  --xuid 0123456789ABCDEF
# Master/older extracted layout:
python -m xsave to-xenia /path/to/console-save --output /path/to/new-content \
  --layout legacy
```

The new content root is staged, rediscovered, and checked against the input file
tree. Canary output includes its full XContent metadata sidecar. Legacy output
uses title/content directories and the thumbnail auxiliary file. Point your
emulator at the exported content root or copy that tree into the appropriate
existing content directory yourself. Output never replaces an existing tree.
Choose a profile that exists in the emulator: structural verification cannot
prove the receiving runtime/account setup is correct.

## Xenia → Xbox 360

```sh
# Structural draft, intentionally not signed for retail:
python -m xsave to-xbox /path/to/extracted/package --template /path/to/same-game-CON \
  --output /path/to/new-save --unsigned
# Explicitly supplied decrypted KeyVault, never copied into the repository:
python -m xsave to-xbox /path/to/extracted/package --template /path/to/same-game-CON \
  --output /path/to/new-save --keyvault /private/path/KeyVault
```

The template must be a verified **CON Saved Game of the same Title ID**. The
writer rebuilds directories, allocation chains and the complete hash tree. It
preserves execution/version metadata from the donor; matching Title ID alone
does not establish region or Title Update compatibility. The donor's Profile ID
is the default receiving identity; `--profile-id` overrides it. `--source-xuid`
supplies otherwise missing source identity, and `--title-id` supplies missing
extracted-folder metadata. Multi-package inputs require `--package NAME`.

Signing accepts a caller-supplied **decrypted** 0x3FF0/0x4000 KeyVault and verifies
that its RSA key matches its certificate. You are responsible for the authority
and suitability of that material. The tool does not extract/decrypt KeyVaults,
fetch shared signing keys, validate the Microsoft certificate issuer chain, or
claim that using any particular key makes a retail console accept the save.
LIVE/PIRS can be identified/extracted, but this project does not sign them.

An unchanged donor may retain its existing content signature. Changing payload,
Profile ID, metadata, or the hash root invalidates that signature. Rehashing
cannot repair it. Key-only creation without a donor is outside v0.1 scope.

## What is generic, and what is not

| Layer | Supported behavior | What is not established |
| --- | --- | --- |
| STFS | Parse/rebuild/validate L0/L1/L2, single/double tables, active copies, fragmented input, nested files/directories | Every historical STFS variant; SVOD/PEC are rejected |
| Xenia | Extracted title layout, Canary profile layout, CON files, legacy/full headers, Manager `.xsave` ZIP import | Every future emulator build; runtime loading has not been tested |
| Identity | Separate path XUID, header evidence, CON Profile/Device/Console IDs; explicit changes | Arbitrary game's account binding or encryption |
| Signing | Public content-RSA check, optional explicit key-backed signing, unsigned draft, unchanged donor preservation | Issuer trust, LIVE/PIRS signing, retail load guarantee |
| Payload | Preserve opaque bytes by default; game adapters can validate/rebind known formats | Universal checksum/encryption repair |

Unknown-game identity changes are blocked unless `--allow-unsafe` is explicitly
given. That option does **not** repair a game's private checksum/binding; it
records an unsafe conversion. Unknown source identity is warned about, not
invented. Even an adapter's successful known-checksum validation is not proof
that every private game mechanism has been discovered.

NGII (`544307D5`) currently recognizes the supplied 31,744-byte story structure
and 2,048-byte system structure. Its adapter checks the observed big-endian word
sum and updates the system XUID plus checksum on rebinding. Replay and other
formats remain opaque. See [compatibility](docs/COMPATIBILITY.md).

## Backups and verification

Conversions always make a verified ZIP snapshot beside the output in
`.xsave-backups/` (override with `--backup-dir`). No in-place replacement is
supported. Inputs, output and backup locations must not overlap. Signing keys
must stay outside backed-up input trees; they are not included in reports.
Protect backups like originals: they contain user data and identifying metadata.
On Windows, verified trees are published by rename. POSIX directories use
exclusive creation followed by moving verified children; interruption can leave
a partial new output, while source saves remain untouched.

JSON reports distinguish hash-tree/content-ID integrity, content-RSA status,
adapter checks, per-file input/output SHA-256 provenance, unsafe identity changes,
and unperformed hardware/runtime tests. “valid” RSA means a mathematical check
against the included certificate key, **not** certification of the issuer.
`structural_valid` confirms only the parsed filesystem structure.

Portable ASCII paths are required in v0.1. Links, junctions, traversal, name
collisions, malformed hashes/chains, encrypted ZIPs and inputs over 256 MiB are
rejected. Resource limits intentionally cover L2 while bounding memory. Metadata
fields not established as payload totals are preserved instead of fabricated.

## Tests and releases

```sh
python -m unittest discover -s tests -t . -v
# Opt-in private fixtures; all generated data stays under ignored .local/:
# set XSAVE_SAMPLE_ROOT to the directory containing simu/ and 360original/
python -m unittest tests.test_real_samples -v
python tools/release_audit.py --help
```

Synthetic tests cover both table layouts, L0/L1/L2 boundaries, corruption,
fragmentation, directory/file cases, signing, sidecar formats, ZIP safety,
mandatory backups and bidirectional conversion. Signing tests skip if the
optional dependency is absent. No copyrighted payload is committed as a fixture.

See [validation evidence](docs/VALIDATION.md), [architecture](docs/DESIGN.md),
[pinned Xenia research](docs/research-xenia.md), [STFS research](docs/research-stfs.md),
[license audit](docs/THIRD_PARTY.md), and [release checklist](docs/RELEASE_CHECKLIST.md).
Release artifacts must pass the source allowlist audit; `.local/` and `.research/`
must never be published. Releases are explicitly experimental: see the
[GitHub repository](https://github.com/liang-dev1/xenia-xbox360-save-converter)
and [release downloads](https://github.com/liang-dev1/xenia-xbox360-save-converter/releases).

## Add a game adapter

Add a small function returning `AdapterResult` and register its Title ID in
`xsave/adapters/__init__.py`. Work on payload bytes only. Reject unknown versions,
test known checksums and reversible identity changes with synthetic fixtures,
and document what remains unverified. Keep STFS offsets and CON signing out of
game adapters. Dynamic third-party plugin loading is deliberately not needed
for the first release.

## License and provenance

Authored project code is licensed under [GPL-3.0-or-later](LICENSE). Reference
implementations are studied, not vendored. In particular, Velocity/XboxInternals
are GPL projects; do not copy them into a permissively licensed fork without
addressing their license obligations. Consult the third-party inventory before
importing code. No Xbox SDK files, saves, artwork, KeyVaults or private keys are
part of the public source package.
