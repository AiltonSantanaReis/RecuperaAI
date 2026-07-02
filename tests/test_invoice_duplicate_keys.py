import sqlite3
import tempfile
import unittest
from pathlib import Path

from recuperaai.bootstrap import create_engine
from recuperaai.fiscal.key_utils import normalize_invoice_key, same_invoice_key


class InvoiceDuplicateKeyTests(unittest.TestCase):
    def test_normalize_invoice_key_removes_prefix_and_formatting(self):
        raw = 'NFe 3524 0112 3456 7800 0190 5500 1000 0012 3410 0001 2345'
        self.assertEqual(
            normalize_invoice_key(raw),
            '35240112345678000190550010000012341000012345',
        )
        self.assertTrue(same_invoice_key(raw, '35240112345678000190550010000012341000012345'))

    def test_import_blocks_same_invoice_key_even_when_file_hash_is_different(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(tmp)
            engine.initialize()
            session = engine.auth.login('admin', 'Admin@12345')
            client = engine.tool('clients').create_client(session, 'Cliente Duplicidade', '00.999.888/0001-77')

            original_xml = Path(__file__).with_name('sample_nfe.xml')
            duplicated_xml = Path(tmp) / 'mesma_nota_formatada.xml'
            duplicated_xml.write_text(
                original_xml.read_text(encoding='utf-8').replace('</nfeProc>', '<!-- arquivo reexportado -->\n</nfeProc>'),
                encoding='utf-8',
            )
            self.assertNotEqual(original_xml.read_bytes(), duplicated_xml.read_bytes())

            first = engine.tool('invoices').import_files(session, client.id, [original_xml], auto_analyze=False)
            self.assertEqual(len(first['imported']), 1)

            second = engine.tool('invoices').import_files(session, client.id, [duplicated_xml], auto_analyze=False)
            self.assertEqual(len(second['imported']), 0)
            self.assertEqual(len(second['skipped']), 1)
            self.assertIn('mesma chave fiscal', second['skipped'][0]['message'])

            docs = engine.tool('documents').list_for_client(session, client.id)
            self.assertEqual(len(docs), 1)
            self.assertEqual(docs[0].invoice_key, '35240112345678000190550010000012341000012345')

    def test_import_blocks_same_invoice_key_across_clients(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(tmp)
            engine.initialize()
            session = engine.auth.login('admin', 'Admin@12345')
            client_a = engine.tool('clients').create_client(session, 'Cliente A', '00.000.000/0001-00')
            client_b = engine.tool('clients').create_client(session, 'Cliente B', '11.111.111/0001-11')

            xml_a = Path(__file__).with_name('sample_nfe.xml')
            xml_b = Path(tmp) / 'mesma_chave_outro_cliente.xml'
            xml_b.write_text(xml_a.read_text(encoding='utf-8') + '\n', encoding='utf-8')

            result_a = engine.tool('invoices').import_files(session, client_a.id, [xml_a], auto_analyze=False)
            result_b = engine.tool('invoices').import_files(session, client_b.id, [xml_b], auto_analyze=False)

            self.assertEqual(len(result_a['imported']), 1)
            self.assertEqual(len(result_b['imported']), 0)
            self.assertEqual(len(result_b['skipped']), 1)
            self.assertIn('mesma chave fiscal', result_b['skipped'][0]['message'])


    def test_import_blocks_duplicate_nfse_by_canonical_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(tmp)
            engine.initialize()
            admin = engine.auth.login('admin', 'Admin@12345')
            client = engine.tool('clients').create_client(admin, 'Cliente NFSe', '00999888000177')
            source = Path(__file__).with_name('sample_nfse_abrasf.xml')

            first = engine.tool('invoices').import_files(admin, client.id, [source], auto_analyze=False)
            self.assertEqual(len(first['imported']), 1)

            copied = Path(tmp) / 'nfse_reexportada.xml'
            copied.write_text(source.read_text(encoding='utf-8').replace('</CompNfse>', '<!-- reexportada -->\n</CompNfse>'), encoding='utf-8')
            second = engine.tool('invoices').import_files(admin, client.id, [copied], auto_analyze=False)
            self.assertEqual(len(second['imported']), 0)
            self.assertEqual(len(second['skipped']), 1)
            self.assertIn('mesma chave fiscal', second['skipped'][0]['message'])

    def test_database_guard_blocks_duplicate_key_on_direct_insert(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(tmp)
            engine.initialize()
            session = engine.auth.login('admin', 'Admin@12345')
            client = engine.tool('clients').create_client(session, 'Cliente Banco', '22.222.222/0001-22')
            source = Path(__file__).with_name('sample_nfe.xml')
            key = 'NFe35240112345678000190550010000012341000012345'

            engine.documents.create_import(
                client.id,
                'nota_a.xml',
                'xml',
                source,
                'hash-a',
                session.user_id,
                initial_payload={'invoice_key': key},
                parser_status='ok',
            )
            with self.assertRaises(sqlite3.IntegrityError):
                engine.documents.create_import(
                    client.id,
                    'nota_b.xml',
                    'xml',
                    source,
                    'hash-b',
                    session.user_id,
                    initial_payload={'invoice_key': normalize_invoice_key(key)},
                    parser_status='ok',
                )


if __name__ == '__main__':
    unittest.main()
