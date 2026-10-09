from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tests.test_converter import template
from xsave.batch import convert_batch
from xsave.cli import main
from xsave.errors import FormatError
from xsave.stfs import build, StfsPackage
from xsave.xenia import XeniaSave, discover, write_save


class BatchTests(unittest.TestCase):
    def make_source(self, root, specs=(('one', 0, 0x12345678), ('two', 0, 0x12345678))):
        source, donor = root / 'source', root / 'template'
        donor.write_bytes(build({'old': b'donor'}, template()))
        for name, xuid, title in specs:
            write_save(XeniaSave(title, 1, xuid, name, name,
                                 {'nested/data': name.encode() + b'\x00\xff'}, {'nested', 'empty'}), source)
        return source, donor

    def test_all_roundtrip_standard_layouts_and_backups(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, donor = self.make_source(root)
            originals = {p: p.read_bytes() for p in source.rglob('*') if p.is_file()}
            before = {s.package_name: s for s in discover(source)}
            xbox = convert_batch('to-xbox', source, root / 'xbox', template=donor, unsigned=True)
            self.assertEqual((xbox['succeeded'], xbox['failed']), (2, 0))
            self.assertEqual(xbox['status'], 'batch_complete')
            for row in xbox['results']:
                output = Path(row['report']['output'])
                self.assertEqual(output.relative_to(root / 'xbox').parts,
                                 ('Content', '0000000000000000', '12345678', '00000001', row['package']))
                package = StfsPackage(output.read_bytes())
                self.assertEqual(package.files, before[row['package']].files)
                self.assertEqual(package.directories, before[row['package']].directories)
                self.assertEqual(row['report']['container']['hash_tree'], 'valid')
            xenia = convert_batch('to-xenia', root / 'xbox', root / 'xenia')
            self.assertEqual(xenia['status'], 'batch_complete')
            returned = discover(root / 'xenia')
            self.assertEqual({s.package_name: s.files for s in returned}, {n: s.files for n, s in before.items()})
            self.assertTrue((root / 'xenia' / '0000000000000000' / '12345678' / 'Headers' / '00000001').is_dir())
            for row in xbox['results'] + xenia['results']:
                with zipfile.ZipFile(row['report']['backup']) as backup:
                    self.assertIsNone(backup.testzip())
            self.assertEqual(originals, {p: p.read_bytes() for p in originals})

    def test_subset_and_legacy_export(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, _ = self.make_source(root, (('one', None, 0x12345678), ('two', None, 0x12345678)))
            report = convert_batch('to-xenia', source, root / 'out', packages=['two'], layout='legacy')
            self.assertEqual(report['succeeded'], 1)
            self.assertEqual([s.package_name for s in discover(root / 'out')], ['two'])
            self.assertTrue((root / 'out' / '12345678' / '00000001' / 'two').is_dir())

    def test_failures_continue_and_cli_preserves_partial_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, donor = self.make_source(root, (('ok', 0, 0x12345678), ('blocked', 1, 0x12345678)))
            stdout, stderr = io.StringIO(), io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = main(['to-xbox', str(source), '--batch', '--template', str(donor),
                             '--unsigned', '--output', str(root / 'out'), '--report', str(root / 'report.json')])
            self.assertEqual(code, 2)
            report = json.loads(stdout.getvalue())
            self.assertEqual(report, json.loads((root / 'report.json').read_text(encoding='utf-8')))
            self.assertEqual((report['succeeded'], report['failed'], report['status']), (1, 1, 'batch_partial'))
            self.assertIn('failed', stderr.getvalue())
            rows = {r['package']: r for r in report['results']}
            self.assertIn('identity', rows['blocked']['error'].lower())
            self.assertTrue(Path(rows['ok']['report']['output']).is_file())
            self.assertFalse((root / 'out' / 'Content' / '0000000000000000' / '12345678' / '00000001' / 'blocked').exists())

    def test_all_failed_does_not_publish_empty_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, donor = self.make_source(root)
            report = convert_batch('to-xbox', source, root / 'out', template=donor)
            self.assertEqual(report['status'], 'batch_failed')
            self.assertEqual(report['failed'], 2)
            self.assertIsNone(report['output'])
            self.assertFalse((root / 'out').exists())

    def test_preflight_rejects_ambiguous_selection_and_wrong_title_without_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, donor = self.make_source(root)
            for selected in (['missing'], ['one', 'one'], []):
                with self.assertRaises(FormatError):
                    convert_batch('to-xbox', source, root / 'out', packages=selected, template=donor, unsigned=True)
            write_save(XeniaSave(0x87654321, 1, 0, 'other-title', 'other', {'data': b'opaque'}, set()), source)
            with self.assertRaisesRegex(FormatError, 'Title'):
                convert_batch('to-xbox', source, root / 'out', template=donor, unsigned=True)
            self.assertFalse((root / 'out').exists())
            self.assertFalse((root / '.xsave-backups').exists())
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, donor = self.make_source(root, (('same', 0, 0x12345678), ('same', 1, 0x12345678)))
            with self.assertRaisesRegex(FormatError, 'ambiguous'):
                convert_batch('to-xbox', source, root / 'out', template=donor, unsigned=True)
            self.assertFalse((root / '.xsave-backups').exists())

    def test_output_and_backup_overlap_rejected_before_any_conversion(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, donor = self.make_source(root)
            for output, backup in ((source / 'new', None), (root / 'out', root / 'out'),
                                   (root / 'out', root / 'out' / 'backup'), (root / 'out', source / 'backup')):
                with self.assertRaises(FormatError):
                    convert_batch('to-xbox', source, output, template=donor, unsigned=True, backup_dir=backup)
                self.assertFalse(output.exists())
            self.assertFalse((root / '.xsave-backups').exists())

    def test_changed_input_between_items_is_rejected(self):
        from xsave.converter import to_xenia
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, _ = self.make_source(root)
            second = next(s for s in discover(source) if s.package_name == 'two')
            data = source / '0000000000000000' / '12345678' / '00000001' / second.package_name / 'nested' / 'data'
            def convert(*args, **kwargs):
                report = to_xenia(*args, **kwargs)
                data.write_bytes(b'changed between batch items')
                return report
            with patch('xsave.batch.to_xenia', side_effect=convert):
                report = convert_batch('to-xenia', source, root / 'out')
            self.assertEqual((report['succeeded'], report['failed']), (1, 1))
            self.assertIn('changed', report['results'][1]['error'])
            self.assertEqual([s.package_name for s in discover(root / 'out')], ['one'])

    def test_staging_failure_never_publishes_partial_item(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, _ = self.make_source(root)
            rename = Path.rename
            def fail_merge(path, target):
                if 'result' in Path(target).parts:
                    raise OSError('simulated staging failure')
                return rename(path, target)
            with patch.object(Path, 'rename', fail_merge):
                with self.assertRaisesRegex(OSError, 'staging failure'):
                    convert_batch('to-xenia', source, root / 'out')
            self.assertFalse((root / 'out').exists())
            self.assertFalse(list(root.glob('.xsave-batch-*')))
