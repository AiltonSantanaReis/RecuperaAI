from __future__ import annotations

from pathlib import Path

from recuperaai.fiscal.models import InvoiceData
from recuperaai.fiscal.pdf_extractor import PdfExtractor
from recuperaai.fiscal.xml_parser import FiscalXmlParser


class FiscalDocumentNormalizer:
    def __init__(self) -> None:
        self.xml = FiscalXmlParser()
        self.pdf = PdfExtractor()

    def parse_file(self, path: Path) -> InvoiceData:
        suffix = path.suffix.lower()
        if suffix == '.xml':
            return self.xml.parse(path)
        if suffix == '.pdf':
            return self.pdf.parse(path)
        raise ValueError(f'Formato não suportado: {suffix}')
