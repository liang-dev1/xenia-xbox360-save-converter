"""Synthetic STFS fixtures. No game data or retail credentials."""

from hashlib import sha1


def donor(*, double=True, header_size=0xA000):
    data = bytearray(header_size + (3 if double else 2) * 0x1000)
    data[:4] = b"CON "
    data[4:6] = (0x1A8).to_bytes(2, "big")
    data[0x340:0x344] = header_size.to_bytes(4, "big")
    data[0x344:0x348] = (1).to_bytes(4, "big")
    data[0x348:0x34C] = (2).to_bytes(4, "big")
    data[0x360:0x364] = (0x544307D5).to_bytes(4, "big")
    data[0x379] = 0x24
    data[0x37B] = 0 if double else 1
    data[0x37C:0x37E] = (1).to_bytes(2, "little")
    data[0x395:0x399] = (1).to_bytes(4, "big")
    table = bytearray(0x1000)
    table[:20] = sha1(bytes(0x1000)).digest()
    table[20] = 0x80
    table[21:24] = b"\xff\xff\xff"
    data[header_size:header_size + 0x1000] = table
    if double:
        data[header_size + 0x1000:header_size + 0x2000] = table
    data[0x381:0x395] = sha1(table).digest()
    data[0x32C:0x340] = sha1(data[0x344:header_size]).digest()
    return bytes(data)
