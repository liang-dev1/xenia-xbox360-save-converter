# Desktop GUI and Windows executable

The desktop interface wraps the existing CLI. The parser, mandatory backups,
game adapters, signing rules, path checks and reports remain shared. Tkinter is
the only UI dependency; PyInstaller is a build dependency, not a service.

The interface offers inspection, validation, Xbox → Xenia and Xenia → Xbox,
file/folder selection, package selection, optional identity/layout fields and
explicit donor-preservation, unsigned-draft or caller-supplied KeyVault modes.
Work runs on one worker thread with a queue; only the main thread touches Tk.
Closing is refused while an operation is running to avoid interrupting writes.
No key path or previous save selection is persisted by the application.

Run the source with `python -m xsave.gui`. The Windows distribution is a portable
ZIP: extract it completely and double-click `XSaveConverter.exe`. Keep the
`_internal` folder beside the executable. No Python installation is needed.
The EXE is not Authenticode-signed; Windows may show an unknown-publisher notice.

Outputs and optional JSON reports must use new paths. Canary exports target a
new content root; choose an account present in the receiving emulator. A changed
donor cannot retain its old signature. Unsigned drafts are not retail-console
saves, and key-backed signatures do not establish issuer trust or hardware load.

## Batch conversion

Inspect the input, enable **批量转换**, then use **全选**, **清空** or the
multi-select list. Inspection initially selects all discovered packages. Choose
a new output directory and click **开始**. Clearing the list does not mean
"all"; select at least one package. Changing the input clears the old selection.

Xbox output shares one same-title CON template and signing/identity settings.
Each package is written under `Content/PROFILE/TITLE/00000001/PACKAGE`. Xenia
output merges packages into one standard content root with metadata sidecars.
Use a separate batch per game for Xbox output. Unique package names are required;
when multiple accounts have the same name, choose a narrower source folder.

Conversion errors are reported per item; successful items are retained. All-failed
batches create no output directory. Staging/publishing I/O errors abort the batch;
check any reported output path before retrying. Backups remain available. Reports
include total/succeeded/failed and each item's integrity/provenance/signing status.
"Batch complete" means every item converted, not retail signature trust or game
compatibility. The current limit is 256 selected packages per batch. Each item repeats input discovery and backup
verification; large roots can be slow. Narrow the input or split the batch.
Discovery/preflight errors abort before per-item reports; even an unselected
malformed neighbour can prevent discovery. Narrow to a valid input subtree.

## Rebuild the Windows release

Build on Windows x64 using official CPython **3.14.4**, with Tcl/Tk 8.6.15 and
stdlib OpenSSL 3.0.19. These exact runtime versions are intentional license and
provenance pins; upgrading requires updating the notice collector and validating
the new binary. Source/CLI support remains Python 3.11+.

```powershell
python -m venv .local/windows-venv
.local/windows-venv/Scripts/python.exe -m pip install --require-hashes -r requirements-windows.txt
.local/windows-venv/Scripts/python.exe tools/build_windows.py
.local/windows-venv/Scripts/python.exe tools/windows_smoke.py .local/windows/0.3.0/xsave-windows-x64-0.3.0.zip --receipt .local/windows/0.3.0/smoke.json
```

The builder refuses to overwrite an existing bundle or ZIP. Preserve or remove
your previous disposable build directory before rebuilding. It uses the standard
PyInstaller Tk/cryptography hooks and retrieves hash-verified upstream
notice/source inputs. Network access is needed on the first build; the application
itself operates offline.

The windowed EXE can also run the existing CLI for automated verification:
`XSaveConverter.exe --cli inspect SAVE --report NEW-REPORT.json`. A new safe
`--report` is mandatory because there is no console. Exit code 2 means failure;
capture native stderr (for example, PowerShell `2> error.log`) for the reason.
Diagnostics also go to the Windows debugger output channel if no console/pipe
is attached. No shell interpretation is used. If conversion output was created
before a report-write failure, the error says to verify that output before retrying.

The smoke tool extracts the ZIP into a temporary project directory, verifies the
file inventory, launches/closes the actual Tk window, and tests inspection,
signature verification, both conversions and all three signing modes through
the frozen executable. Its credentials and payload are synthetic and deleted
after testing. Source GUI tests separately exercise the window's worker flow.

`THIRD_PARTY/manifest.json` includes a conservative **all-Cargo.lock-crates**
license inventory, including build/platform crates that might not occur in the
published cryptography wheel. This is not an exact compiled-crate SBOM; neither
the builder nor this project can attest that upstream wheel's build graph.
`BUILD.json` labels wheel URLs/hashes as **expected** pins; actual installed
package versions and bundled-file hashes are measured separately. CI uses
hash-required installation. The smoke tool refuses optimized Python because
optimization would disable its release assertions.

Build and distribution validation are recorded in the release notes.
Source remains GPL-3.0-or-later. The Windows ZIP must include dependency notices
and an inventory of its bundled files; private saves and signing material are
never build inputs.
