from pathlib import Path
import tempfile
import unittest
import zipfile

from xsave.xenia import XeniaHeader, XeniaSave, discover, write_save
from xsave.errors import FormatError
from xsave.stfs import StfsPackage

PNG = b'\x89PNG\r\n\x1a\nsynthetic'


class XeniaTest(unittest.TestCase):
    def test_header_basic_and_aggregate_roundtrip(self):
        for size in (0x134, 0x148, 0x14c):
            header = XeniaHeader(1, 1, '章节 / Chapter', 'test.dat', title_id=0x12345678)
            blob = header.to_bytes(size=size)
            self.assertEqual(len(blob), size)
            parsed = XeniaHeader.parse(blob)
            self.assertEqual(parsed.display_name, header.display_name)
            self.assertEqual(parsed.package_name, 'test.dat')
            if size >= 0x148:
                self.assertEqual(parsed.title_id, 0x12345678)
            self.assertEqual(parsed.to_bytes(size=size), blob)

    def test_current_canary_full_sidecar_roundtrip_is_not_stfs(self):
        header = XeniaHeader(1, 1, 'Current Canary', 'save', 0x12345678,
                             kind='canary_full', profile_id=(10).to_bytes(8, 'big'),
                             console_id=b'12345', full_device_id=b'D' * 20,
                             metadata_version=2, thumbnail=PNG)
        blob = header.to_full_bytes()
        self.assertEqual(len(blob), 0xA000)
        parsed = XeniaHeader.parse(blob, package_name_hint='save')
        self.assertEqual(parsed.kind, 'canary_full')
        self.assertEqual(parsed.title_id, 0x12345678)
        self.assertEqual(parsed.profile_id, (10).to_bytes(8, 'big'))
        self.assertEqual(parsed.console_id, b'12345')
        self.assertEqual(parsed.full_device_id, b'D' * 20)
        self.assertEqual(parsed.thumbnail, PNG)
        self.assertEqual(parsed.to_full_bytes(), blob)
        with self.assertRaises(FormatError):
            StfsPackage(blob)

    def test_full_header_preserves_licenses_and_unrounded_sidecar(self):
        from tests.helpers import donor
        data = bytearray(donor())
        data[0x22c:0x23c] = b'\xff' * 8 + bytes(8)
        header = XeniaHeader.from_container(bytes(data), 'save')
        blob = header.to_full_bytes()
        self.assertEqual(blob[0x22c:0x32c], data[0x22c:0x32c])
        self.assertEqual(XeniaHeader.parse(blob[:0x9744]).package_name, 'save')

    def test_hostile_header_rejected(self):
        for name in ('../x', 'a/b', '..', 'CON', 'a\\b'):
            with self.assertRaises(FormatError):
                XeniaHeader(1, 1, 'test', name).to_bytes()
        with self.assertRaises(FormatError):
            XeniaHeader.parse(bytes(18))

    def test_modern_layout_filetree_roundtrip_and_zip_detection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            save = XeniaSave(0x12345678, 1, 10, 'save', 'test',
                             {'file': b'data', 'nested/zero': b''}, {'nested', 'empty'}, PNG)
            write_save(save, root)
            sidecar = root / '000000000000000A/12345678/Headers/00000001/save.header'
            self.assertEqual(sidecar.stat().st_size, 0xA000)
            self.assertFalse((root / '000000000000000A/12345678/00000001/save/__thumbnail.png').exists())
            found = discover(root)
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0].files, save.files)
            self.assertEqual(found[0].directories, save.directories)
            self.assertEqual(found[0].xuid, 10)
            self.assertEqual(found[0].thumbnail, PNG)
            self.assertEqual(found[0].header.kind, 'canary_full')
            archive = root.parent / (root.name + '.zip')
            try:
                with zipfile.ZipFile(archive, 'w') as z:
                    for p in root.rglob('*'):
                        if p.is_file():
                            relative = p.relative_to(root).as_posix().split('/', 1)[1]
                            z.write(p, relative)
                        elif p.is_dir():
                            relative = p.relative_to(root).as_posix().split('/', 1)
                            if len(relative) == 2:
                                z.writestr(relative[1] + '/', b'')
                imported = discover(archive)[0]
                self.assertEqual(imported.files, save.files)
                self.assertEqual(imported.xuid, 10)
                self.assertEqual(imported.thumbnail, PNG)
            finally:
                archive.unlink(missing_ok=True)

    def test_legacy_layout_and_orphan_headers(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            save = XeniaSave(0x12345678, 1, None, 'save', 'test', {'file': b'data'}, set(), PNG)
            write_save(save, root, layout='legacy')
            hdir = root / '12345678/Headers/00000001'
            (hdir / 'missing.header').write_bytes(XeniaHeader(1, 1, 'old', 'missing').to_bytes())
            found = discover(root)
            self.assertEqual(len(found), 1)
            self.assertIsNone(found[0].xuid)
            self.assertEqual(found[0].thumbnail, PNG)

    def test_selected_package_scope_ignores_neighbour_saves(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = XeniaSave(0x12345678, 1, 10, 'first', 'first', {'a': b'1'}, set())
            second = XeniaSave(0x12345678, 1, 10, 'second', 'second', {'b': b'2'}, set())
            package = write_save(first, root)
            write_save(second, root)
            found = discover(package)
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0].package_name, 'first')
            self.assertEqual(found[0].files, {'a': b'1'})

    def test_zip_traversal_and_symlinks_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / 'bad.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('../attack', b'bad')
            with self.assertRaises(FormatError):
                discover(archive)
            with zipfile.ZipFile(archive, 'w') as z:
                info = zipfile.ZipInfo('link')
                info.create_system = 3
                info.external_attr = (0o120777 << 16)
                z.writestr(info, 'target')
            with self.assertRaises(FormatError):
                discover(archive)
