# Security reporting

This tool parses untrusted binary packages and archives. Keep input backups,
run it locally, and do not use `--allow-unsafe` unless you understand the game
binding risk. No report establishes retail-console acceptance.

Before reporting a bug, remove identifiers and personal paths from JSON reports.
Provide the tool/Python version, command with paths redacted, exact error and a
minimal **synthetic** reproduction where possible. Never upload KeyVaults, CPU
keys, private keys, game saves, donor packages or copyrighted artwork to issues.

For a vulnerability involving file writes, traversal or key disclosure, use
the repository's enabled [private vulnerability reporting](https://github.com/liang-dev1/xenia-xbox360-save-converter/security/advisories/new).
Reports go to repository maintainer [liang-dev1](https://github.com/liang-dev1).
Do not post secrets or an exploit containing user data in public issues.
