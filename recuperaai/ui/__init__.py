from __future__ import annotations

import os
from pathlib import Path


def _configure_offscreen_fonts() -> None:
    """Help Qt offscreen renders use real Windows fonts during visual audits."""
    if os.environ.get("QT_QPA_PLATFORM", "").lower() != "offscreen":
        return
    if os.environ.get("QT_QPA_FONTDIR"):
        return
    windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    font_dir = windir / "Fonts"
    if font_dir.exists():
        os.environ["QT_QPA_FONTDIR"] = str(font_dir)


_configure_offscreen_fonts()