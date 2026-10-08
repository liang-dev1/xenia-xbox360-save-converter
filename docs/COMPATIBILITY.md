# Compatibility boundary

| Input / action | v0.1 result |
| --- | --- |
| Standard same-identity STFS Saved Game → extracted Xenia | Generic extraction; hashes validated; runtime test still required |
| Xenia extracted files → same-title CON donor, no signing key | Explicit unsigned structural draft only |
| Changed payload + donor + matching caller-supplied signing material | Content RSA verified; certificate trust and console load still unverified |
| Identical donor files/metadata with valid original signature | Existing package bytes may be retained unchanged |
| Unknown game, identity change | Blocked, or explicitly unsafe with `--allow-unsafe` |
| Legacy Xenia input without account identity | Keep identity unknown; donor target and unknown-binding warning reported |
| NGII recognized story/system | Known checksum checked; system XUID rebinding supported |
| NGII replay/unknown version | Opaque, warning; identity change blocked without unsafe override |
| LIVE/PIRS Saved Game | Identify/extract; no LIVE/PIRS signing |
| SVOD, PEC, non-Saved-Game content | Unsupported for conversion |
| Xenia Manager `.xsave` | Safe ZIP import; selected emulator profile is external to archive |

The NGII structure was established from the supplied samples and an independent
additive-checksum calculation. Filename, length and header checks are combined;
filename alone does not select a supported story version. Region/Title Update
coverage beyond those samples has not been established. Story files have no
account rewrite in this adapter: lack of a detected binding is not proof of lack
of a binding. System identity and checksum changes are explicit in provenance.

Canary sidecar formats change across versions. Current source was reviewed at
the pinned commits in the research notes. Metadata-only CON-shaped `.header`
files are recognized separately from containers with block areas. Legacy 0x134
and 0x138 sidecars are import formats; current Canary does not accept them as
its current full-header disk representation. Preserve originals and export a
documented layout, rather than silently treating all sidecars as one ABI.

Retail testing needs a suitable console/account/device, authorized signing
material, matching game/region/Title Update and an actual load/save cycle.
Emulator testing needs the selected receiving profile and matching content-root
configuration. Neither was available in this implementation session. Test a
copy and keep the original hardware save until a load/save cycle succeeds.
