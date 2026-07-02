from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from recuperaai.bootstrap import create_engine
from recuperaai.build_info import version_label
from recuperaai.core.logging_config import install_global_exception_hooks, setup_logging, shutdown_logging
from recuperaai.diagnostics import run_smoke_test, runtime_info, to_json


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="RecuperaAI", description="RecuperaAI Desktop Local")
    parser.add_argument("--version", action="store_true", help="Mostra a versão e encerra.")
    parser.add_argument("--diagnostics", action="store_true", help="Mostra diagnóstico headless e encerra.")
    parser.add_argument("--smoke-test", action="store_true", help="Executa teste headless de inicialização e encerra.")
    parser.add_argument("--base-dir", help="Diretório de dados para diagnóstico/teste/execução.")
    parser.add_argument("--portable", action="store_true", help="Usa a pasta dados ao lado do executável.")
    parser.add_argument("--keep-smoke-data", action="store_true", help="Mantém dados temporários do smoke test.")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Nível do log técnico.")
    parser.add_argument("--log-console", action="store_true", help="Também imprime o log no console quando houver console disponível.")
    parser.add_argument("--output-file", help="Grava a saída headless em arquivo. Útil para executável Windows sem console.")
    parser.add_argument("--visual-check", action="store_true", help="Prepara dados e checklist para validação visual guiada no Windows.")
    parser.add_argument("--checklist-output", help="Caminho opcional do checklist de validação visual.")
    return parser


def _emit(text: str, output_file: str | None = None) -> None:
    """Emite texto de comandos headless sem derrubar EXE Windows sem console.

    Em builds PyInstaller com ``console=False`` o ``sys.stdout`` pode existir,
    mas ``write`` ou ``flush`` podem levantar ``OSError: [Errno 22]``.
    Isso não deve abrir a janela "Unhandled exception in script" quando o
    usuário ou o build chamam ``RecuperaAI.exe --version``.
    """
    if output_file:
        try:
            out_path = Path(output_file)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(text + "\n", encoding="utf-8")
        except Exception:
            logging.getLogger("recuperaai.app").exception("Falha ao gravar output_file=%s", output_file)

    stream = getattr(sys, "stdout", None)
    if stream is None:
        return
    try:
        stream.write(text + "\n")
        stream.flush()
    except (OSError, ValueError):
        # EXE windowed sem console: não há saída padrão válida.
        logging.getLogger("recuperaai.app").debug("Saída padrão indisponível; mensagem não impressa.", exc_info=True)


def main(argv: list[str] | None = None) -> int:
    try:
        return _main_impl(argv)
    finally:
        shutdown_logging()


def _main_impl(argv: list[str] | None = None) -> int:
    parser = _parser()
    args, unknown_args = parser.parse_known_args(argv)

    if args.version:
        _emit(version_label(), args.output_file)
        return 0

    engine = create_engine(base_dir=args.base_dir, portable=args.portable)
    log_path = setup_logging(engine.paths, level=args.log_level, console=args.log_console)
    install_global_exception_hooks()
    logger = logging.getLogger("recuperaai.app")
    logger.info("Argumentos: diagnostics=%s smoke_test=%s portable=%s base_dir=%s unknown=%s", args.diagnostics, args.smoke_test, args.portable, args.base_dir, unknown_args)
    if unknown_args:
        logger.warning("Argumentos desconhecidos ignorados para evitar encerramento codigo 2: %s", unknown_args)
        _emit("Aviso: alguns argumentos desconhecidos foram ignorados. Veja o log técnico para detalhes.", args.output_file)

    if args.diagnostics:
        logger.info("Executando diagnóstico headless.")
        _emit(to_json(runtime_info(base_dir=args.base_dir, portable=args.portable, log_path=str(log_path))), args.output_file)
        return 0

    if args.visual_check:
        logger.info("Preparando validação visual guiada.")
        from recuperaai.validation.visual_validation import prepare_visual_validation
        result = prepare_visual_validation(base_dir=args.base_dir, portable=args.portable, checklist_output=args.checklist_output)
        result["log_path"] = str(log_path)
        _emit(to_json(result), args.output_file)
        return 0 if result.get("ok") else 1

    if args.smoke_test:
        logger.info("Executando smoke test headless.")
        result = run_smoke_test(base_dir=args.base_dir, keep_data=args.keep_smoke_data, portable=args.portable)
        result["log_path"] = str(log_path)
        _emit(to_json(result), args.output_file)
        return 0 if result.get("ok") else 1

    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        from recuperaai.ui.login_window import LoginWindow
        from recuperaai.ui.main_window import MainWindow
        from recuperaai.ui.splash import SplashScreen
    except Exception as exc:  # pragma: no cover - depende do ambiente grafico
        logger.exception("Falha ao importar a interface gráfica.")
        _emit("Nao foi possivel iniciar a interface grafica.", args.output_file)
        _emit("Instale as dependencias com: pip install -r requirements.txt", args.output_file)
        _emit(f"Detalhe: {exc}", args.output_file)
        _emit(f"Log: {log_path}", args.output_file)
        return 1

    app = QApplication(sys.argv)
    app.setApplicationName("RecuperaAI")
    app.setOrganizationName("RecuperaAI")

    try:
        splash = SplashScreen()
        splash.show_message("Preparando ambiente local...")
        app.processEvents()
        logger.info("Inicializando engine.")
        engine.initialize()

        splash.show_message("Carregando segurança e banco de dados...")
        app.processEvents()

        login = LoginWindow(engine)
        if not login.exec():
            logger.info("Login cancelado pelo usuário.")
            return 0

        splash.show_message("Abrindo painel principal...")
        app.processEvents()

        window = MainWindow(engine, login.session)
        window.showMaximized()
        splash.finish(window)
        logger.info("Interface principal aberta para usuário=%s perfil=%s", login.session.user.username, login.session.role)
        return app.exec()
    except Exception as exc:  # pragma: no cover - depende de GUI
        logger.exception("Falha crítica durante inicialização da interface.")
        QMessageBox.critical(
            None,
            "RecuperaAI - erro ao iniciar",
            "O sistema encontrou um erro ao iniciar.\n\n"
            f"Detalhe: {str(exc) or exc.__class__.__name__}\n\n"
            f"Arquivo de diagnóstico:\n{log_path}",
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
