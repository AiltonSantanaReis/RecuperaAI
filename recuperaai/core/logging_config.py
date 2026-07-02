from __future__ import annotations

import logging
import platform
import sys
import tempfile
import threading
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType
from typing import Any

from recuperaai.build_info import version_label
from recuperaai.core.paths import AppPaths

_LOG_PATH: Path | None = None
_HOOKS_INSTALLED = False


def current_log_path() -> Path | None:
    return _LOG_PATH


def _level_from_text(level: str | None) -> int:
    value = (level or "INFO").upper().strip()
    return getattr(logging, value, logging.INFO)


def setup_logging(paths: AppPaths, level: str | None = "INFO", console: bool = False) -> Path:
    """Configura log persistente do aplicativo.

    O log é criado sempre em ``paths.logs``. Em caso de falha visual no Windows,
    este arquivo é o principal material de diagnóstico para descobrir qual ação
    quebrou e qual exceção técnica ocorreu.
    """
    global _LOG_PATH

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Evita handlers duplicados quando testes ou smoke-tests chamam main mais de uma vez.
    for handler in list(root.handlers):
        if getattr(handler, "_recuperaai_handler", False):
            root.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass

    log_path = paths.logs / "recuperaai_app.log"
    try:
        paths.logs.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
    except OSError:
        fallback_dir = Path(tempfile.gettempdir()) / "RecuperaAI" / "logs"
        fallback_dir.mkdir(parents=True, exist_ok=True)
        log_path = fallback_dir / "recuperaai_app.log"
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
    _LOG_PATH = log_path
    file_handler.setLevel(_level_from_text(level))
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    ))
    file_handler._recuperaai_handler = True  # type: ignore[attr-defined]
    root.addHandler(file_handler)

    if console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(_level_from_text(level))
        console_handler.setFormatter(logging.Formatter("%(levelname)s | %(name)s | %(message)s"))
        console_handler._recuperaai_handler = True  # type: ignore[attr-defined]
        root.addHandler(console_handler)

    logger = logging.getLogger("recuperaai")
    logger.info("Aplicativo iniciado: %s", version_label())
    logger.info("Python: %s | Plataforma: %s", sys.version.replace("\n", " "), platform.platform())
    logger.info("Executável: %s | frozen=%s", Path(sys.executable).resolve(), bool(getattr(sys, "frozen", False)))
    logger.info("Base de dados: %s", paths.base)
    logger.info("Arquivo de log: %s", log_path)
    return log_path


def shutdown_logging() -> None:
    """Fecha handlers do RecuperaAI para liberar arquivos de log no Windows.

    Em Windows, handlers de arquivo mantidos abertos impedem a remoção de
    diretórios temporários usados pelos testes e podem travar limpeza de build.
    Esta função precisa ser chamada antes de apagar pastas temporárias que
    contenham ``recuperaai_app.log``.
    """
    global _LOG_PATH

    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_recuperaai_handler", False):
            root.removeHandler(handler)
            try:
                handler.flush()
            except Exception:
                pass
            try:
                handler.close()
            except Exception:
                pass
    _LOG_PATH = None


def install_global_exception_hooks() -> None:
    """Registra exceções não tratadas no log antes de o aplicativo encerrar."""
    global _HOOKS_INSTALLED
    if _HOOKS_INSTALLED:
        return
    _HOOKS_INSTALLED = True

    original_excepthook = sys.excepthook

    def excepthook(exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None) -> None:
        logging.getLogger("recuperaai.unhandled").critical(
            "Exceção não tratada no processo principal",
            exc_info=(exc_type, exc, tb),
        )
        original_excepthook(exc_type, exc, tb)

    sys.excepthook = excepthook

    if hasattr(threading, "excepthook"):
        original_thread_hook = threading.excepthook

        def thread_hook(args: threading.ExceptHookArgs) -> None:
            logging.getLogger("recuperaai.unhandled").critical(
                "Exceção não tratada em thread: %s",
                getattr(args.thread, "name", "thread"),
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
            )
            original_thread_hook(args)

        threading.excepthook = thread_hook


def log_exception(action: str, exc: BaseException, **context: Any) -> None:
    details = " | ".join(f"{key}={value}" for key, value in context.items() if value not in (None, ""))
    if details:
        logging.getLogger("recuperaai.ui").exception("Falha na ação '%s' (%s)", action, details, exc_info=exc)
    else:
        logging.getLogger("recuperaai.ui").exception("Falha na ação '%s'", action, exc_info=exc)


def error_text(exc: BaseException, action: str | None = None) -> str:
    """Gera mensagem de erro nunca vazia para exibição ao usuário."""
    raw = str(exc).strip()
    if raw:
        message = raw
    else:
        message = f"Erro interno sem mensagem detalhada ({exc.__class__.__name__})."

    prefix = f"Não foi possível concluir: {action}." if action else "Não foi possível concluir a operação."
    log_path = current_log_path()
    if log_path:
        return f"{prefix}\n\n{message}\n\nArquivo de diagnóstico:\n{log_path}"
    return f"{prefix}\n\n{message}"


def traceback_text(exc: BaseException) -> str:
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
