from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from recuperaai.bootstrap import create_engine


class _FakeFiscalApi:
    def __init__(self, response: dict[str, Any] | None = None, *, status: int = 200) -> None:
        self.response = response or {}
        self.status = status
        self.requests: list[dict[str, Any]] = []
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "_FakeFiscalApi":
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0") or "0")
                raw_body = self.rfile.read(length)
                try:
                    payload = json.loads(raw_body.decode("utf-8"))
                except Exception:
                    payload = None
                owner.requests.append({
                    "path": self.path,
                    "headers": dict(self.headers),
                    "payload": payload,
                })
                body = json.dumps(owner.response).encode("utf-8")
                self.send_response(owner.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    @property
    def url(self) -> str:
        if self._server is None:
            raise RuntimeError("Servidor fake não iniciado.")
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)


class ExternalApiIntegrationTests(unittest.TestCase):
    def test_import_and_analysis_send_payload_to_external_api_and_persist_response(self):
        response = {
            "findings": [{
                "severity": "critical",
                "code": "API_CREDITO_ICMS",
                "title": "Crédito ICMS simulado",
                "message": "Resposta simulada da API para conferência.",
                "amount": "123.45",
                "field": "icms",
            }],
            "opportunities": [{
                "title": "Oportunidade simulada",
                "description": "Valor recuperável calculado pela API fake.",
                "amount": 321.0,
                "confidence": "alta",
            }],
        }

        with _FakeFiscalApi(response) as api, tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(tmp)
            engine.initialize()
            session = engine.auth.login("admin", "Admin@12345")
            engine.tool("settings").update_api(session, True, api.url, "token-teste")
            client = engine.tool("clients").create_client(session, "Cliente API Fake", "12.345.678/0001-90")

            result = engine.tool("invoices").import_files(
                session,
                client.id,
                [Path(__file__).with_name("sample_nfe.xml")],
            )

            self.assertEqual(result["failed"], [])
            self.assertEqual(len(result["imported"]), 1)
            self.assertEqual(len(api.requests), 1)
            request = api.requests[0]
            self.assertEqual(request["path"], "/analyze")
            self.assertEqual(request["headers"].get("Authorization"), "Bearer token-teste")
            self.assertEqual(request["payload"]["schema_version"], "1.0")
            self.assertEqual(request["payload"]["client"]["name"], "Cliente API Fake")
            self.assertEqual(request["payload"]["document"]["file_name"], "sample_nfe.xml")
            self.assertEqual(
                request["payload"]["invoice"]["invoice_key"],
                "35240112345678000190550010000012341000012345",
            )

            findings = engine.tool("analysis").list_for_client(session, client.id)
            by_code = {finding["code"]: finding for finding in findings}
            self.assertEqual(by_code["API_CREDITO_ICMS"]["source"], "api")
            self.assertAlmostEqual(by_code["API_CREDITO_ICMS"]["amount"], 123.45)
            self.assertEqual(by_code["POSSIVEL_OPORTUNIDADE"]["source"], "api")
            self.assertAlmostEqual(by_code["POSSIVEL_OPORTUNIDADE"]["amount"], 321.0)
            self.assertIn("Confiança informada: alta.", by_code["POSSIVEL_OPORTUNIDADE"]["message"])

            workspace = engine.tool("clients").get_client_workspace(session, client.id)
            dashboard = engine.tool("analysis").dashboard(session)
            self.assertAlmostEqual(workspace["summary"]["opportunities"]["api_estimated_total"], 444.45)
            self.assertAlmostEqual(dashboard["opportunities"]["api_estimated_total"], 444.45)
            self.assertEqual(dashboard["opportunities_by_client"][0]["client_id"], client.id)

    def test_external_api_failure_is_recorded_without_breaking_invoice_import(self):
        with _FakeFiscalApi({"error": "indisponível"}, status=500) as api, tempfile.TemporaryDirectory() as tmp:
            engine = create_engine(tmp)
            engine.initialize()
            session = engine.auth.login("admin", "Admin@12345")
            engine.tool("settings").update_api(session, True, api.url, "token-teste")
            client = engine.tool("clients").create_client(session, "Cliente API Fora", "98.765.432/0001-10")

            result = engine.tool("invoices").import_files(
                session,
                client.id,
                [Path(__file__).with_name("sample_nfe.xml")],
            )

            self.assertEqual(result["failed"], [])
            self.assertEqual(len(result["imported"]), 1)
            self.assertEqual(len(api.requests), 3)
            findings = engine.tool("analysis").list_for_client(session, client.id)
            by_code = {finding["code"]: finding for finding in findings}
            self.assertIn("API_INDISPONIVEL", by_code)
            self.assertEqual(by_code["API_INDISPONIVEL"]["source"], "api")
            self.assertIn("API de inconsistências", by_code["API_INDISPONIVEL"]["message"])


if __name__ == "__main__":
    unittest.main()
