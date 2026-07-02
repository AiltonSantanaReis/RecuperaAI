from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from recuperaai.app import main
from recuperaai.core.logging_config import shutdown_logging
from recuperaai.security.permissions import visible_tabs_for_role
from recuperaai.validation.visual_validation import prepare_visual_validation


class Stage10VisualValidationTests(unittest.TestCase):
    def tearDown(self):
        shutdown_logging()

    def test_visual_validation_prepares_demo_client_checklist_and_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            checklist = Path(tmp) / 'checklist.md'
            result = prepare_visual_validation(base_dir=tmp, checklist_output=str(checklist))
            self.assertTrue(result['ok'])
            self.assertTrue(checklist.exists())
            text = checklist.read_text(encoding='utf-8')
            self.assertIn('Checklist de Validação Visual', text)
            self.assertIn('Cliente Validação Visual', text)
            self.assertGreaterEqual(result['findings'], 1)
            self.assertGreaterEqual(result['reports'], 1)
            self.assertIn('invoices', result['workspace_sections'])
            self.assertIn('history', result['workspace_sections'])

    def test_cli_visual_check_writes_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'visual.json'
            checklist = Path(tmp) / 'visual.md'
            code = main(['--visual-check', '--base-dir', tmp, '--output-file', str(output), '--checklist-output', str(checklist)])
            self.assertEqual(code, 0)
            self.assertTrue(output.exists())
            self.assertTrue(checklist.exists())
            self.assertIn('"ok": true', output.read_text(encoding='utf-8'))

    def test_stage10_exposes_operational_tabs_without_technical_tabs_for_operator_and_viewer(self):
        self.assertEqual(
            [tab.key for tab in visible_tabs_for_role('viewer')],
            ['dashboard', 'clients', 'invoices', 'analysis'],
        )
        self.assertEqual(
            [tab.key for tab in visible_tabs_for_role('operator')],
            ['dashboard', 'clients', 'invoices', 'analysis'],
        )
        self.assertIn('backup', [tab.key for tab in visible_tabs_for_role('supervisor')])
        self.assertNotIn('settings', [tab.key for tab in visible_tabs_for_role('operator')])
        self.assertNotIn('backup', [tab.key for tab in visible_tabs_for_role('operator')])

    def test_stage10_build_and_package_scripts_include_visual_validation(self):
        build_ps1 = Path('scripts/build_windows.ps1').read_text(encoding='utf-8')
        package_py = Path('scripts/package_windows_release.py').read_text(encoding='utf-8')
        self.assertIn('--visual-check', build_ps1)
        self.assertIn('CHECKLIST_VALIDACAO_VISUAL', build_ps1)
        self.assertIn('validacao_visual.bat', package_py)
        self.assertTrue(Path('validacao_visual.bat').exists())
        self.assertTrue(Path('README.md').exists())
        self.assertTrue(Path('ARCHITECTURE.md').exists())


if __name__ == '__main__':
    unittest.main()
