import struct
import unittest

from xsave.adapters import adapt
from xsave.errors import FormatError


def payload(size, check_offset, identity=0):
    data = bytearray(size)
    if size == 2048:
        data[:8] = identity.to_bytes(8, 'big')
        data[8:16] = 'Test'.encode('utf-16-be')
    else:
        data[:32] = bytes.fromhex('0000788000000006000000000123456701000000012345670000000000000000')
    total = sum(struct.unpack(f'>{check_offset // 4}I', data[:check_offset])) & 0xffffffff
    data[check_offset:check_offset + 4] = total.to_bytes(4, 'big')
    return bytes(data)


class AdaptersTest(unittest.TestCase):
    def test_opaque_same_identity_preserves_every_byte(self):
        files = {'a': b'opaque', 'nested/b': b'\0\xff'}
        result = adapt(0x12345678, files, 10, 10)
        self.assertEqual(files, result.files)
        self.assertFalse(result.checked)
        self.assertIn('opaque_payload', result.warnings)

    def test_unknown_identity_change_requires_acknowledgement(self):
        with self.assertRaises(FormatError):
            adapt(0x12345678, {'a': b'opaque'}, 10, 11)
        result = adapt(0x12345678, {'a': b'opaque'}, 10, 11, allow_unsafe=True)
        self.assertEqual(result.files['a'], b'opaque')
        self.assertIn('unsafe_identity_change', result.warnings)

    def test_ngii_rebinds_system_and_recalculates_checksum(self):
        raw = payload(2048, 0x768, 10)
        story = payload(31744, 0x7880)
        result = adapt(0x544307D5, {'ng2sysd.dat': raw, 'ng2stryd00.dat': story}, 10, 11)
        data = result.files['ng2sysd.dat']
        self.assertEqual(data[:8], (11).to_bytes(8, 'big'))
        self.assertEqual(data[8:0x768], raw[8:0x768])
        self.assertEqual(data[0x76c:], raw[0x76c:])
        self.assertEqual(result.files['ng2stryd00.dat'], story)
        self.assertTrue(result.checked)
        self.assertEqual(adapt(0x544307D5, result.files, 11, 10).files['ng2sysd.dat'], raw)

    def test_ngii_bad_checksum_and_bad_version_rejected(self):
        data = bytearray(payload(31744, 0x7880))
        data[100] ^= 1
        with self.assertRaises(FormatError):
            adapt(0x544307D5, {'ng2stryd00.dat': bytes(data)}, None, None)
        data = bytearray(payload(31744, 0x7880))
        data[7] = 7
        with self.assertRaises(FormatError):
            adapt(0x544307D5, {'ng2stryd00.dat': bytes(data)}, None, None)

    def test_ngii_preserves_embedded_xuid_when_outer_identity_unchanged(self):
        raw = payload(2048, 0x768, 11)
        result = adapt(0x544307D5, {'ng2sysd.dat': raw}, 10, 10)
        self.assertEqual(result.files['ng2sysd.dat'], raw)
        self.assertTrue(result.checked)
        self.assertIn('source_system_xuid_differs_from_container_identity', result.warnings)

    def test_ngii_replay_is_not_claimed_as_checked(self):
        result = adapt(0x544307D5, {'replay': b'unknown'}, 10, 10)
        self.assertFalse(result.checked)
        with self.assertRaises(FormatError):
            adapt(0x544307D5, {'replay': b'unknown'}, 10, 11)
