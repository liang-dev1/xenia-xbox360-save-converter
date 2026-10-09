"""Exercise the extracted release EXE using synthetic data only (Windows x64)."""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def window_startup(exe):
    user = ctypes.WinDLL('user32', use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.EnumWindows.argtypes = (callback_type, wintypes.LPARAM)
    user.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    process = subprocess.Popen([str(exe)], cwd=exe.parent)
    found = []

    @callback_type
    def visit(window, _):
        pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(window, ctypes.byref(pid))
        if pid.value == process.pid:
            text = ctypes.create_unicode_buffer(256)
            user.GetWindowTextW(window, text, len(text))
            if 'Xenia' in text.value and 'Save Converter' in text.value:
                found.append(window)
        return True

    try:
        deadline = time.monotonic() + 30
        while not found and process.poll() is None and time.monotonic() < deadline:
            user.EnumWindows(visit, 0)
            time.sleep(0.05)
        if not found:
            raise RuntimeError(f'Frozen Tk window did not appear; exit={process.poll()}')
        user.PostMessageW(found[0], 0x0010, 0, 0)  # Close only our own idle window.
        if process.wait(timeout=10) != 0:
            raise RuntimeError('Frozen GUI did not close normally.')
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)


def main():
    if not __debug__:
        raise SystemExit('Release smoke checks require unoptimized Python; remove -O/PYTHONOPTIMIZE.')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--receipt', required=True, type=Path)
    args = parser.parse_args()
    from cryptography.hazmat.primitives.asymmetric import rsa
    from tests.helpers import donor
    from xsave.signing import ConSigner
    from xsave.stfs import StfsPackage, build
    with tempfile.TemporaryDirectory(dir=ROOT / '.local' / 'tmp', prefix='frozen-') as temp:
        base = Path(temp)
        with zipfile.ZipFile(args.archive) as archive:
            for item in archive.namelist():
                if not item.startswith('XSaveConverter/') or '..' in Path(item).parts or '\\' in item:
                    raise RuntimeError('Unexpected archive entry.')
            archive.extractall(base)
        bundle = base / 'XSaveConverter'
        inventory = json.loads((bundle / 'FILES.json').read_text())
        assert {p.relative_to(bundle).as_posix() for p in bundle.rglob('*') if p.is_file()} == (
            {item['path'] for item in inventory} | {'FILES.json'})
        for item in inventory:
            path = bundle / item['path']
            if path.stat().st_size != item['size'] or hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
                raise RuntimeError(f"Bundle file changed: {item['path']}")
        exe = bundle / 'XSaveConverter.exe'
        window_startup(exe)
        key = rsa.generate_private_key(public_exponent=65537, key_size=1024).private_numbers()
        qwords = lambda number, length: b''.join(number.to_bytes(length, 'big')[i:i+8]
                                                for i in range(length-8, -1, -8))
        kv = bytearray(0x3FF0)
        kv[0x298:0x318] = qwords(key.public_numbers.n, 128)
        kv[0x318:0x358], kv[0x358:0x398] = qwords(key.p, 64), qwords(key.q, 64)
        cert = bytearray(0x1A8)
        cert[:7] = b'\x01\xa8TEST!'
        cert[0x24:0x28] = (65537).to_bytes(4, 'big')
        cert[0x28:0xA8] = qwords(key.public_numbers.n, 128)
        kv[0x9B8:0xB60] = cert
        key_path, source = base / 'synthetic-keyvault', base / 'synthetic-save'
        key_path.write_bytes(kv)
        source.write_bytes(build({'replay': b'Synthetic EXE round trip\x00\xff'}, donor(),
                                signer=ConSigner.from_keyvault(bytes(kv))))
        original = source.read_bytes()
        reports = {}

        def run(name, arguments):
            path = base / f'{name}.json'
            completed = subprocess.run([str(exe), '--cli', *map(str, arguments),
                                        '--report', str(path)], cwd=base, timeout=30)
            if completed.returncode != 0:
                raise RuntimeError(f'Frozen {name} failed: {completed.returncode}')
            reports[name] = json.loads(path.read_text(encoding='utf-8'))
            return reports[name]

        run('inspect', ['inspect', source])
        check = run('verify', ['verify', source, '--game-check'])
        assert check['container']['signature'] == 'valid'
        run('to-xenia', ['to-xenia', source, '--output', base / 'content'])
        for name, flags in (('unsigned', ['--unsigned']), ('signed', ['--keyvault', key_path]), ('preserved', [])):
            report = run(name, ['to-xbox', base / 'content', '--template', source,
                                '--output', base / name, *flags])
            assert StfsPackage((base / name).read_bytes()).files == StfsPackage(original).files
            assert report['container']['signature'] == ('missing' if name == 'unsigned' else 'valid')
        assert (base / 'preserved').read_bytes() == original
        assert source.read_bytes() == original
        failed = subprocess.run([str(exe), '--cli', 'inspect', str(base / 'missing'),
                                 '--report', str(base / 'error.json')], cwd=base,
                                capture_output=True, timeout=30)
        assert failed.returncode == 2 and b'xsave:' in failed.stderr
        assert not (base / 'error.json').exists()
        for name in ('to-xenia', 'unsigned', 'signed', 'preserved'):
            with zipfile.ZipFile(reports[name]['backup']) as backup:
                assert backup.testzip() is None
        report = {'archive_sha256': hashlib.sha256(args.archive.read_bytes()).hexdigest(),
                  'frozen_tk_startup_and_close': 'passed', 'reports': reports,
                  'frozen_failure_stderr': 'passed',
                  'round_trip_file_equality': True, 'original_unchanged': True,
                  'synthetic_signing_only': True, 'runtime_or_console_game_load': 'not_tested'}
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('Frozen EXE: Tk startup, inspect, verify, both directions, all three signing modes passed.')


if __name__ == '__main__':
    main()
