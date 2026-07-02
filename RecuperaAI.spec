# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

block_cipher = None
project_dir = Path.cwd()

_common_exe_kwargs = dict(
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/recuperaai.ico' if Path('assets/recuperaai.ico').exists() else None,
)

a = Analysis(
    ['recuperaai/__main__.py'],
    pathex=[str(project_dir)],
    binaries=[],
    datas=[
        ('recuperaai/ui/styles.qss', 'recuperaai/ui'),
        ('recuperaai/ui/chevron_down.svg', 'recuperaai/ui'),
        ('recuperaai/database/schema.sql', 'recuperaai/database'),
        ('assets', 'assets'),
    ],
    hiddenimports=[
        'pypdf',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtSvg',
        'openpyxl',
        'reportlab',
        'cryptography',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', 'unittest'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# EXE principal: sem console para uso normal pelo cliente.
exe_gui = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='RecuperaAI',
    console=False,
    **_common_exe_kwargs,
)

# EXE auxiliar: com console para build, diagnóstico e smoke test.
# Isso evita falhas de stdout/stderr em builds windowed do PyInstaller.
exe_cli = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='RecuperaAI_CLI',
    console=True,
    **_common_exe_kwargs,
)

coll = COLLECT(
    exe_gui,
    exe_cli,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='RecuperaAI',
)
