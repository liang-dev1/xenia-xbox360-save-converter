import contextlib
from hashlib import sha1
import io
import json
from pathlib import Path
import tempfile
import unittest

from tests.helpers import donor
from xsave.cli import main
from xsave.stfs import StfsPackage, build
from xsave.xenia import XeniaSave, discover, write_save


def template():
    data = bytearray(donor())
    data[0x360:0x364] = (0x12345678).to_bytes(4, 'big')
    data[0x348:0x34c] = (2).to_bytes(4, 'big')
    data[0x32c:0x340] = sha1(data[0x344:0xa000]).digest()
    return bytes(data)


def call(*arguments):
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main(list(map(str, arguments)))
    return code, stdout.getvalue(), stderr.getvalue()


class CliTests(unittest.TestCase):
    def test_inspect_verify_and_bidirectional_draft(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            donor_path = root / 'donor'
            donor_path.write_bytes(build({'old': b'old'}, template()))
            source = root / 'source'
            payload = {'nested/data': b'progress' * 700}
            write_save(XeniaSave(0x12345678, 1, 0, 'save', 'save', payload, {'nested'}), source)
            code, output, error = call('inspect', source)
            self.assertEqual((code, error), (0, ''))
            self.assertEqual(json.loads(output)['packages'][0]['title_id'], '12345678')
            converted = root / 'converted'
            code, output, error = call('to-xbox', source, '--template', donor_path,
                                       '--output', converted, '--unsigned')
            self.assertEqual((code, error), (0, ''))
            report = json.loads(output)
            self.assertEqual(report['status'], 'unsigned_draft')
            self.assertEqual(StfsPackage(converted.read_bytes()).files, payload)
            self.assertTrue(Path(report['backup']).is_file())
            code, output, error = call('verify', converted)
            self.assertEqual((code, error), (0, ''))
            self.assertEqual(json.loads(output)['container']['hash_tree'], 'valid')
            exported = root / 'export'
            code, output, error = call('to-xenia', converted, '--output', exported)
            self.assertEqual((code, error), (0, ''))
            self.assertEqual(discover(exported)[0].files, payload)

    def test_errors_and_report_overlap(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'invalid'
            source.write_bytes(b'not a package')
            code, output, error = call('inspect', source)
            self.assertEqual(code, 2)
            self.assertEqual(output, '')
            self.assertNotIn('Traceback', error)
            code, output, error = call('to-xenia', source, '--output', root / 'new',
                                       '--report', source)
            self.assertEqual(code, 2)
            self.assertEqual(source.read_bytes(), b'not a package')
            self.assertFalse((root / 'new').exists())
            with self.assertRaises(SystemExit) as invalid:
                call('inspect', source, '--title-id', 'xyz')
            self.assertEqual(invalid.exception.code, 2)

    def test_keyvault_inside_input_is_not_backed_up(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'source'
            source.mkdir()
            key = source / 'KeyVault'
            key.write_bytes(b'not a real key')
            code, _, error = call('to-xbox', source, '--template', root / 'donor',
                                   '--output', root / 'new', '--keyvault', key)
            self.assertEqual(code, 2)
            self.assertIn('outside the backed-up input tree', error)
            self.assertFalse((root / '.xsave-backups').exists())


if __name__ == '__main__':
    unittest.main()
