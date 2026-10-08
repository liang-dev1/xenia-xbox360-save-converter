import unittest
from hashlib import sha1

from tests.helpers import donor
from xsave.errors import FormatError
from xsave.stfs import StfsPackage, build


class StfsTests(unittest.TestCase):
    def test_round_trip_nested_empty_and_multiblock(self):
        files = {"A/B": b"x" * 9000, "A/empty": b"", "root": b"z"}
        raw = build(files, donor(), directories={"A", "unused/deeper"})
        parsed = StfsPackage(raw)
        self.assertEqual(parsed.files, files)
        self.assertEqual(parsed.directories, {"A", "unused", "unused/deeper"})
        self.assertEqual(parsed.metadata.title_id, 0x544307D5)
        self.assertTrue(parsed.validate()["structural_valid"])

    def test_multiblock_directory_table_and_invalid_metadata(self):
        files = {f'save{i:03}': bytes([i % 256]) for i in range(130)}
        self.assertEqual(StfsPackage(build(files, donor())).files, files)
        for offset, value in ((0x348, 3), (0x340, 0x9001)):
            raw = bytearray(donor())
            raw[offset:offset + 4] = value.to_bytes(4, 'big')
            raw[0x32c:0x340] = sha1(raw[0x344:0xa000]).digest()
            with self.assertRaises(FormatError):
                StfsPackage(bytes(raw))

    def test_corrupt_data_rejected(self):
        raw = bytearray(build({"one": b"hello"}, donor()))
        parsed = StfsPackage(bytes(raw))
        raw[parsed.data_offset(1)] ^= 1
        with self.assertRaises(FormatError):
            StfsPackage(bytes(raw))

    def test_unsafe_paths_rejected(self):
        with self.assertRaises(FormatError):
            build({"../bad": b"x"}, donor())

    def test_level_one_hash_tree(self):
        payload = bytes(range(256)) * 3000
        raw = build({"large": payload}, donor())
        pkg = StfsPackage(raw)
        self.assertEqual(pkg.files["large"], payload)
        self.assertEqual(int.from_bytes(raw[pkg.base + pkg._table_backing(0, 1) * 0x1000 + 0xFF0:
                                            pkg.base + pkg._table_backing(0, 1) * 0x1000 + 0xFF4], "big"), pkg.count)

    def test_single_hash_table_layout(self):
        payload = b"Q" * 9000
        raw = build({"save": payload}, donor(double=False))
        self.assertEqual(StfsPackage(raw).files["save"], payload)

    def test_level_two_hash_tree(self):
        payload = bytes(0x70E4 * 0x1000)
        raw = build({"large": payload}, donor())
        pkg = StfsPackage(raw)
        self.assertEqual(pkg.files["large"], payload)
        self.assertEqual(int.from_bytes(raw[pkg.base + pkg._table_backing(0, 2) * 0x1000 + 0xFF0:
                                            pkg.base + pkg._table_backing(0, 2) * 0x1000 + 0xFF4], "big"), pkg.count)

    def test_fragmented_chain(self):
        raw = bytearray(build({"a": b"A" * 5000, "b": b"B"}, donor()))
        pkg = StfsPackage(bytes(raw))
        off2, off3 = pkg.data_offset(2), pkg.data_offset(3)
        raw[off2:off2 + 0x1000], raw[off3:off3 + 0x1000] = (
            raw[off3:off3 + 0x1000], raw[off2:off2 + 0x1000])
        raw[pkg.data_offset(0) + 0x40 + 0x2F:pkg.data_offset(0) + 0x40 + 0x32] = b"\x02\0\0"
        raw[pkg.base + 0x18 + 21:pkg.base + 0x18 + 24] = b"\0\0\x03"
        for n in (0, 2, 3):
            digest = sha1(raw[pkg.data_offset(n):pkg.data_offset(n) + 0x1000]).digest()
            for copy in range(2):
                raw[pkg.base + copy * 0x1000 + n * 0x18:pkg.base + copy * 0x1000 + n * 0x18 + 20] = digest
        raw[pkg.base + 0x1000 + 0x18 + 21:pkg.base + 0x1000 + 0x18 + 24] = b"\0\0\x03"
        raw[0x381:0x395] = sha1(raw[pkg.base:pkg.base + 0x1000]).digest()
        raw[0x32C:0x340] = sha1(raw[0x344:pkg.base]).digest()
        self.assertEqual(StfsPackage(bytes(raw)).files, {"a": b"A" * 5000, "b": b"B"})

    def test_case_alias_rejected(self):
        with self.assertRaises(FormatError):
            build({"Save": b"a", "save": b"b"}, donor())
        with self.assertRaises(FormatError):
            build({"Save": b"a", "save/child": b"b"}, donor())

    def test_reserved_allocation_exceeds_valid_blocks(self):
        raw = bytearray(build({"one": b"ok"}, donor()))
        file_entry = 0xC000
        raw[file_entry + 0x2C:file_entry + 0x2F] = b"\x02\0\0"
        table = 0xA000
        digest = sha1(raw[file_entry:file_entry + 0x1000]).digest()
        for copy in range(2):
            raw[table + copy * 0x1000:table + copy * 0x1000 + 20] = digest
        raw[0x381:0x395] = sha1(raw[table:table + 0x1000]).digest()
        raw[0x32C:0x340] = sha1(raw[0x344:0xA000]).digest()
        self.assertEqual(StfsPackage(bytes(raw)).files["one"], b"ok")

    def test_active_secondary_hash_copy(self):
        raw = bytearray(build({"one": b"ok"}, donor()))
        raw[0x37B] |= 2
        raw[0xA000] ^= 1  # Inactive primary may be stale/corrupt.
        raw[0x32C:0x340] = sha1(raw[0x344:0xA000]).digest()
        self.assertEqual(StfsPackage(bytes(raw)).files["one"], b"ok")
        raw[0x37B] &= ~2
        raw[0x32C:0x340] = sha1(raw[0x344:0xA000]).digest()
        with self.assertRaises(FormatError):
            StfsPackage(bytes(raw))

    def test_metadata_v2_names_and_thumbnail(self):
        template = bytearray(donor())
        template[0x348:0x34C] = (2).to_bytes(4, "big")
        template[0x32C:0x340] = sha1(template[0x344:0xA000]).digest()
        out = StfsPackage(build({}, bytes(template), display_name="测试", thumbnail=b"PNG"))
        self.assertEqual(out.metadata.display_name, "测试")
        self.assertEqual(out.thumbnail, b"PNG")
        self.assertEqual(out.data[0x541A:0x541E], "测试".encode("utf-16-be"))


if __name__ == "__main__":
    unittest.main()
