import unittest

from recuperaai.fiscal.api_client import FiscalApiClient


class FiscalApiContractTests(unittest.TestCase):
    def test_build_analysis_payload_includes_context_and_readiness(self):
        payload = FiscalApiClient.build_analysis_payload(
            {
                'invoice_key': '123',
                'issuer_state': 'SP',
                'total_amount': 100.0,
                'items': [{'ncm': '01012100', 'cfop': '5102'}],
                'taxes': {'ICMS': 18.0},
            },
            client={'name': 'Cliente Teste', 'document': '00.000.000/0001-00'},
            document={'file_name': 'nota.xml'},
        )

        self.assertEqual(payload['schema_version'], '1.0')
        self.assertEqual(payload['client']['name'], 'Cliente Teste')
        self.assertEqual(payload['document']['file_name'], 'nota.xml')
        self.assertEqual(payload['invoice']['invoice_key'], '123')
        self.assertEqual(payload['data_quality']['confidence'], 'limited')
        self.assertTrue(payload['readiness']['has_items'])
        self.assertTrue(payload['readiness']['has_taxes'])
        self.assertIn('documento do emitente', payload['readiness']['missing'])

    def test_pdf_payload_marks_missing_structured_data_for_external_review(self):
        payload = FiscalApiClient.build_analysis_payload(
            {
                'source_type': 'pdf',
                'total_amount': 3000.0,
                'raw_text': 'Valor total da nota: R$ 3.000,00',
                'warnings': ['PDF sem itens estruturados.'],
            },
            client={'name': 'Cliente Teste'},
            document={'file_name': 'nota.pdf'},
        )

        self.assertEqual(payload['data_quality']['source_type'], 'pdf')
        self.assertEqual(payload['data_quality']['confidence'], 'requires_document_review')
        self.assertTrue(payload['data_quality']['has_raw_text'])
        self.assertIn('itens da nota', payload['readiness']['missing'])
        self.assertIn('impostos destacados', payload['readiness']['missing'])

    def test_normalize_response_accepts_findings_and_opportunities(self):
        findings = FiscalApiClient.normalize_response({
            'findings': [{
                'severity': 'warning',
                'code': 'CFOP_REVISAR',
                'title': 'CFOP requer revisão',
                'message': 'Operação pode exigir conferência.',
                'amount': '12.50',
            }],
            'opportunities': [{
                'title': 'Possível crédito',
                'description': 'Há indício de valor recuperável.',
                'amount': 35,
                'confidence': 'média',
            }],
        })

        self.assertEqual(len(findings), 2)
        self.assertEqual(findings[0]['source'], 'api')
        self.assertEqual(findings[0]['amount'], 12.5)
        self.assertEqual(findings[1]['code'], 'POSSIVEL_OPORTUNIDADE')
        self.assertIn('Confiança informada: média.', findings[1]['message'])


if __name__ == '__main__':
    unittest.main()
