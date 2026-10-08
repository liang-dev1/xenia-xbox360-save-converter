"""CON content RSA verification and explicit decrypted-KeyVault signing.

Mathematical content signature validity does not establish Microsoft's trust
in the certificate, the target console, or game-level payload acceptance.
"""

from __future__ import annotations

from .errors import FormatError


def _qword_order(value: bytes) -> bytes:
    if len(value) % 8:
        raise FormatError("invalid Xbox RSA integer length")
    return b"".join(value[i:i + 8] for i in range(len(value) - 8, -1, -8))


def _public(data: bytes):
    from cryptography.hazmat.primitives.asymmetric import rsa

    cert = data[4:0x1AC]
    if len(cert) != 0x1A8 or cert[:2] != b"\x01\xA8":
        raise FormatError("missing CON certificate")
    exponent = int.from_bytes(cert[0x24:0x28], "big")
    modulus = int.from_bytes(_qword_order(cert[0x28:0xA8]), "big")
    if exponent < 3 or exponent % 2 == 0 or modulus.bit_length() != 1024:
        raise FormatError("invalid CON certificate public key")
    return rsa.RSAPublicNumbers(exponent, modulus).public_key()


def verify_con_signature(data: bytes) -> str:
    """Return valid/invalid/missing/unsupported/unavailable for content RSA only."""
    if data[:4] != b"CON ":
        return "unsupported"
    if len(data) < 0x344:
        return "invalid"
    signature = data[0x1AC:0x22C]
    if not any(signature):
        return "missing"
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding

        _public(data).verify(signature[::-1], data[0x22C:0x344], padding.PKCS1v15(), hashes.SHA1())
    except ImportError:
        return "unavailable"
    except (FormatError, InvalidSignature, ValueError):
        return "invalid"
    return "valid"


class ConSigner:
    def __init__(self, certificate: bytes, private_key):
        self.certificate = certificate
        self.private_key = private_key

    @classmethod
    def from_keyvault(cls, data: bytes) -> "ConSigner":
        """Load a decrypted 0x3ff0/0x4000 KeyVault supplied by the caller."""
        if len(data) not in (0x3FF0, 0x4000):
            raise FormatError("expected decrypted Xbox 360 KeyVault")
        try:
            from cryptography.hazmat.primitives.asymmetric import rsa
        except ImportError as exc:
            raise FormatError("cryptography is required for CON signing") from exc

        base = 0x10 if len(data) == 0x4000 else 0
        integer = lambda offset, length: int.from_bytes(_qword_order(data[base + offset:base + offset + length]), "big")
        n, p, q = integer(0x298, 0x80), integer(0x318, 0x40), integer(0x358, 0x40)
        certificate = data[base + 0x9B8:base + 0x9B8 + 0x1A8]
        try:
            public = _public(b"CON " + certificate)
            numbers = public.public_numbers()
            if not p or not q or p * q != n or n != numbers.n:
                raise FormatError("KeyVault key does not match certificate")
            e = numbers.e
            from math import lcm

            d = pow(e, -1, lcm(p - 1, q - 1))
            key = rsa.RSAPrivateNumbers(p=p, q=q, d=d, dmp1=d % (p - 1),
                                        dmq1=d % (q - 1), iqmp=pow(q, -1, p),
                                        public_numbers=numbers).private_key()
        except (ValueError, TypeError) as exc:
            raise FormatError("invalid KeyVault RSA material") from exc
        return cls(certificate, key)

    def sign(self, blob: bytearray) -> None:
        if blob[:4] != b"CON " or len(blob) < 0x344:
            raise FormatError("CON package required for signing")
        try:
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import padding
        except ImportError as exc:
            raise FormatError("cryptography is required for CON signing") from exc

        blob[4:0x1AC] = self.certificate
        blob[0x36C:0x371] = self.certificate[2:7]
        blob[0x32C:0x340] = __import__("hashlib").sha1(blob[0x344:((int.from_bytes(blob[0x340:0x344], "big") + 0xFFF) & ~0xFFF)]).digest()
        signature = self.private_key.sign(bytes(blob[0x22C:0x344]), padding.PKCS1v15(), hashes.SHA1())
        blob[0x1AC:0x22C] = signature[::-1]
