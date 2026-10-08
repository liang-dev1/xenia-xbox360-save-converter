import unittest
from importlib.util import find_spec

from tests.helpers import donor
from xsave.errors import FormatError
from xsave.signing import ConSigner, verify_con_signature
from xsave.stfs import build, StfsPackage


class SigningTests(unittest.TestCase):
    def test_unsigned_status_and_invalid_material(self):
        self.assertEqual(verify_con_signature(donor()), "missing")
        with self.assertRaises(FormatError):
            ConSigner.from_keyvault(b"bad")

    @unittest.skipUnless(find_spec("cryptography"), "cryptography unavailable")
    def test_synthetic_keyvault_sign_and_mutation(self):
        from cryptography.hazmat.primitives.asymmetric import rsa

        key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
        values = key.private_numbers()
        qwords = lambda n, length: b"".join(
            n.to_bytes(length, "big")[i:i + 8]
            for i in range(length - 8, -1, -8))
        kv = bytearray(0x3FF0)
        kv[0x298:0x318] = qwords(values.public_numbers.n, 128)
        kv[0x318:0x358] = qwords(values.p, 64)
        kv[0x358:0x398] = qwords(values.q, 64)
        cert = bytearray(0x1A8)
        cert[:2] = b"\x01\xA8"
        cert[2:7] = b"TEST!"
        cert[0x24:0x28] = (65537).to_bytes(4, "big")
        cert[0x28:0xA8] = qwords(values.public_numbers.n, 128)
        kv[0x9B8:0xB60] = cert
        signer = ConSigner.from_keyvault(bytes(kv))
        output = build({"save": b"signed"}, donor(), signer=signer)
        self.assertEqual(verify_con_signature(output), "valid")
        self.assertEqual(StfsPackage(output).files["save"], b"signed")
        changed = bytearray(output)
        changed[0x22C] ^= 1
        self.assertEqual(verify_con_signature(changed), "invalid")


if __name__ == "__main__":
    unittest.main()
