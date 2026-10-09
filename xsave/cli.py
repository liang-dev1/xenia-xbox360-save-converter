"""Command-line entry point. Reports describe structural evidence, not console acceptance."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
import zipfile

from .adapters import adapt
from .batch import convert_batch
from .converter import to_xbox, to_xenia
from .errors import FormatError
from .paths import is_link, read_file
from .signing import ConSigner
from .stfs import StfsPackage
from .xenia import discover


def _hex(value: str, digits: int) -> int:
    if len(value) != digits or any(c not in '0123456789abcdefABCDEF' for c in value):
        raise argparse.ArgumentTypeError(f'expected exactly {digits} hexadecimal digits')
    return int(value, 16)


def _id8(value: str) -> int:
    return _hex(value, 8)


def _id16(value: str) -> int:
    return _hex(value, 16)


def _bytes8(value: str) -> bytes:
    return _id16(value).to_bytes(8, 'big')


def _bytes20(value: str) -> bytes:
    return _hex(value, 40).to_bytes(20, 'big')


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='xsave', description='Inspect and convert Xenia/Xbox 360 saves')
    commands = parser.add_subparsers(dest='command', required=True)
    inspect = commands.add_parser('inspect', help='identify packages and metadata')
    inspect.add_argument('input', type=Path)
    inspect.add_argument('--title-id', type=_id8)
    inspect.add_argument('--source-xuid', type=_id16)
    inspect.add_argument('--report', type=Path)
    verify = commands.add_parser('verify', help='validate container/file tree and optional game payload')
    verify.add_argument('input', type=Path)
    verify.add_argument('--title-id', type=_id8)
    verify.add_argument('--source-xuid', type=_id16)
    verify.add_argument('--game-check', action='store_true')
    verify.add_argument('--report', type=Path)
    xbox = commands.add_parser('to-xbox', help='build a same-title donor-based CON')
    xbox.add_argument('input', type=Path)
    xbox.add_argument('--template', required=True, type=Path, help='same-title retail CON donor')
    xbox.add_argument('--output', required=True, type=Path)
    xbox.add_argument('--package', action='append')
    xbox.add_argument('--batch', action='store_true', help='convert all or repeatedly selected packages into a new directory')
    xbox.add_argument('--title-id', type=_id8)
    xbox.add_argument('--source-xuid', type=_id16)
    xbox.add_argument('--profile-id', type=_bytes8)
    xbox.add_argument('--device-id', type=_bytes20)
    method = xbox.add_mutually_exclusive_group()
    method.add_argument('--keyvault', type=Path, help='caller-supplied decrypted KeyVault; never copied into backups')
    method.add_argument('--unsigned', action='store_true', help='create a non-retail unsigned draft')
    xbox.add_argument('--allow-unsafe', action='store_true', help='permit unverified game-level rebinding')
    xbox.add_argument('--backup-dir', type=Path)
    xbox.add_argument('--report', type=Path)
    xenia = commands.add_parser('to-xenia', help='export an extracted Xenia content tree')
    xenia.add_argument('input', type=Path)
    xenia.add_argument('--output', required=True, type=Path)
    xenia.add_argument('--xuid', type=_id16, help='target Xenia profile XUID')
    xenia.add_argument('--layout', choices=('canary', 'legacy'), default='canary')
    xenia.add_argument('--package', action='append')
    xenia.add_argument('--batch', action='store_true', help='merge all or repeatedly selected packages into a new content root')
    xenia.add_argument('--title-id', type=_id8)
    xenia.add_argument('--source-xuid', type=_id16)
    xenia.add_argument('--allow-unsafe', action='store_true')
    xenia.add_argument('--backup-dir', type=Path)
    xenia.add_argument('--report', type=Path)
    return parser


def _report_target(path: Path | None, sources: tuple[Path, ...]) -> Path | None:
    if path is None:
        return None
    target = path.absolute()
    if target.exists() or target.is_symlink():
        raise FormatError('Refuse to overwrite an existing report')
    if any(is_link(parent) for parent in (target.parent, *target.parents)):
        raise FormatError('Report path must not traverse links/junctions')
    resolved = target.resolve()
    for source in sources:
        source = source.resolve()
        if resolved == source or resolved.is_relative_to(source) or source.is_relative_to(resolved):
            raise FormatError('Report must not overlap an input or output')
    return target


def _read_file(path: Path) -> bytes:
    return read_file(path)


def _inspect(path: Path, title_id: int | None, source_xuid: int | None,
             game_check: bool = False) -> dict:
    saves = discover(path, title_id=title_id, xuid=source_xuid)
    packages = []
    for save in saves:
        item = {'title_id': f'{save.title_id:08X}', 'content_type': f'{save.content_type:08X}',
                'package': save.package_name, 'xuid': f'{save.xuid:016X}' if save.xuid is not None else None,
                'files': len(save.files), 'directories': len(save.directories),
                'file_sha256': {name: sha256(blob).hexdigest() for name, blob in sorted(save.files.items())},
                'xenia_header': save.header.kind if save.header else None,
                'warnings': save.warnings}
        if game_check:
            result = adapt(save.title_id, save.files, save.xuid, save.xuid)
            item['payload_integrity'] = 'checked' if result.checked else 'unknown'
            item['adapter'] = result.adapter
            item['warnings'] = sorted(set(item['warnings'] + result.warnings))
        packages.append(item)
    report = {'source': str(path.absolute()), 'packages': packages,
              'xenia_runtime_test': 'not_tested', 'retail_console_test': 'not_tested'}
    if path.is_file():
        with path.open('rb') as stream:
            magic = stream.read(4)
        if magic in (b'CON ', b'LIVE', b'PIRS'):
            package = StfsPackage(_read_file(path))
            report['container'] = package.validate()
            report['container'].update(magic=package.magic.decode('ascii'),
                                       profile_id=package.metadata.profile_id.hex().upper(),
                                       device_id=package.metadata.device_id.hex().upper(),
                                       console_id=package.metadata.console_id.hex().upper())
        elif magic[:2] == b'PK':
            report['container'] = {'format': 'xsave_zip', 'file_tree': 'valid'}
        else:
            report['container'] = {'format': 'extracted_xenia', 'file_tree': 'valid'}
    else:
        report['container'] = {'format': 'extracted_xenia', 'file_tree': 'valid'}
    return report


def _run(args: argparse.Namespace) -> dict:
    if args.command in ('inspect', 'verify'):
        return _inspect(args.input, args.title_id, args.source_xuid,
                        game_check=args.command == 'verify' and args.game_check)
    if not args.batch and args.package and len(args.package) > 1:
        raise FormatError('Use --batch for multiple --package values')
    common = dict(title_id=args.title_id, source_xuid=args.source_xuid,
                  allow_unsafe=args.allow_unsafe, backup_dir=args.backup_dir)
    selection = args.package if args.batch else args.package[0] if args.package else None
    if args.command == 'to-xbox':
        signer = None
        if args.keyvault is not None:
            key_path = args.keyvault.resolve()
            if args.input.is_dir() and key_path.is_relative_to(args.input.resolve()):
                raise FormatError('Signing material must be outside the backed-up input tree')
            key = _read_file(args.keyvault)
            signer = ConSigner.from_keyvault(key)
        options = dict(template=args.template, profile_id=args.profile_id, device_id=args.device_id,
                       signer=signer, unsigned=args.unsigned, **common)
        if args.batch:
            return convert_batch(args.command, args.input, args.output, packages=selection, **options)
        return to_xbox(args.input, output=args.output, package=selection, **options)
    if args.batch:
        return convert_batch(args.command, args.input, args.output, packages=selection,
                             xuid=args.xuid, layout=args.layout, **common)
    return to_xenia(args.input, args.output, xuid=args.xuid, layout=args.layout,
                    package=selection, **common)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        sources = (args.input,)
        if args.command == 'to-xbox':
            sources += (args.template, args.output)
        elif args.command == 'to-xenia':
            sources += (args.output,)
        report_path = _report_target(args.report, sources)
        report = _run(args)
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + '\n'
        if report_path is not None:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            with report_path.open('x', encoding='utf-8') as stream:
                stream.write(encoded)
        sys.stdout.write(encoded)
        if report.get('failed'):
            sys.stderr.write(f"xsave: batch has {report['failed']} failed package(s); inspect the JSON report\n")
            return 2
        return 0
    except (FormatError, OSError, zipfile.BadZipFile, UnicodeError) as exc:
        sys.stderr.write(f'xsave: {exc}\n')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
