import json
import tempfile
import unittest
from pathlib import Path

from recuperaai.bootstrap import create_engine
from recuperaai.fiscal.pdf_extractor import PdfExtractor


def write_fake_invoice_pdf(path: Path, *, key: str, total: str = "R$ 1.234,56") -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    pdf = canvas.Canvas(str(path), pagesize=A4)
    y = 800
    lines = [
        "NOTA FISCAL ELETRONICA FICTICIA - AMBIENTE DE TESTE",
        f"Chave fiscal: {key}",
        "Data de emissao: 15/03/2026",
        "Emitente: Fornecedor PDF Teste Ltda",
        "CNPJ emitente: 12.345.678/0001-90",
        "Destinatario: Cliente PDF Teste SA",
        "CNPJ destinatario: 00.999.888/0001-77",
        "Produto: Servico fiscal demonstrativo",
        f"Valor total da nota: {total}",
        "Valor do ICMS: R$ 180,00",
        "Valor do PIS: R$ 16,50",
        "Valor do COFINS: R$ 76,00",
    ]
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(72, y, lines[0])
    pdf.setFont("Helvetica", 10)
    for line in lines[1:]:
        y -= 24
        pdf.drawString(72, y, line)
    pdf.save()


class PdfExtractionSampleTests(unittest.TestCase):
    def test_textual_fake_invoice_pdf_extracts_labeled_fields(self):
        key = "35260412345678000190550010000000011000000010"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nota_fiscal_ficticia.pdf"
            write_fake_invoice_pdf(path, key=key)

            data = PdfExtractor().parse(path)

        self.assertEqual(data.source_type, "pdf")
        self.assertEqual(data.invoice_key, key)
        self.assertEqual(data.issue_date, "2026-03-15")
        self.assertEqual(data.issuer_name, "Fornecedor PDF Teste Ltda")
        self.assertEqual(data.issuer_document, "12.345.678/0001-90")
        self.assertEqual(data.recipient_name, "Cliente PDF Teste SA")
        self.assertEqual(data.recipient_document, "00.999.888/0001-77")
        self.assertEqual(data.total_amount, 1234.56)
        self.assertEqual(data.taxes["ICMS"], 180.0)
        self.assertEqual(data.taxes["PIS"], 16.5)
        self.assertEqual(data.taxes["COFINS"], 76.0)
        self.assertTrue(any("PDF não fornece itens" in warning for warning in data.warnings))

    def test_fake_invoice_pdf_import_persists_extracted_payload(self):
        key = "35260412345678000190550010000000021000000020"
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "nota_fiscal_importacao.pdf"
            write_fake_invoice_pdf(pdf_path, key=key, total="R$ 2.500,00")
            engine = create_engine(tmp)
            engine.initialize()
            session = engine.auth.login("admin", "Admin@12345")
            client = engine.tool("clients").create_client(session, "Cliente PDF", "00.999.888/0001-77")

            result = engine.tool("invoices").import_files(session, client.id, [pdf_path], auto_analyze=False)
            document = result["imported"][0]
            payload = json.loads(document.payload_json)

        self.assertEqual(document.file_type, "pdf")
        self.assertEqual(document.parser_status, "ok")
        self.assertEqual(document.invoice_key, key)
        self.assertEqual(document.total_amount, 2500.0)
        self.assertEqual(payload["issuer_name"], "Fornecedor PDF Teste Ltda")
        self.assertEqual(payload["recipient_document"], "00.999.888/0001-77")
        self.assertEqual(payload["taxes"]["ICMS"], 180.0)


if __name__ == "__main__":
    unittest.main()
