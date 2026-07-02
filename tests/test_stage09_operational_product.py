import tempfile
import unittest
import sqlite3
from pathlib import Path

from recuperaai.bootstrap import create_engine
from recuperaai.core.exceptions import PermissionDenied
from recuperaai.security.permissions import can, visible_tabs_for_role


class Stage09OperationalProductTests(unittest.TestCase):
    def test_workspace_has_operational_sections_for_client_central(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(tmp)
            engine.initialize()
            session = engine.auth.login('admin', 'Admin@12345')
            client = engine.tool('clients').create_client(session, 'Cliente Central', '12.345.678/0001-90')

            xml = Path(__file__).with_name('sample_nfe.xml')
            imported = engine.tool('invoices').import_files(session, client.id, [xml])
            self.assertEqual(len(imported['imported']), 1)

            pdf_like = Path(tmp) / 'documento_cliente.txt'
            pdf_like.write_text('Documento recebido do cliente.', encoding='utf-8')
            engine.tool('documents').add_client_document(session, client.id, pdf_like, 'corporate')

            workspace = engine.tool('clients').get_client_workspace(session, client.id)
            for key in ['client', 'summary', 'invoices', 'client_documents', 'all_findings', 'import_history', 'reports', 'history']:
                self.assertIn(key, workspace)
            self.assertEqual(workspace['summary']['invoices_total'], 1)
            self.assertGreaterEqual(len(workspace['all_findings']), 1)
            self.assertGreaterEqual(len(workspace['import_history']), 1)
            self.assertGreaterEqual(len(workspace['history']), 3)

    def test_human_review_updates_finding_status_and_client_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(tmp)
            engine.initialize()
            admin = engine.auth.login('admin', 'Admin@12345')
            analyst_user = engine.tool('users').create_user(admin, 'analista09', 'Analista 09', 'analyst', 'Analista@12345')
            analyst = engine.auth.login('analista09', 'Analista@12345')
            client = engine.tool('clients').create_client(admin, 'Cliente Revisão', '22.333.444/0001-55')
            xml = Path(__file__).with_name('sample_nfe.xml')
            engine.tool('invoices').import_files(admin, client.id, [xml])

            finding = engine.tool('analysis').list_for_client(admin, client.id)[0]
            updated = engine.tool('analysis').review_finding(analyst, finding['id'], 'in_review', 'Validar regime tributário do período.')
            self.assertEqual(updated['status'], 'in_review')
            self.assertEqual(updated['review_note'], 'Validar regime tributário do período.')

            workspace = engine.tool('clients').get_client_workspace(admin, client.id)
            self.assertEqual(workspace['summary']['finding_status']['in_review'], 1)
            actions = [item['action'] for item in workspace['history']]
            self.assertIn('INCONSISTENCIA_REVISADA', actions)

    def test_stage09_roles_include_supervisor_and_viewer(self):
        self.assertTrue(can('supervisor', 'reports_approve'))
        self.assertTrue(can('viewer', 'clients_read'))
        self.assertFalse(can('viewer', 'invoices_import'))
        self.assertEqual(
            [tab.key for tab in visible_tabs_for_role('viewer')],
            ['dashboard', 'clients', 'invoices', 'analysis'],
        )
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(tmp)
            engine.initialize()
            admin = engine.auth.login('admin', 'Admin@12345')
            engine.tool('users').create_user(admin, 'consulta09', 'Consulta 09', 'viewer', 'Consulta@12345')
            viewer = engine.auth.login('consulta09', 'Consulta@12345')
            client = engine.tool('clients').create_client(admin, 'Cliente Consulta', '00.111.222/0001-33')
            self.assertEqual(engine.tool('clients').get_client_workspace(viewer, client.id)['client']['name'], 'Cliente Consulta')
            with self.assertRaises(PermissionDenied):
                engine.tool('invoices').import_files(viewer, client.id, [Path(__file__).with_name('sample_nfe.xml')])

    def test_reports_tab_lists_generated_reports_and_csv_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(tmp)
            engine.initialize()
            session = engine.auth.login('admin', 'Admin@12345')
            client = engine.tool('clients').create_client(session, 'Cliente CSV', '66.777.888/0001-00')
            xml = Path(__file__).with_name('sample_nfe.xml')
            engine.tool('invoices').import_files(session, client.id, [xml])
            csv_path = engine.tool('reports').export_client_csv(session, client.id)
            self.assertTrue(csv_path.exists())
            reports = engine.tool('reports').list_client_reports(session, client.id)
            self.assertTrue(any(item['path'] == str(csv_path) for item in reports))

    def test_migration_repairs_legacy_user_reference_before_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(tmp)
            engine.initialize()

            conn = sqlite3.connect(engine.paths.database)
            try:
                conn.execute("PRAGMA foreign_keys=OFF")
                conn.executescript(
                    """
                    DROP TABLE documents;
                    CREATE TABLE documents (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                        original_name TEXT NOT NULL,
                        file_type TEXT NOT NULL,
                        category TEXT NOT NULL DEFAULT 'invoice',
                        storage_path TEXT NOT NULL,
                        sha256 TEXT NOT NULL,
                        invoice_key TEXT,
                        issue_date TEXT,
                        issuer_name TEXT,
                        issuer_document TEXT,
                        recipient_name TEXT,
                        recipient_document TEXT,
                        total_amount REAL,
                        parser_status TEXT NOT NULL DEFAULT 'pending',
                        processing_status TEXT NOT NULL DEFAULT 'imported',
                        payload_json TEXT,
                        created_by INTEGER REFERENCES users_old_stage09(id),
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(client_id, sha256)
                    );
                    """
                )
                conn.commit()
            finally:
                conn.close()

            repaired = create_engine(tmp)
            repaired.initialize()
            session = repaired.auth.login('admin', 'Admin@12345')
            client = repaired.tool('clients').create_client(session, 'Cliente Migração', '11.222.333/0001-44')
            xml = Path(__file__).with_name('sample_nfe.xml')

            result = repaired.tool('invoices').import_files(session, client.id, [xml], auto_analyze=False)
            self.assertEqual(len(result['imported']), 1)


if __name__ == '__main__':
    unittest.main()
