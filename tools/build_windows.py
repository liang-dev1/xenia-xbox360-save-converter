"""Build a portable Windows x64 GUI ZIP with dependency notices and file hashes."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    if os.name != 'nt' or platform.machine().lower() not in ('amd64', 'x86_64'):
        raise SystemExit('Build on Windows x64 with a clean virtual environment.')
    if sys.prefix == sys.base_prefix:
        raise SystemExit('Use a clean release virtual environment, not system Python.')
    config = (Path(sys.prefix) / 'pyvenv.cfg').read_text().lower()
    if 'include-system-site-packages = false' not in config:
        raise SystemExit('System-site-packages must be disabled.')
    packages = {}
    for requirement in ('requirements-build.txt', 'requirements-signing.txt'):
        for line in (ROOT / requirement).read_text().splitlines():
            if not line.strip() or line.startswith('#'):
                continue
            name, version = line.strip().split('==')
            if importlib.metadata.version(name) != version:
                raise SystemExit(f'Install the pinned version of {name}: {version}')
            packages[name] = version
    version = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']['version']
    destination = ROOT / '.local' / 'windows' / version
    bundle = destination / 'dist' / 'XSaveConverter'
    archive = destination / f'xsave-windows-x64-{version}.zip'
    if bundle.exists() or archive.exists():
        raise SystemExit(f'Refuse to overwrite an existing build: {destination}')
    destination.mkdir(parents=True, exist_ok=True)
    os.environ['TMP'] = os.environ['TEMP'] = str(ROOT / '.local' / 'tmp')
    Path(os.environ['TMP']).mkdir(parents=True, exist_ok=True)
    command = [sys.executable, '-m', 'PyInstaller', '--clean', '--onedir', '--windowed',
               '--name', 'XSaveConverter', '--paths', str(ROOT),
               '--distpath', str(destination / 'dist'), '--workpath', str(destination / 'work'),
               '--specpath', str(destination)]
    # The upstream cryptography hook includes its Rust/CFFI backend and metadata.
    command.append(str(ROOT / 'tools' / 'gui_launcher.py'))
    with (destination / 'build.log').open('w', encoding='utf-8') as log:
        subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
    subprocess.run([sys.executable, str(ROOT / 'tools' / 'binary_notices.py'),
                    '--output', str(bundle / 'THIRD_PARTY')], cwd=ROOT, check=True)
    shutil.copyfile(ROOT / 'LICENSE', bundle / 'LICENSE')
    shutil.copyfile(ROOT / 'docs' / 'GUI.md', bundle / 'README.md')
    from cryptography.hazmat.backends.openssl.backend import backend
    build = {'project_version': version, 'python': sys.version, 'platform': platform.platform(),
             'packages': packages, 'crypto_openssl': backend.openssl_version_text(),
             'expected_wheel_inputs': json.loads((ROOT / 'docs' / 'DEPENDENCIES.json').read_text())['windows_release']['build_inputs'],
             'wheel_provenance': 'Expected official wheel pins; this builder checks versions, not installed wheel bytes. Use --require-hashes.',
             'source': f'https://github.com/liang-dev1/xenia-xbox360-save-converter/tree/v{version}',
             'authenticode_signed': False}
    (bundle / 'BUILD.json').write_text(json.dumps(build, indent=2) + '\n', encoding='utf-8')
    files = sorted(p for p in bundle.rglob('*') if p.is_file())
    inventory = [{'path': p.relative_to(bundle).as_posix(), 'size': p.stat().st_size,
                  'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]
    (bundle / 'FILES.json').write_text(json.dumps(inventory, indent=2) + '\n', encoding='utf-8')
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as output:
        for path in sorted(p for p in bundle.rglob('*') if p.is_file()):
            output.write(path, path.relative_to(bundle.parent).as_posix())
    with zipfile.ZipFile(archive) as output:
        if output.testzip() is not None:
            raise SystemExit('Archive integrity check failed.')
    print(json.dumps({'archive': str(archive), 'size': archive.stat().st_size,
                      'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}, indent=2))


if __name__ == '__main__':
    main()
