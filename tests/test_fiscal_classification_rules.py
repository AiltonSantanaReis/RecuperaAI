import tempfile
import unittest
from pathlib import Path

from recuperaai.fiscal.models import InvoiceData, InvoiceItem
from recuperaai.fiscal.rule_engine import FiscalRuleEngine
from recuperaai.fiscal.xml_parser import FiscalXmlParser


class FiscalClassificationRuleTests(unittest.TestCase):
    def _codes(self, invoice: InvoiceData) -> set[str]:
        return {finding['code'] for finding in FiscalRuleEngine().analyze(invoice)}

    def test_valid_normal_regime_item_does_not_raise_classification_findings(self):
        invoice = InvoiceData(
            source_type='xml',
            invoice_key='35240112345678000190550010000012341000012345',
            model='55',
            document_type='NF-e',
            issuer_tax_regime='3',
            operation_type='saida',
            operation_scope='interna',
            total_amount=100.0,
            taxes={'ICMS': 18.0},
            items=[InvoiceItem(description='Produto', ncm='12345678', cfop='5102', cst='00', total_value=100.0)],
        )
        codes = self._codes(invoice)
        self.assertNotIn('NCM_AUSENTE', codes)
        self.assertNotIn('CFOP_INCOMPATIVEL_OPERACAO', codes)
        self.assertNotIn('REGIME_TRIBUTARIO_INCOMPATIVEL', codes)
        self.assertNotIn('CST_CSOSN_AUSENTE', codes)

    def test_detects_invalid_ncm_missing_tax_code_and_cfop_direction(self):
        invoice = InvoiceData(
            source_type='xml',
            invoice_key='35240112345678000190550010000012341000012345',
            model='65',
            document_type='NFC-e',
            issuer_tax_regime='3',
            operation_type='saida',
            operation_scope='interna',
            total_amount=100.0,
            taxes={'TotalTributos': 5.0},
            items=[InvoiceItem(description='Produto', ncm='00000000', cfop='1102', total_value=100.0)],
        )
        codes = self._codes(invoice)
        self.assertIn('NCM_FORMATO_INVALIDO', codes)
        self.assertIn('CFOP_INCOMPATIVEL_OPERACAO', codes)
        self.assertIn('CST_CSOSN_AUSENTE', codes)

    def test_detects_cst_csosn_regime_mismatch(self):
        normal_with_csosn = InvoiceData(
            source_type='xml', invoice_key='1', model='55', document_type='NF-e', issuer_tax_regime='3', total_amount=10,
            taxes={'ICMS': 0.0}, items=[InvoiceItem(description='Produto', ncm='12345678', cfop='5102', csosn='102', total_value=10)]
        )
        simples_with_cst = InvoiceData(
            source_type='xml', invoice_key='2', model='55', document_type='NF-e', issuer_tax_regime='1', total_amount=10,
            taxes={'ICMS': 0.0}, items=[InvoiceItem(description='Produto', ncm='12345678', cfop='5102', cst='00', total_value=10)]
        )
        self.assertIn('REGIME_TRIBUTARIO_INCOMPATIVEL', self._codes(normal_with_csosn))
        self.assertIn('REGIME_TRIBUTARIO_INCOMPATIVEL', self._codes(simples_with_cst))

    def test_detects_invalid_cst_and_csosn_values(self):
        invoice = InvoiceData(
            source_type='xml', invoice_key='1', model='55', document_type='NF-e', issuer_tax_regime='3', total_amount=10,
            taxes={'ICMS': 0.0}, items=[InvoiceItem(description='Produto', ncm='12345678', cfop='5102', cst='99', csosn='999', total_value=10)]
        )
        codes = self._codes(invoice)
        self.assertIn('CST_CSOSN_DUPLO', codes)
        self.assertIn('CST_ICMS_INVALIDO', codes)
        self.assertIn('CSOSN_INVALIDO', codes)

    def test_parser_extracts_fiscal_context_from_nfe_xml(self):
        xml = '''<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">
          <NFe><infNFe Id="NFe35240112345678000190550010000077771000077775">
            <ide><mod>55</mod><tpNF>1</tpNF><idDest>2</idDest><serie>1</serie><nNF>7777</nNF><dhEmi>2024-01-10T09:30:00-03:00</dhEmi></ide>
            <emit><CNPJ>12345678000190</CNPJ><xNome>Fornecedor</xNome><enderEmit><UF>SP</UF></enderEmit><CRT>3</CRT></emit>
            <dest><CNPJ>00999888000177</CNPJ><xNome>Cliente</xNome><enderDest><UF>RJ</UF></enderDest></dest>
            <det nItem="1"><prod><cProd>A1</cProd><xProd>Produto A</xProd><NCM>12345678</NCM><CFOP>6102</CFOP><qCom>1</qCom><vUnCom>100</vUnCom><vProd>100</vProd></prod><imposto><ICMS><ICMS00><orig>0</orig><CST>00</CST><vICMS>18</vICMS></ICMS00></ICMS></imposto></det>
            <total><ICMSTot><vProd>100</vProd><vICMS>18</vICMS><vNF>100</vNF></ICMSTot></total>
          </infNFe></NFe>
        </nfeProc>'''
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'contexto.xml'
            path.write_text(xml, encoding='utf-8')
            invoice = FiscalXmlParser().parse(path)
        self.assertEqual(invoice.operation_type, 'saida')
        self.assertEqual(invoice.operation_scope, 'interestadual')
        self.assertEqual(invoice.issuer_state, 'SP')
        self.assertEqual(invoice.recipient_state, 'RJ')
        self.assertEqual(invoice.issuer_tax_regime, '3')
        self.assertEqual(invoice.items[0].cst, '00')


if __name__ == '__main__':
    unittest.main()
