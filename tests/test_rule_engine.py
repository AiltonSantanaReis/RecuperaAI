import unittest
import tempfile
from pathlib import Path

from recuperaai.fiscal.models import InvoiceData, InvoiceItem
from recuperaai.fiscal.pdf_extractor import PDF_TEXT_BACKEND, PdfExtractor
from recuperaai.fiscal.rule_engine import FiscalRuleEngine


class RuleEngineTests(unittest.TestCase):
    def test_missing_total(self):
        findings = FiscalRuleEngine().analyze(InvoiceData(source_type='xml', invoice_key='123'))
        codes = {f['code'] for f in findings}
        self.assertIn('TOTAL_AUSENTE', codes)

    def test_pdf_confidence(self):
        findings = FiscalRuleEngine().analyze(InvoiceData(source_type='pdf', total_amount=100))
        codes = {f['code'] for f in findings}
        self.assertIn('PDF_BAIXA_CONFIANCA', codes)

    def test_pdf_text_extraction_uses_pypdf_backend(self):
        from reportlab.pdfgen import canvas

        key = '12345678901234567890123456789012345678901234'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'nota.pdf'
            pdf = canvas.Canvas(str(path))
            pdf.drawString(72, 760, f'Chave fiscal: {key}')
            pdf.drawString(72, 740, 'CNPJ: 12.345.678/0001-90')
            pdf.drawString(72, 720, 'Valor total: R$ 1.234,56')
            pdf.save()

            data = PdfExtractor().parse(path)

        self.assertEqual(PDF_TEXT_BACKEND, 'pypdf')
        self.assertEqual(data.invoice_key, key)
        self.assertEqual(data.issuer_document, '12.345.678/0001-90')
        self.assertEqual(data.total_amount, 1234.56)

    def test_pdf_total_uses_fiscal_label_not_largest_money_value(self):
        from reportlab.pdfgen import canvas

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'nota_com_capital_social.pdf'
            pdf = canvas.Canvas(str(path))
            pdf.drawString(72, 760, 'Fornecedor Exemplo Ltda')
            pdf.drawString(72, 740, 'CNPJ: 12.345.678/0001-90')
            pdf.drawString(72, 720, 'Capital social: R$ 50.000,00')
            pdf.drawString(72, 700, 'Valor total da nota: R$ 3.000,00')
            pdf.save()

            data = PdfExtractor().parse(path)

        self.assertEqual(data.total_amount, 3000.0)

    def test_pdf_does_not_guess_total_from_unrelated_money_value(self):
        from reportlab.pdfgen import canvas

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'documento_sem_total_fiscal.pdf'
            pdf = canvas.Canvas(str(path))
            pdf.drawString(72, 760, 'Contrato social anexado a nota')
            pdf.drawString(72, 740, 'CNPJ: 12.345.678/0001-90')
            pdf.drawString(72, 720, 'Capital social: R$ 50.000,00')
            pdf.save()

            data = PdfExtractor().parse(path)

        self.assertIsNone(data.total_amount)
        self.assertTrue(any('Valor total da nota não identificado' in warning for warning in data.warnings))

    def test_item_mismatch(self):
        invoice = InvoiceData(source_type='xml', invoice_key='123', total_amount=120, items=[InvoiceItem(total_value=100)])
        findings = FiscalRuleEngine().analyze(invoice)
        self.assertIn('SOMA_ITENS_DIVERGENTE', {f['code'] for f in findings})


if __name__ == '__main__':
    unittest.main()
