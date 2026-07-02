from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIST = PROJECT_ROOT / "dist" / "RecuperaAI"
DEFAULT_RELEASE = PROJECT_ROOT / "release"
EXE_NAME = "RecuperaAI.exe"
CLI_EXE_NAME = "RecuperaAI_CLI.exe"


def _safe_version_label() -> str:
    try:
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from recuperaai.build_info import APP_VERSION
        return APP_VERSION.replace(".", "_").replace("-", "_")
    except Exception:
        return datetime.now().strftime("%Y%m%d_%H%M%S")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_manifest(package_root: Path, dist_dir: Path) -> Path:
    manifest = package_root / "CHECKSUMS_SHA256.txt"
    lines: list[str] = []
    for path in sorted(dist_dir.rglob("*")):
        if path.is_file():
            rel = path.relative_to(package_root).as_posix()
            lines.append(f"{sha256_file(path)}  {rel}")
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest


def run_exe_smoke_test(exe_path: Path, cli_exe_path: Path | None = None) -> None:
    smoke_dir = Path(tempfile.mkdtemp(prefix="recuperaai_exe_smoke_"))
    output_file = smoke_dir / "smoke_output.json"
    try:
        completed = subprocess.run(
            [str(cli_exe_path or exe_path), "--smoke-test", "--base-dir", str(smoke_dir), "--output-file", str(output_file)],
            cwd=str(exe_path.parent),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=120,
        )
        output = completed.stdout or ""
        if output_file.exists():
            output = output_file.read_text(encoding="utf-8", errors="replace") + output
        if completed.returncode != 0:
            raise RuntimeError("Smoke test do executável falhou:\n" + output)
    finally:
        shutil.rmtree(smoke_dir, ignore_errors=True)


def create_release_package(dist_dir: Path, output_dir: Path, skip_smoke: bool = False) -> Path:
    dist_dir = dist_dir.resolve()
    exe_path = dist_dir / EXE_NAME
    cli_exe_path = dist_dir / CLI_EXE_NAME
    if not exe_path.exists():
        raise FileNotFoundError(f"Executável principal não encontrado: {exe_path}")
    if not cli_exe_path.exists():
        raise FileNotFoundError(f"Executável auxiliar de diagnóstico não encontrado: {cli_exe_path}")

    if not skip_smoke:
        run_exe_smoke_test(exe_path, cli_exe_path)

    output_dir.mkdir(parents=True, exist_ok=True)
    version = _safe_version_label()
    package_name = f"RecuperaAI_Desktop_{version}"
    package_root = output_dir / package_name
    if package_root.exists():
        shutil.rmtree(package_root)
    package_root.mkdir(parents=True)

    packaged_app = package_root / "RecuperaAI"
    shutil.copytree(dist_dir, packaged_app)

    for doc_name in ["README.md", "ARCHITECTURE.md"]:
        src = PROJECT_ROOT / doc_name
        if src.exists():
            shutil.copy2(src, package_root / doc_name)

    for script_name in ["executar_com_log.bat", "diagnostico_rapido.bat", "validacao_visual.bat"]:
        src = PROJECT_ROOT / script_name
        if src.exists():
            shutil.copy2(src, package_root / script_name)

    (package_root / "VERSAO.txt").write_text(
        f"RecuperaAI Desktop\nGerado em: {datetime.now():%d/%m/%Y %H:%M:%S}\nVersão: {version}\n",
        encoding="utf-8",
    )
    write_manifest(package_root, packaged_app)

    zip_path = output_dir / f"{package_name}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(package_root.rglob("*")):
            if file.is_file():
                zf.write(file, file.relative_to(output_dir))
    return zip_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Empacota a pasta dist/RecuperaAI para teste do cliente.")
    parser.add_argument("--dist", default=str(DEFAULT_DIST), help="Pasta dist/RecuperaAI gerada pelo PyInstaller.")
    parser.add_argument("--output", default=str(DEFAULT_RELEASE), help="Pasta de saída do pacote final.")
    parser.add_argument("--skip-smoke", action="store_true", help="Não executa smoke test do .exe antes de zipar.")
    args = parser.parse_args(argv)

    try:
        zip_path = create_release_package(Path(args.dist), Path(args.output), skip_smoke=args.skip_smoke)
    except Exception as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1
    print(f"Pacote criado: {zip_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
