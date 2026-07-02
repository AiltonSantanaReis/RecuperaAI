import unittest
import tempfile
from pathlib import Path

from recuperaai.fiscal.key_utils import normalize_invoice_key
from recuperaai.fiscal.xml_parser import FiscalXmlParser


class XmlParserTests(unittest.TestCase):
    def _sample(self, name: str) -> Path:
        return Path(__file__).with_name(name)

    def test_parse_sample_nfe(self):
        invoice = FiscalXmlParser().parse(self._sample('sample_nfe.xml'))
        self.assertEqual(invoice.document_type, 'NF-e')
        self.assertEqual(invoice.model, '55')
        self.assertEqual(invoice.invoice_key, '35240112345678000190550010000012341000012345')
        self.assertEqual(invoice.issuer_name, 'Fornecedor Exemplo Ltda')
        self.assertEqual(invoice.issuer_document, '12345678000190')
        self.assertEqual(invoice.recipient_document, '00999888000177')
        self.assertEqual(invoice.total_amount, 150.00)
        self.assertEqual(len(invoice.items), 2)
        self.assertEqual(invoice.items[0].ncm, '12345678')
        self.assertEqual(invoice.items[0].cfop, '5102')
        self.assertEqual(invoice.taxes['ICMS'], 18.00)

    def test_parse_nfce_model_65_without_recipient(self):
        invoice = FiscalXmlParser().parse(self._sample('sample_nfce.xml'))
        self.assertEqual(invoice.document_type, 'NFC-e')
        self.assertEqual(invoice.model, '65')
        self.assertEqual(invoice.invoice_key, '35240212345678000190650010000000011000000019')
        self.assertEqual(invoice.issuer_name, 'Mercado NFCe Ltda')
        self.assertIsNone(invoice.recipient_document)
        self.assertEqual(invoice.total_amount, 25.50)
        self.assertEqual(invoice.taxes['TotalTributos'], 2.10)
        self.assertEqual(invoice.items[0].cest, '1709600')
        self.assertEqual(invoice.items[0].csosn, '102')

    def test_parse_cte_model_57_with_transport_service_item(self):
        invoice = FiscalXmlParser().parse(self._sample('sample_cte.xml'))
        self.assertEqual(invoice.document_type, 'CT-e')
        self.assertEqual(invoice.model, '57')
        self.assertEqual(invoice.invoice_key, '35240312345678000190570010000022221000022225')
        self.assertEqual(invoice.number, '2222')
        self.assertEqual(invoice.issuer_document, '12345678000190')
        self.assertEqual(invoice.recipient_name, 'Destinatário SA')
        self.assertEqual(invoice.total_amount, 800.00)
        self.assertEqual(invoice.services_total, 800.00)
        self.assertEqual(invoice.taxes['ICMS'], 96.00)
        self.assertEqual(len(invoice.items), 1)
        self.assertEqual(invoice.items[0].cfop, '5353')

    def test_parse_nfse_abrasf_generates_canonical_key(self):
        invoice = FiscalXmlParser().parse(self._sample('sample_nfse_abrasf.xml'))
        expected_key = normalize_invoice_key('SERVICONFSE:12345678000190:9001:AB12CD')
        self.assertEqual(invoice.document_type, 'NFS-e')
        self.assertEqual(invoice.model, 'NFS-e')
        self.assertEqual(invoice.invoice_key, expected_key)
        self.assertEqual(invoice.number, '9001')
        self.assertEqual(invoice.issuer_name, 'Software House Exemplo Ltda')
        self.assertEqual(invoice.issuer_document, '12345678000190')
        self.assertEqual(invoice.recipient_document, '00999888000177')
        self.assertEqual(invoice.total_amount, 1140.00)
        self.assertEqual(invoice.services_total, 1200.00)
        self.assertEqual(invoice.items[0].service_code, '0107')
        self.assertEqual(invoice.taxes['ISS'], 60.00)
        self.assertTrue(any('Chave canônica de NFS-e' in warning for warning in invoice.warnings))

    def test_rejects_xml_with_dtd_or_entity_declaration(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'unsafe.xml'
            path.write_text(
                '<?xml version="1.0"?><!DOCTYPE nfe [<!ENTITY xxe SYSTEM "file:///c:/windows/win.ini">]><nfe>&xxe;</nfe>',
                encoding='utf-8',
            )
            with self.assertRaises(ValueError):
                FiscalXmlParser().parse(path)


if __name__ == '__main__':
    unittest.main()
