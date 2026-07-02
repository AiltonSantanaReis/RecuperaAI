from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from recuperaai.app import main
from recuperaai.core.paths import AppPaths
from recuperaai.core.logging_config import shutdown_logging
from recuperaai.diagnostics import run_smoke_test, runtime_info
from scripts.package_windows_release import create_release_package


class Stage08PackagingTests(unittest.TestCase):
    def tearDown(self):
        shutdown_logging()

    def test_headless_smoke_test_initializes_core_without_gui(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_smoke_test(base_dir=tmp, keep_data=True)
            self.assertTrue(result["ok"])
            self.assertIn("engine_initialized", result["checks"])
            self.assertIn("default_admin_login_ok", result["checks"])
            self.assertTrue(Path(result["database"]).exists())
            self.assertTrue(Path(result["backup"]).exists())

    def test_cli_smoke_test_returns_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main(["--smoke-test", "--base-dir", tmp]), 0)
            self.assertIn('"ok": true', out.getvalue())

    def test_diagnostics_exposes_version_and_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            info = runtime_info(base_dir=tmp)
            self.assertEqual(info["app"], "RecuperaAI")
            self.assertIn("version", info)
            self.assertEqual(info["paths"]["base"], str(Path(tmp).resolve()))

    def test_portable_paths_use_dados_folder_when_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            current = Path.cwd()
            try:
                # AppPaths.portable usa o diretório corrente quando não está congelado.
                import os
                os.chdir(tmp)
                paths = AppPaths.create(portable=True)
                self.assertEqual(paths.base, Path(tmp).resolve() / "dados")
                self.assertTrue(paths.database.parent.exists())
            finally:
                os.chdir(current)


    def test_windows_build_scripts_do_not_have_known_powershell_variable_parse_bug(self):
        ps1 = Path("scripts/build_windows.ps1").read_text(encoding="utf-8")
        bat = Path("build_windows.bat").read_text(encoding="utf-8")
        self.assertNotIn("$LASTEXITCODE:", ps1)
        self.assertIn("${LASTEXITCODE}:", ps1)
        self.assertIn('> "%BUILD_LOG%" 2>&1', bat)
        self.assertIn('type "%BUILD_LOG%"', bat)

    def test_release_packager_creates_customer_zip_from_dist_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dist = root / "dist" / "RecuperaAI"
            dist.mkdir(parents=True)
            exe = dist / "RecuperaAI.exe"
            exe.write_bytes(b"fake exe for packaging test")
            cli = dist / "RecuperaAI_CLI.exe"
            cli.write_bytes(b"fake cli exe for packaging test")
            (dist / "recuperaai_internal.txt").write_text("ok", encoding="utf-8")
            out = root / "release"

            zip_path = create_release_package(dist, out, skip_smoke=True)

            self.assertTrue(zip_path.exists())
            with zipfile.ZipFile(zip_path) as zf:
                names = set(zf.namelist())
            self.assertTrue(any(name.endswith("RecuperaAI/RecuperaAI.exe") for name in names))
            self.assertTrue(any(name.endswith("RecuperaAI/RecuperaAI_CLI.exe") for name in names))
            self.assertTrue(any(name.endswith("CHECKSUMS_SHA256.txt") for name in names))
            self.assertTrue(any(name.endswith("VERSAO.txt") for name in names))
            self.assertTrue(any(name.endswith("executar_com_log.bat") for name in names))
            self.assertTrue(any(name.endswith("diagnostico_rapido.bat") for name in names))
            self.assertTrue(any(name.endswith("README.md") for name in names))
            self.assertTrue(any(name.endswith("ARCHITECTURE.md") for name in names))
            self.assertFalse(any(name.endswith("README_DIAGNOSTICO_ERROS.md") for name in names))
            self.assertFalse(any(name.endswith("README_TESTES_AUDITORIA.md") for name in names))
            self.assertFalse(any(name.endswith("README_BUILD_WINDOWS_ERRO.md") for name in names))
            self.assertFalse(any(name.endswith("AUDITORIA_PROJETO_ATUAL.md") for name in names))
            self.assertFalse(any(name.endswith("README_TECNICO.md") for name in names))
            self.assertFalse(any(name.endswith("MATRIZ_FUNCIONAL.md") for name in names))
            self.assertFalse(any(name.endswith("MATRIZ_PERMISSOES_ATUAL.md") for name in names))
            self.assertFalse(any(name.endswith("MATRIZ_RELATORIOS_ETAPA07.md") for name in names))

    def test_diagnostic_scripts_prefer_source_tree_before_stale_exe(self):
        run_bat = Path("executar_com_log.bat").read_text(encoding="utf-8")
        diag_bat = Path("diagnostico_rapido.bat").read_text(encoding="utf-8")
        self.assertIn('if exist "%CD%\\recuperaai\\app.py" set SOURCE_MODE=1', run_bat)
        self.assertIn('if "%SOURCE_MODE%"=="1" if not defined HEADLESS_CMD set HEADLESS_CMD=python -m recuperaai', run_bat)
        self.assertLess(run_bat.index('if "%SOURCE_MODE%"=="1"'), run_bat.index('if not defined HEADLESS_CMD if exist "%CD%\\RecuperaAI\\RecuperaAI_CLI.exe"'))
        self.assertIn('--version', run_bat)
        self.assertIn('--diagnostics', run_bat)
        self.assertIn('codigo 2', run_bat.lower())
        self.assertIn('SOURCE_MODE=1', diag_bat)

    def test_stage085_scripts_detect_stale_exe_and_avoid_new_log_args_when_needed(self):
        run_bat = Path("executar_com_log.bat").read_text(encoding="utf-8")
        diag_bat = Path("diagnostico_rapido.bat").read_text(encoding="utf-8")
        self.assertIn("Versao detectada", run_bat)
        self.assertIn("SUPPORTS_LOG_ARGS", run_bat)
        self.assertIn("EXTRA_LOG_ARGS", run_bat)
        self.assertIn("RecuperaAI_CLI.exe", run_bat)
        self.assertIn("etapa", run_bat)
        self.assertIn("dist\\RecuperaAI\\RecuperaAI.exe", run_bat)
        self.assertIn("limpar_build_antigo.bat", run_bat)
        self.assertIn("RecuperaAI_CLI.exe", diag_bat)
        self.assertIn("EXTRA_LOG_ARGS", diag_bat)
        self.assertTrue(Path("limpar_build_antigo.bat").exists())

    def test_build_script_checks_exe_version_matches_source_and_cleans_release(self):
        ps1 = Path("scripts/build_windows.ps1").read_text(encoding="utf-8")
        self.assertIn("Versao do codigo-fonte", ps1)
        self.assertIn("Versao do executavel auxiliar", ps1)
        self.assertIn("EXE gerado nao corresponde", ps1)
        self.assertIn("Remove-Item -Path build, dist, release", ps1)
        self.assertIn("--output-file", ps1)
        self.assertIn("RecuperaAI_CLI.exe", ps1)
        self.assertIn("RecuperaAI_EXE_Version_", ps1)
        self.assertIn("Invoke-Capture", ps1)
        packager = Path("scripts/package_windows_release.py").read_text(encoding="utf-8")
        self.assertIn("--output-file", packager)
        self.assertIn("RecuperaAI_CLI.exe", packager)
        self.assertIn("README.md", packager)
        self.assertIn("ARCHITECTURE.md", packager)
        self.assertNotIn("README_TESTES_AUDITORIA.md", packager)
        self.assertNotIn("AUDITORIA_PROJETO_ATUAL.md", packager)
        self.assertNotIn("README_TECNICO.md", packager)
        self.assertNotIn("MATRIZ_FUNCIONAL.md", packager)
        self.assertNotIn("MATRIZ_PERMISSOES_ATUAL.md", packager)
        self.assertNotIn("MATRIZ_RELATORIOS_ETAPA07.md", packager)

    def test_run_tests_script_uses_explicit_test_discovery_and_temp_smoke_dir(self):
        script = Path("run_tests.bat").read_text(encoding="utf-8")
        self.assertIn("unittest discover -s tests", script)
        self.assertIn("--smoke-test --base-dir", script)
        self.assertIn("%TEMP%\\RecuperaAI_Source_Smoke_", script)
        self.assertIn("rmdir /s /q", script)

    def test_package_verifier_uses_cli_exe_with_working_directory(self):
        script = Path("scripts/verify_windows_package.ps1").read_text(encoding="utf-8")
        self.assertIn('Filter "RecuperaAI_CLI.exe"', script)
        self.assertIn("Push-Location $cliExe.DirectoryName", script)
        self.assertIn("& $cliExe.FullName --smoke-test --base-dir $base", script)


if __name__ == "__main__":
    unittest.main()
