import tempfile
import unittest
from pathlib import Path

from recuperaai.bootstrap import create_engine
from recuperaai.core.exceptions import PermissionDenied, ValidationError


class ClientWorkspaceTests(unittest.TestCase):
    def test_client_workspace_concentrates_data_invoices_documents_and_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(tmp)
            engine.initialize()
            session = engine.auth.login('admin', 'Admin@12345')
            client = engine.tool('clients').create_client(
                session,
                'Cliente 360',
                '11.222.333/0001-44',
                contact_name='Maria Fiscal',
                email='fiscal@example.com',
                phone='11999990000',
                notes='Contrato anual e análise mensal.',
            )

            xml = Path(__file__).with_name('sample_nfe.xml')
            import_result = engine.tool('invoices').import_files(session, client.id, [xml])
            self.assertEqual(len(import_result['imported']), 1)

            contract = Path(tmp) / 'contrato.txt'
            contract.write_text('Contrato do cliente.', encoding='utf-8')
            engine.tool('documents').add_client_document(session, client.id, contract, category='contract')

            workspace = engine.tool('clients').get_client_workspace(session, client.id)

            self.assertEqual(workspace['client']['name'], 'Cliente 360')
            self.assertEqual(workspace['client']['contact_name'], 'Maria Fiscal')
            self.assertEqual(workspace['summary']['invoices_total'], 1)
            self.assertEqual(workspace['summary']['contracts_total'], 1)
            self.assertEqual(workspace['summary']['documents_total'], 2)
            self.assertEqual(len(workspace['invoices']), 1)
            self.assertEqual(len(workspace['contracts']), 1)
            self.assertEqual(len(workspace['all_documents']), 2)
            self.assertIn('open_findings_total', workspace['summary'])
            self.assertIsInstance(workspace['open_findings'], list)

    def test_operator_can_open_workspace_but_cannot_edit_or_attach_documents(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(tmp)
            engine.initialize()
            admin = engine.auth.login('admin', 'Admin@12345')
            engine.tool('users').create_user(admin, 'operador360', 'Operador 360', 'operator', 'Operador@12345')
            operator = engine.auth.login('operador360', 'Operador@12345')
            client = engine.tool('clients').create_client(admin, 'Cliente Operador', '00.000.000/0001-00')

            workspace = engine.tool('clients').get_client_workspace(operator, client.id)
            self.assertEqual(workspace['client']['name'], 'Cliente Operador')

            with self.assertRaises(PermissionDenied):
                engine.tool('clients').update_client(operator, client.id, name='Alteração indevida')

            file_path = Path(tmp) / 'documento.txt'
            file_path.write_text('Documento interno.', encoding='utf-8')
            with self.assertRaises(PermissionDenied):
                engine.tool('documents').add_client_document(operator, client.id, file_path, category='contract')

    def test_client_update_rejects_blank_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(tmp)
            engine.initialize()
            session = engine.auth.login('admin', 'Admin@12345')
            client = engine.tool('clients').create_client(session, 'Cliente Nome', '00.000.000/0001-00')

            with self.assertRaises(ValidationError):
                engine.tool('clients').update_client(session, client.id, name='   ')

            saved = engine.tool('clients').get_client(session, client.id)
            self.assertEqual(saved.name, 'Cliente Nome')

    def test_archive_client_preserves_workspace_and_hides_operational_views(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(tmp)
            engine.initialize()
            session = engine.auth.login('admin', 'Admin@12345')
            client = engine.tool('clients').create_client(session, 'Cliente Arquivo', '00.000.000/0001-00')
            invoice = engine.tool('invoices').import_files(
                session,
                client.id,
                [Path(__file__).with_name('sample_nfe.xml')],
                auto_analyze=False,
            )['imported'][0]
            engine.findings.add_many(invoice.id, [{
                'severity': 'warning',
                'code': 'ARQUIVO_TESTE',
                'title': 'Oportunidade preservada',
                'message': 'Apontamento mantido no histórico do cliente.',
                'amount': 250.0,
                'source': 'api',
            }])

            archived = engine.tool('clients').archive_client(session, client.id)

            self.assertEqual(archived.status, 'archived')
            self.assertEqual(engine.tool('clients').list_clients(session), [])
            archived_list = engine.tool('clients').list_clients(session, include_archived=True, archived_only=True)
            self.assertEqual([item.id for item in archived_list], [client.id])

            workspace = engine.tool('clients').get_client_workspace(session, client.id)
            self.assertEqual(workspace['client']['status'], 'archived')
            self.assertEqual(len(workspace['invoices']), 1)
            self.assertEqual(len(workspace['all_findings']), 1)
            self.assertIn('CLIENTE_ARQUIVADO', [item['action'] for item in workspace['history']])

            dashboard = engine.tool('analysis').dashboard(session)
            self.assertEqual(dashboard['clients'].get('active', 0), 0)
            self.assertEqual(dashboard['documents']['total_documents'], 0)
            self.assertEqual(dashboard['opportunities']['estimated_total'], 0.0)
            self.assertEqual(dashboard['opportunities_by_client'], [])
            self.assertEqual(dashboard['recent_documents'], [])

            restored = engine.tool('clients').restore_client(session, client.id)

            self.assertEqual(restored.status, 'active')
            self.assertEqual([item.id for item in engine.tool('clients').list_clients(session)], [client.id])
            restored_dashboard = engine.tool('analysis').dashboard(session)
            self.assertAlmostEqual(restored_dashboard['opportunities']['estimated_total'], 250.0)

    def test_archived_client_blocks_new_operational_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(tmp)
            engine.initialize()
            session = engine.auth.login('admin', 'Admin@12345')
            client = engine.tool('clients').create_client(session, 'Cliente Bloqueado', '00.000.000/0001-00')
            engine.tool('clients').archive_client(session, client.id)

            document = Path(tmp) / 'documento.txt'
            document.write_text('Documento interno.', encoding='utf-8')

            with self.assertRaises(ValidationError):
                engine.tool('documents').add_client_document(session, client.id, document, category='contract')
            with self.assertRaises(ValidationError):
                engine.tool('invoices').import_files(session, client.id, [Path(__file__).with_name('sample_nfe.xml')])
            with self.assertRaises(ValidationError):
                engine.tool('analysis').analyze_client(session, client.id)

    def test_client_document_rejects_unknown_or_path_like_category(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(tmp)
            engine.initialize()
            session = engine.auth.login('admin', 'Admin@12345')
            client = engine.tool('clients').create_client(session, 'Cliente Documento', '00.000.000/0001-00')
            file_path = Path(tmp) / 'documento.txt'
            file_path.write_text('Documento interno.', encoding='utf-8')

            for category in ('', 'invoice', '..\\escape', '../../escape'):
                with self.assertRaises(ValidationError):
                    engine.tool('documents').add_client_document(session, client.id, file_path, category=category)

    def test_analyze_client_ignores_contracts_and_client_documents(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(tmp)
            engine.initialize()
            session = engine.auth.login('admin', 'Admin@12345')
            client = engine.tool('clients').create_client(session, 'Cliente Análise', '00.000.000/0001-00')
            xml = Path(__file__).with_name('sample_nfe.xml')
            invoice = engine.tool('invoices').import_files(session, client.id, [xml], auto_analyze=False)['imported'][0]

            contract_path = Path(tmp) / 'contrato.txt'
            contract_path.write_text('Contrato do cliente.', encoding='utf-8')
            contract = engine.tool('documents').add_client_document(session, client.id, contract_path, category='contract')

            result = engine.tool('analysis').analyze_client(session, client.id)

            self.assertEqual(result['analyzed'], 1)
            self.assertEqual(result['failed'], [])
            self.assertEqual(engine.tool('documents').get_document(session, contract.id).processing_status, 'stored')
            self.assertNotEqual(engine.tool('documents').get_document(session, invoice.id).processing_status, 'stored')

    def test_invoice_delete_removes_record_file_and_linked_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(tmp)
            engine.initialize()
            admin = engine.auth.login('admin', 'Admin@12345')
            engine.tool('users').create_user(admin, 'operador_del', 'Operador Delete', 'operator', 'Operador@12345')
            operator = engine.auth.login('operador_del', 'Operador@12345')
            client = engine.tool('clients').create_client(admin, 'Cliente Delete', '00.000.000/0001-00')
            invoice = engine.tool('invoices').import_files(operator, client.id, [Path(__file__).with_name('sample_nfe.xml')], auto_analyze=False)['imported'][0]
            stored_path = Path(invoice.storage_path)
            self.assertTrue(stored_path.exists())
            engine.findings.add_many(invoice.id, [{
                'severity': 'warning',
                'code': 'TESTE',
                'title': 'Apontamento de teste',
                'message': 'Valor recuperável para teste.',
                'amount': 123.45,
                'source': 'api',
            }])

            deleted = engine.tool('invoices').delete_invoice(operator, invoice.id)

            self.assertEqual(deleted.id, invoice.id)
            self.assertIsNone(engine.tool('documents').get_document(admin, invoice.id))
            self.assertFalse(stored_path.exists())
            self.assertEqual(engine.tool('analysis').list_for_client(admin, client.id), [])

            with self.assertRaises(ValidationError):
                engine.tool('invoices').delete_invoice(operator, invoice.id)

    def test_viewer_cannot_delete_invoice(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(tmp)
            engine.initialize()
            admin = engine.auth.login('admin', 'Admin@12345')
            engine.tool('users').create_user(admin, 'consulta_del', 'Consulta Delete', 'viewer', 'Consulta@12345')
            viewer = engine.auth.login('consulta_del', 'Consulta@12345')
            client = engine.tool('clients').create_client(admin, 'Cliente Consulta Delete', '00.000.000/0001-00')
            invoice = engine.tool('invoices').import_files(admin, client.id, [Path(__file__).with_name('sample_nfe.xml')], auto_analyze=False)['imported'][0]

            with self.assertRaises(PermissionDenied):
                engine.tool('invoices').delete_invoice(viewer, invoice.id)

    def test_workspace_and_dashboard_include_refund_opportunity_totals(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(tmp)
            engine.initialize()
            session = engine.auth.login('admin', 'Admin@12345')
            client = engine.tool('clients').create_client(session, 'Cliente Oportunidade', '00.000.000/0001-00')
            invoice = engine.tool('invoices').import_files(session, client.id, [Path(__file__).with_name('sample_nfe.xml')], auto_analyze=False)['imported'][0]
            engine.findings.add_many(invoice.id, [{
                'severity': 'critical',
                'code': 'CREDITO_API',
                'title': 'Crédito fiscal potencial',
                'message': 'Valor retornado pela integração para revisão.',
                'amount': 987.65,
                'source': 'api',
            }])

            workspace = engine.tool('clients').get_client_workspace(session, client.id)
            dashboard = engine.tool('analysis').dashboard(session)

            self.assertAlmostEqual(workspace['summary']['opportunities']['estimated_total'], 987.65)
            self.assertAlmostEqual(workspace['summary']['opportunities']['api_estimated_total'], 987.65)
            self.assertAlmostEqual(dashboard['opportunities']['estimated_total'], 987.65)
            self.assertEqual(dashboard['opportunities_by_client'][0]['client_id'], client.id)


if __name__ == '__main__':
    unittest.main()
