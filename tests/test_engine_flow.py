import tempfile
import unittest
from pathlib import Path

from recuperaai.bootstrap import create_engine


class EngineFlowTests(unittest.TestCase):
    def test_create_client_import_and_analyze_xml(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(tmp)
            engine.initialize()
            session = engine.auth.login('admin', 'Admin@12345')
            client = engine.tool('clients').create_client(session, 'Cliente Teste', '00.999.888/0001-77')
            xml = Path(__file__).with_name('sample_nfe.xml')
            result = engine.tool('invoices').import_files(session, client.id, [xml])
            self.assertEqual(len(result['imported']), 1)
            docs = engine.tool('documents').list_for_client(session, client.id)
            self.assertEqual(len(docs), 1)
            findings = engine.tool('analysis').list_open_for_client(session, client.id)
            self.assertIsInstance(findings, list)


if __name__ == '__main__':
    unittest.main()
