import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication, QComboBox, QToolButton

from recuperaai.bootstrap import create_engine
from recuperaai.ui.main_window import MainWindow


class UiOperationalFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_client_selectors_are_visible_and_drive_operational_tabs(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(tmp)
            engine.initialize()
            session = engine.auth.login('admin', 'Admin@12345')
            client = engine.tool('clients').create_client(session, 'Cliente Fluxo UI', '12.345.678/0001-90')
            engine.tool('invoices').import_files(session, client.id, [Path(__file__).with_name('sample_nfe.xml')])

            window = MainWindow(engine, session)
            window.resize(1180, 760)
            window.show()
            self.app.processEvents()

            selectors = [
                ('Notas Fiscais', window.invoices_client_combo),
                ('Análises', window.analysis_client_combo),
                ('Relatórios', window.reports_client_combo),
            ]
            self.assertIn('Oportunidades', window.tabs.labels)
            self.assertNotIn('Importação', window.tabs.labels)
            for tab_label, selector in selectors:
                window.tabs.setCurrentIndex(window.tabs.labels.index(tab_label))
                self.app.processEvents()
                self.assertIsInstance(selector, QComboBox)
                self.assertTrue(selector.isVisible())
                self.assertGreater(selector.count(), 1)
                self.assertIn('color: #102033', selector.styleSheet())

            window.tabs.setCurrentIndex(window.tabs.labels.index('Notas Fiscais'))
            self.app.processEvents()
            index = window.invoices_client_combo.findData(client.id)
            self.assertGreaterEqual(index, 0)
            window.invoices_client_combo.setCurrentIndex(index)
            self.app.processEvents()

            self.assertEqual(window.selected_client_id, client.id)
            self.assertEqual(window.analysis_client_combo.currentData(), client.id)
            self.assertNotIn('Inconsistências', window.tabs.labels)

            window.open_client_workspace_dialog()
            self.app.processEvents()
            for tab_index in range(window.client_detail_tabs.count()):
                if window.client_detail_tabs.tabText(tab_index) == 'Importações':
                    window.client_detail_tabs.setCurrentIndex(tab_index)
                    break
            self.app.processEvents()
            import_buttons = [
                button for button in window.client_detail_tabs.findChildren(QToolButton)
                if button.toolTip() == 'Anexar XML/PDF fiscal'
            ]
            self.assertEqual(len(import_buttons), 1)
            self.assertTrue(import_buttons[0].isVisible())
            self.assertEqual(window.review_status.objectName(), 'actionCombo')
            self.assertEqual(window.review_note.objectName(), 'actionInput')
            self.assertEqual(window.detail_status.objectName(), 'formCombo')
            self.assertEqual(window.client_doc_category.objectName(), 'actionCombo')

            window.tabs.setCurrentIndex(window.tabs.labels.index('Análises'))
            window.refresh_client_workspace()
            self.app.processEvents()
            self.assertEqual(window.global_review_status.objectName(), 'actionCombo')
            self.assertEqual(window.global_review_note.objectName(), 'actionInput')
            analysis_headers = [
                window.findings_table.horizontalHeaderItem(i).text()
                for i in range(window.findings_table.columnCount())
            ]
            self.assertIn('Valor da nota', analysis_headers)
            self.assertIn('Valor apontado', analysis_headers)
            self.assertGreater(window.findings_table.rowCount(), 0)
            table_text = ' '.join(
                window.findings_table.item(row, col).text()
                for row in range(window.findings_table.rowCount())
                for col in range(window.findings_table.columnCount())
                if window.findings_table.item(row, col)
            )
            self.assertIn('R$', table_text)
            self.assertIn('150,00', table_text)
            window.findings_table.selectRow(0)
            document_id = window._document_id_from_finding_table(window.findings_table)
            self.assertIsNotNone(document_id)
            preview = window._document_preview_text(engine.tool('documents').get_document(session, document_id))
            self.assertIn('Dados lidos da nota', preview)
            self.assertIn('150.0', preview)
            window._workspace_dialog.close()
            window.close()

    def test_search_and_predefined_filters_reduce_operational_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(tmp)
            engine.initialize()
            session = engine.auth.login('admin', 'Admin@12345')
            alpha = engine.tool('clients').create_client(session, 'Alpha Fiscal', '11.111.111/0001-11')
            beta = engine.tool('clients').create_client(session, 'Beta Pausado', '22.222.222/0001-22')
            engine.tool('clients').update_client(session, beta.id, status='paused')
            engine.tool('invoices').import_files(session, alpha.id, [Path(__file__).with_name('sample_nfe.xml')])

            window = MainWindow(engine, session)
            window.resize(1180, 760)
            window.show()
            self.app.processEvents()

            window.tabs.setCurrentIndex(window.tabs.labels.index('Clientes'))
            window.clients_search.setText('Beta')
            self.app.processEvents()
            self.assertEqual(window.clients_table.rowCount(), 1)
            self.assertEqual(window.clients_table.item(0, 1).text(), 'Beta Pausado')

            window.clients_status_filter.setCurrentIndex(window.clients_status_filter.findData('active'))
            self.app.processEvents()
            self.assertEqual(window.clients_table.rowCount(), 0)

            window.clients_search.clear()
            self.app.processEvents()
            self.assertEqual(window.clients_table.rowCount(), 1)
            self.assertEqual(window.clients_table.item(0, 1).text(), 'Alpha Fiscal')

            window.selected_client_id = alpha.id
            window.refresh_client_workspace()
            window.tabs.setCurrentIndex(window.tabs.labels.index('Notas Fiscais'))
            self.app.processEvents()
            window.invoices_type_filter.setCurrentIndex(window.invoices_type_filter.findData('xml'))
            self.app.processEvents()
            self.assertEqual(window.invoices_table.rowCount(), 1)
            self.assertIn('sample_nfe.xml', window.invoices_table.item(0, 1).text())

            window.invoices_search.setText('texto inexistente')
            self.app.processEvents()
            self.assertEqual(window.invoices_table.horizontalHeaderItem(0).text(), 'Aviso')
            self.assertIn('Nenhuma nota fiscal', window.invoices_table.item(0, 0).text())

            window.tabs.setCurrentIndex(window.tabs.labels.index('Análises'))
            self.app.processEvents()
            finding = engine.tool('analysis').list_for_client(session, alpha.id)[0]
            severity_index = window.analysis_severity_filter.findData(finding['severity'])
            self.assertGreaterEqual(severity_index, 0)
            window.analysis_severity_filter.setCurrentIndex(severity_index)
            self.app.processEvents()
            self.assertGreater(window.findings_table.rowCount(), 0)

            status_index = window.analysis_status_filter.findData(finding['status'])
            self.assertGreaterEqual(status_index, 0)
            window.analysis_status_filter.setCurrentIndex(status_index)
            window.analysis_search.setText(finding['title'])
            self.app.processEvents()
            self.assertGreater(window.findings_table.rowCount(), 0)

            window.analysis_search.setText('texto inexistente')
            self.app.processEvents()
            self.assertEqual(window.findings_table.rowCount(), 0)
            window.close()


if __name__ == '__main__':
    unittest.main()
