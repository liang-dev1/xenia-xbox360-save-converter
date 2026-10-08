import tempfile
import unittest
from unittest.mock import patch
from importlib.util import find_spec
from pathlib import Path

from tests.helpers import donor as synthetic_donor
from hashlib import sha1
from xsave.errors import FormatError
from xsave.stfs import StfsPackage, build
from xsave.xenia import XeniaSave, discover, write_save
from xsave.converter import to_xbox, to_xenia
from xsave.signing import ConSigner


def template():
    data = bytearray(synthetic_donor())
    data[0x360:0x364] = (0x12345678).to_bytes(4, 'big')
    data[0x32c:0x340] = sha1(data[0x344:0xa000]).digest()
    return bytes(data)


class ConverterTests(unittest.TestCase):
    def test_bidirectional_and_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            donor = root / 'donor'
            donor.write_bytes(build({'old': b'old'}, template()))
            source = root / 'source'
            original = {'nested/data': b'progress' * 700, 'empty': b''}
            save = XeniaSave(0x12345678, 1, 0, 'save', 'save', original, {'nested'})
            write_save(save, source)
            report = to_xbox(source, donor, root / 'converted', unsigned=True)
            self.assertEqual(report['status'], 'unsigned_draft')
            self.assertEqual(StfsPackage((root / 'converted').read_bytes()).files, original)
            self.assertTrue(Path(report['backup']).is_file())
            report = to_xenia(root / 'converted', root / 'export')
            self.assertEqual(discover(root / 'export')[0].files, original)
            self.assertEqual(report['file_provenance']['nested/data']['changed'], False)

    def test_requires_signing_or_explicit_draft(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            donor = root / 'donor'
            donor.write_bytes(build({'a': b'old'}, template()))
            source = root / 'source'
            write_save(XeniaSave(0x12345678, 1, 0, 'save', 'save', {'a': b'new'}, set()), source)
            with self.assertRaises(FormatError):
                to_xbox(source, donor, root / 'output')
            self.assertFalse((root / 'output').exists())

    def test_overlap_and_existing_output_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            donor = root / 'donor'
            donor.write_bytes(build({'a': b'old'}, template()))
            with self.assertRaises(FormatError):
                to_xenia(donor, donor)
            folder = root / 'existing'
            folder.mkdir()
            with self.assertRaises(FormatError):
                to_xenia(donor, folder)

    def test_title_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            donor = root / 'donor'
            donor.write_bytes(build({'a': b'old'}, template()))
            source = root / 'source'
            write_save(XeniaSave(0x87654321, 1, 0, 'save', 'save', {'a': b'new'}, set()), source)
            with self.assertRaises(FormatError):
                to_xbox(source, donor, root / 'output', unsigned=True)

    def test_changed_input_after_backup_aborts(self):
        from xsave.converter import backup
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            donor = root / 'donor'
            donor.write_bytes(build({'a': b'old'}, template()))
            source = root / 'source'
            package = write_save(XeniaSave(0x12345678, 1, 0, 'save', '', {'a': b'new'}, set()), source)
            def changed(inputs, directory):
                snapshot = backup(inputs, directory)
                (package / 'a').write_bytes(b'changed')
                return snapshot
            with patch('xsave.converter.backup', side_effect=changed):
                with self.assertRaisesRegex(FormatError, 'changed during backup'):
                    to_xbox(source, donor, root / 'output', unsigned=True)
            self.assertFalse((root / 'output').exists())

    @unittest.skipUnless(find_spec('cryptography'), 'optional signing dependency')
    def test_signed_and_unchanged_donor_modes(self):
        from cryptography.hazmat.primitives.asymmetric import rsa
        key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
        numbers = key.public_key().public_numbers()
        cert = bytearray(0x1a8)
        cert[:2] = b'\x01\xa8'
        cert[2:7] = b'TEST!'
        cert[0x24:0x28] = numbers.e.to_bytes(4, 'big')
        modulus = numbers.n.to_bytes(128, 'big')
        cert[0x28:0xa8] = b''.join(modulus[i:i + 8] for i in range(120, -1, -8))
        signer = ConSigner(bytes(cert), key)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            donor = root / 'donor'
            donor.write_bytes(build({'a': b'old'}, template(), signer=signer))
            source = root / 'source'
            write_save(XeniaSave(0x12345678, 1, 0, 'save', '', {'a': b'new'}, set()), source)
            report = to_xbox(source, donor, root / 'signed', signer=signer)
            self.assertEqual(report['container']['signature'], 'valid')
            self.assertEqual(report['certificate_issuer_trust'], 'not_verified')
            to_xenia(root / 'signed', root / 'export')
            report = to_xbox(root / 'export', root / 'signed', root / 'preserved')
            self.assertEqual(report['status'], 'preserved_donor_signature')
            self.assertEqual((root / 'preserved').read_bytes(), (root / 'signed').read_bytes())

