from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

from recuperaai.build_info import version_label


class Stage11VisualRedesignTests(unittest.TestCase):
    def test_version_identifies_stage11(self):
        self.assertIn('1.0.0-etapa11.0', version_label())
        self.assertIn('Etapa 11', version_label())

    def test_main_window_uses_sidebar_instead_of_top_level_tabs(self):
        text = Path('recuperaai/ui/main_window.py').read_text(encoding='utf-8')
        self.assertIn('class SidebarNavigation', text)
        self.assertIn("sidebarButton", text)
        self.assertIn("self.content_stack = QStackedWidget()", text)
        self.assertNotIn('self.tabs = QTabWidget()\n        self.setCentralWidget(self.tabs)', text)

    def test_styles_include_modern_sidebar_and_empty_states(self):
        qss = Path('recuperaai/ui/styles.qss').read_text(encoding='utf-8')
        for selector in ['QFrame#sidebar', 'QPushButton#sidebarButton', 'QLabel#metricCard', 'QLabel#emptyState', 'QLabel#clientSummaryCard']:
            self.assertIn(selector, qss)
        self.assertNotIn('primaryImportButton', qss)

    def test_filters_and_delete_confirmation_follow_current_visual_pattern(self):
        main_window = Path('recuperaai/ui/main_window.py').read_text(encoding='utf-8')
        qss = Path('recuperaai/ui/styles.qss').read_text(encoding='utf-8')
        pyproject = Path('pyproject.toml').read_text(encoding='utf-8')
        spec = Path('RecuperaAI.spec').read_text(encoding='utf-8')

        self.assertIn('def _confirm_destructive_action', main_window)
        self.assertIn('def _selection_combo', main_window)
        self.assertIn('def _action_input', main_window)
        self.assertNotIn('QMessageBox.question', main_window)
        self.assertIn("card_layout.addLayout(self._filter_row(", main_window)
        self.assertIn("__UI_ASSET_DIR__", qss)
        self.assertTrue(Path('recuperaai/ui/chevron_down.svg').exists())
        self.assertIn('ui/chevron_down.svg', pyproject)
        self.assertIn('recuperaai/ui/chevron_down.svg', spec)
        for selector in [
            'QComboBox::drop-down',
            'QComboBox::down-arrow',
            'QComboBox#actionCombo',
            'QComboBox#formCombo',
            'QLineEdit#actionInput',
            'QLineEdit#filterSearch:hover',
            'QComboBox#filterCombo::drop-down',
            'QComboBox#filterCombo QAbstractItemView',
            'QDialog#confirmDialog',
            'QPushButton#dangerButton',
            'QPushButton#secondaryButton',
        ]:
            self.assertIn(selector, qss)

    def test_visual_validation_uses_stage11_checklist_name(self):
        validation = Path('recuperaai/validation/visual_validation.py').read_text(encoding='utf-8')
        build_ps1 = Path('scripts/build_windows.ps1').read_text(encoding='utf-8')
        self.assertIn('Checklist de Validação Visual Etapa 11', validation)
        self.assertIn('CHECKLIST_VALIDACAO_VISUAL_ETAPA11', build_ps1)
        package_py = Path('scripts/package_windows_release.py').read_text(encoding='utf-8')
        self.assertIn('README.md', package_py)
        self.assertIn('ARCHITECTURE.md', package_py)

    def test_visual_checklist_matches_current_navigation(self):
        from recuperaai.validation.visual_validation import CHECKLIST_ITEMS

        titles = [title for title, _description in CHECKLIST_ITEMS]
        descriptions = ' '.join(description for _title, description in CHECKLIST_ITEMS)
        self.assertIn('Oportunidades', titles)
        self.assertIn('Importações do cliente', titles)
        self.assertNotIn('Painel', titles)
        self.assertNotIn('Importação', titles)
        self.assertIn('central do cliente', descriptions)

    def test_offscreen_visual_audit_configures_windows_font_directory(self):
        import recuperaai.ui as ui

        with mock.patch.dict(os.environ, {'QT_QPA_PLATFORM': 'offscreen'}, clear=False):
            os.environ.pop('QT_QPA_FONTDIR', None)
            ui._configure_offscreen_fonts()
            font_dir = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Fonts'
            if font_dir.exists():
                self.assertEqual(Path(os.environ['QT_QPA_FONTDIR']), font_dir)


if __name__ == '__main__':
    unittest.main()
