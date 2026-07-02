import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from recuperaai.bootstrap import create_engine
from recuperaai.core.exceptions import PermissionDenied


class ProfessionalReportTests(unittest.TestCase):
    def test_report_data_contains_executive_summary_ranking_and_evidences(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(tmp)
            engine.initialize()
            session = engine.auth.login('admin', 'Admin@12345')
            client = engine.tool('clients').create_client(session, 'Cliente Relatório', '11.222.333/0001-44')
            xml = Path(__file__).with_name('sample_nfe.xml')
            result = engine.tool('invoices').import_files(session, client.id, [xml])
            self.assertEqual(len(result['imported']), 1)

            data = engine.tool('reports').build_client_report_data(session, client.id)

            self.assertEqual(data['client']['name'], 'Cliente Relatório')
            self.assertGreaterEqual(data['executive_summary']['total_invoices'], 1)
            self.assertGreaterEqual(data['executive_summary']['open_findings_total'], 1)
            self.assertGreaterEqual(data['executive_summary']['warning_findings'], 1)
            self.assertGreaterEqual(len(data['ranking']), 1)
            self.assertGreaterEqual(len(data['evidences']), 1)
            self.assertEqual(data['ranking'][0]['code'], 'CST_CSOSN_AUSENTE')
            self.assertIn('não representam', data['executive_summary']['method_note'])

    def test_professional_xlsx_has_expected_sheets_and_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(tmp)
            engine.initialize()
            session = engine.auth.login('admin', 'Admin@12345')
            client = engine.tool('clients').create_client(session, 'Cliente Excel', '22.333.444/0001-55')
            xml = Path(__file__).with_name('sample_nfe.xml')
            engine.tool('invoices').import_files(session, client.id, [xml])

            report_path = engine.tool('reports').export_client_xlsx(session, client.id)

            self.assertTrue(report_path.exists())
            self.assertEqual(report_path.suffix, '.xlsx')
            with ZipFile(report_path) as zf:
                workbook_xml = zf.read('xl/workbook.xml').decode('utf-8')
                package_text = ''.join(zf.read(name).decode('utf-8', errors='ignore') for name in zf.namelist() if name.endswith('.xml'))
            self.assertIn('Resumo Executivo', workbook_xml)
            self.assertIn('Ranking', workbook_xml)
            self.assertIn('Evidências por Nota', workbook_xml)
            self.assertIn('Notas Fiscais', workbook_xml)
            self.assertIn('CST_CSOSN_AUSENTE', package_text)
            self.assertIn('Relat', package_text)

    def test_professional_pdf_is_generated(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(tmp)
            engine.initialize()
            session = engine.auth.login('admin', 'Admin@12345')
            client = engine.tool('clients').create_client(session, 'Cliente PDF', '33.444.555/0001-66')
            xml = Path(__file__).with_name('sample_nfe.xml')
            engine.tool('invoices').import_files(session, client.id, [xml])

            report_path = engine.tool('reports').export_client_pdf(session, client.id)

            self.assertTrue(report_path.exists())
            self.assertEqual(report_path.suffix, '.pdf')
            self.assertGreater(report_path.stat().st_size, 1000)
            self.assertEqual(report_path.read_bytes()[:4], b'%PDF')

    def test_operator_cannot_build_or_export_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(tmp)
            engine.initialize()
            admin = engine.auth.login('admin', 'Admin@12345')
            engine.tool('users').create_user(admin, 'operadorrel', 'Operador Relatório', 'operator', 'Operador@12345')
            operator = engine.auth.login('operadorrel', 'Operador@12345')
            client = engine.tool('clients').create_client(admin, 'Cliente Restrito Relatório', '44.555.666/0001-77')

            with self.assertRaises(PermissionDenied):
                engine.tool('reports').build_client_report_data(operator, client.id)
            with self.assertRaises(PermissionDenied):
                engine.tool('reports').export_client_xlsx(operator, client.id)


if __name__ == '__main__':
    unittest.main()
