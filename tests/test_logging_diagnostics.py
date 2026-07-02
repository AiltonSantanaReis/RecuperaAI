from __future__ import annotations

import contextlib
import logging
import tempfile
import unittest
from logging.handlers import RotatingFileHandler as RealRotatingFileHandler
from pathlib import Path
from unittest import mock

from recuperaai.core.logging_config import current_log_path, error_text, log_exception, setup_logging, shutdown_logging
from recuperaai.core.paths import AppPaths
from recuperaai.app import main, _emit


class LoggingDiagnosticsTests(unittest.TestCase):
    def tearDown(self):
        shutdown_logging()

    def test_setup_logging_writes_persistent_log_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths.create(base_dir=tmp)
            log_path = setup_logging(paths, level="DEBUG")
            try:
                logging.getLogger("recuperaai.test").debug("mensagem de teste do log")
                for handler in logging.getLogger().handlers:
                    handler.flush()
                self.assertTrue(log_path.exists())
                self.assertEqual(current_log_path(), log_path)
                self.assertIn("mensagem de teste do log", log_path.read_text(encoding="utf-8"))
            finally:
                # No Windows, TemporaryDirectory não consegue remover a pasta
                # enquanto o FileHandler ainda mantém recuperaai_app.log aberto.
                shutdown_logging()

    def test_setup_logging_falls_back_when_primary_log_file_is_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths.create(base_dir=tmp)
            attempts: list[Path] = []

            def build_handler(filename, *args, **kwargs):
                attempts.append(Path(filename))
                if len(attempts) == 1:
                    raise PermissionError("log bloqueado")
                return RealRotatingFileHandler(filename, *args, **kwargs)

            with mock.patch("recuperaai.core.logging_config.RotatingFileHandler", side_effect=build_handler):
                log_path = setup_logging(paths, level="DEBUG")
                try:
                    logging.getLogger("recuperaai.test").debug("log em fallback")
                    for handler in logging.getLogger().handlers:
                        handler.flush()
                    self.assertEqual(len(attempts), 2)
                    self.assertEqual(attempts[0], paths.logs / "recuperaai_app.log")
                    self.assertNotEqual(log_path, attempts[0])
                    self.assertTrue(log_path.exists())
                    self.assertIn("log em fallback", log_path.read_text(encoding="utf-8"))
                finally:
                    shutdown_logging()

    def test_shutdown_logging_closes_recuperaai_handlers(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths.create(base_dir=tmp)
            setup_logging(paths, level="DEBUG")
            self.assertTrue(any(getattr(handler, "_recuperaai_handler", False) for handler in logging.getLogger().handlers))
            shutdown_logging()
            self.assertFalse(any(getattr(handler, "_recuperaai_handler", False) for handler in logging.getLogger().handlers))
            self.assertIsNone(current_log_path())

    def test_error_text_never_returns_blank_message(self):
        exc = Exception()
        msg = error_text(exc, "ação de teste")
        self.assertIn("Não foi possível concluir", msg)
        self.assertIn("Erro interno sem mensagem detalhada", msg)

    def test_log_exception_records_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths.create(base_dir=tmp)
            log_path = setup_logging(paths, level="DEBUG")
            try:
                try:
                    raise RuntimeError("falha controlada")
                except RuntimeError as exc:
                    log_exception("teste controlado", exc, user="tester")
                for handler in logging.getLogger().handlers:
                    handler.flush()
                content = log_path.read_text(encoding="utf-8")
                self.assertIn("teste controlado", content)
                self.assertIn("falha controlada", content)
                self.assertIn("Traceback", content)
            finally:
                # Fecha o arquivo antes da limpeza automática da pasta temporária.
                shutdown_logging()


    def test_emit_does_not_crash_when_stdout_is_invalid(self):
        class BrokenStdout:
            def write(self, _text):
                raise OSError(22, "Invalid argument")

            def flush(self):
                raise OSError(22, "Invalid argument")

        with tempfile.TemporaryDirectory() as tmp:
            out_file = Path(tmp) / "saida.txt"
            import sys
            original_stdout = sys.stdout
            try:
                sys.stdout = BrokenStdout()
                _emit("RecuperaAI teste", str(out_file))
            finally:
                sys.stdout = original_stdout
            self.assertEqual(out_file.read_text(encoding="utf-8").strip(), "RecuperaAI teste")

    def test_cli_version_can_write_to_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_file = Path(tmp) / "versao.txt"
            code = main(["--version", "--output-file", str(out_file)])
            self.assertEqual(code, 0)
            self.assertIn("RecuperaAI 1.0.0-etapa11.0", out_file.read_text(encoding="utf-8"))

    def test_cli_ignores_unknown_arguments_instead_of_exiting_code_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = main(["--diagnostics", "--base-dir", tmp, "--argumento-antigo-ou-desconhecido"])
            self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
