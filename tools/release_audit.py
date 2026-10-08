"""Audit distributable source and optionally create an explicit allowlist ZIP.

Local samples, signing material and conversion outputs are never candidates.
"""

import argparse
from pathlib import Path
import subprocess
import sys
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TOP = {'README.md', 'LICENSE', 'pyproject.toml', '.gitignore', 'MANIFEST.in', 'SECURITY.md', 'CHANGELOG.md', 'requirements-signing.txt'}
DOCS = {'DESIGN.md', 'PLAN.md', 'THIRD_PARTY.md', 'RELEASE_CHECKLIST.md',
        'research-stfs.md', 'research-xenia.md', 'COMPATIBILITY.md', 'VALIDATION.md', 'DEPENDENCIES.json'}
CI = {'.github/workflows/tests.yml', '.github/ISSUE_TEMPLATE/bug_report.yml'}


def allowed(relative: Path) -> bool:
    parts = relative.parts
    if len(parts) == 1:
        return relative.name in TOP
    if parts[0] == 'docs' and len(parts) == 2:
        return relative.name in DOCS
    if parts[0] in ('xsave', 'tests', 'tools'):
        return relative.suffix == '.py' and len(parts) <= 3
    return relative.as_posix() in CI


def candidates() -> list[Path]:
    found = []
    for top in (*sorted(TOP), 'docs', 'xsave', 'tests', 'tools', '.github'):
        entry = ROOT / top
        if not entry.exists():
            continue
        for path in ([entry] if entry.is_file() else entry.rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts:
                found.append(path.relative_to(ROOT))
    return sorted(found)


def audit() -> list[Path]:
    files = candidates()
    missing = TOP - {item.as_posix() for item in files}
    bad = [item for item in files if not allowed(item)
           or any(p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction())
                  for p in ((ROOT / item), *(ROOT / item).parents))]
    if missing or bad:
        raise ValueError(f'missing release files: {sorted(missing)}; forbidden files: {bad}')
    # If this is its own Git repository, also catch accidental tracked binaries or samples.
    repo = subprocess.run(['git', 'rev-parse', '--show-toplevel'], cwd=ROOT,
                          capture_output=True, text=True, check=False)
    if repo.returncode == 0 and Path(repo.stdout.strip()).resolve() == ROOT:
        tracked = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT,
                                 capture_output=True, check=True).stdout
        bad_tracked = [Path(name.decode()) for name in tracked.split(b'\0') if name
                       and not allowed(Path(name.decode()))]
        if bad_tracked:
            raise ValueError(f'forbidden tracked files: {bad_tracked}')
    return files


def build_zip(files: list[Path]) -> Path:
    version = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    output = ROOT / '.local' / f'xsave-source-{version}.zip'
    output.parent.mkdir(exist_ok=True)
    if output.exists():
        raise ValueError(f'refuse to overwrite {output}')
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in files:
            metadata = zipfile.ZipInfo(relative.as_posix(), (2026, 1, 1, 0, 0, 0))
            metadata.compress_type = zipfile.ZIP_DEFLATED
            metadata.external_attr = 0o100644 << 16
            archive.writestr(metadata, (ROOT / relative).read_bytes())
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != {p.as_posix() for p in files}:
            raise ValueError('release archive verification failed')
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zip', action='store_true', help='create sanitized source archive under .local')
    args = parser.parse_args()
    try:
        files = audit()
        print(f'release audit: {len(files)} allowed source files')
        if args.zip:
            print(build_zip(files))
        return 0
    except (ValueError, OSError) as exc:
        print(f'release audit: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
