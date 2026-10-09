from pathlib import Path
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from tests.helpers import donor
from xsave.errors import FormatError
from xsave.stfs import build, StfsPackage
from xsave.gui import Application, arguments, run_command, summary


class GuiTests(unittest.TestCase):
    def test_command_arguments_keep_explicit_signing_and_identity(self):
        values = {'input': 'source', 'output': 'new', 'template': 'donor',
                  'method': 'unsigned', 'package': 'save', 'source_xuid': '000000000000000A'}
        argv = arguments('to-xbox', values)
        self.assertIn('--unsigned', argv)
        self.assertIn('--source-xuid', argv)
        values.update(method='keyvault', keyvault='private-key')
        argv = arguments('to-xbox', values)
        self.assertNotIn('--unsigned', argv)
        self.assertEqual(argv[argv.index('--keyvault') + 1], 'private-key')
        values['method'] = 'preserve'
        self.assertNotIn('--keyvault', arguments('to-xbox', values))
        for mode in ('inspect', 'verify', 'to-xenia'):
            argv = arguments(mode, values)
            self.assertNotIn('--keyvault', argv)
            self.assertNotIn('--unsigned', argv)
            self.assertNotIn('--template', argv)

    def test_error_and_summary_do_not_claim_console_acceptance(self):
        with self.assertRaises(FormatError):
            run_command(['inspect', 'missing', '--title-id', 'not-hex'])
        self.assertIn('零售', summary({'status': 'unsigned_draft'}))
        self.assertIn('真机', summary({'status': 'signed_needs_console_test'}))
        self.assertIn('未验证', summary({'status': 'xenia_export_needs_runtime_test'}))

    def test_gui_runner_uses_cli_data_and_report_safety(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'save'
            source.write_bytes(build({'replay': b'opaque synthetic'}, donor()))
            report = run_command(['inspect', str(source)])
            self.assertEqual(report['packages'][0]['title_id'], '544307D5')
            with self.assertRaises(FormatError):
                run_command(['inspect', str(source), '--report', str(source)])
            self.assertEqual(StfsPackage(source.read_bytes()).files['replay'], b'opaque synthetic')

    def test_windowed_launcher_cli_requires_safe_report(self):
        launcher = Path(__file__).resolve().parents[1] / 'tools' / 'gui_launcher.py'
        environment = os.environ | {'PYTHONPATH': str(launcher.parents[1])}
        with tempfile.TemporaryDirectory() as temp:
            source, report = Path(temp) / 'save', Path(temp) / 'report.json'
            source.write_bytes(build({'replay': b'launcher synthetic'}, donor()))
            command = [sys.executable, str(launcher), '--cli', 'inspect', str(source)]
            failed = subprocess.run(command, env=environment, capture_output=True)
            self.assertEqual(failed.returncode, 2)
            self.assertIn(b'requires a new --report', failed.stderr)
            self.assertEqual(subprocess.run(command + ['--report', str(report)], env=environment).returncode, 0)
            self.assertTrue(report.is_file())
            original = source.read_bytes()
            self.assertEqual(subprocess.run(command + ['--report', str(source)], env=environment).returncode, 2)
            self.assertEqual(source.read_bytes(), original)

    def test_report_failure_keeps_root_cause_and_explains_created_output(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / 'new-save'

            def fail_report(_):
                destination.write_bytes(b'synthetic output')
                sys.stderr.write('xsave: report permission denied\n')
                return 2

            with patch('xsave.gui.cli_main', side_effect=fail_report):
                with self.assertRaises(FormatError) as error:
                    run_command(['to-xbox', 'source', '--output', str(destination)])
            self.assertIn('report permission denied', str(error.exception))
            self.assertIn('输出路径已产生', str(error.exception))

    def test_native_window_async_roundtrip_and_close_guard(self):
        try:
            import tkinter as tk
        except ImportError as exc:
            self.skipTest(f'Tk display unavailable: {exc}')
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f'Tk display unavailable: {exc}')
        root.withdraw()
        app = Application(root)
        try:
            with tempfile.TemporaryDirectory() as temp:
                base = Path(temp)
                source = base / 'save'
                source.write_bytes(build({'replay': b'opaque synthetic'}, donor()))
                original = source.read_bytes()
                for mode, input_path, output in (
                    ('inspect', source, None), ('verify', source, None),
                    ('to-xenia', source, base / 'content'),
                    ('to-xbox', base / 'content', base / 'rebuilt'),
                ):
                    app.mode.set(mode)
                    app.values['input'].set(str(input_path))
                    app.values['output'].set(str(output) if output else '')
                    app.values['template'].set(str(source))
                    app.values['method'].set('unsigned')
                    app.apply_mode()
                    app.start()
                    self.assertTrue(app.busy)
                    with patch('tkinter.messagebox.showwarning') as warning:
                        app.close()
                        warning.assert_called_once()
                    deadline = time.monotonic() + 15
                    while app.busy and time.monotonic() < deadline:
                        root.update()
                        time.sleep(0.01)
                    self.assertFalse(app.busy)
                    self.assertIsNotNone(app.report)
                    self.assertEqual(app.error, '')
                self.assertEqual(StfsPackage((base / 'rebuilt').read_bytes()).files,
                                 StfsPackage(original).files)
                self.assertEqual(source.read_bytes(), original)
                self.assertTrue(list((base / '.xsave-backups').glob('*.zip')))
                app.mode.set('inspect')
                app.values['input'].set(str(base / 'missing'))
                app.apply_mode()
                app.start()
                deadline = time.monotonic() + 15
                while app.busy and time.monotonic() < deadline:
                    root.update()
                    time.sleep(0.01)
                self.assertFalse(app.busy)
                self.assertTrue(app.error)
                self.assertIsNone(app.report)
                self.assertEqual(str(app.run_button['state']), 'normal')
                app.mode.set('to-xbox')
                app.values['output'].set(str(base / 'cancelled'))
                app.values['allow_unsafe'].set(True)
                app.apply_mode()
                with patch('tkinter.messagebox.askyesno', return_value=False):
                    app.start()
                self.assertFalse(app.busy)
                self.assertFalse((base / 'cancelled').exists())
        finally:
            app.close()
