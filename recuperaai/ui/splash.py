from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSplashScreen, QLabel, QVBoxLayout, QWidget
from PySide6.QtGui import QPixmap, QColor, QPainter


class SplashScreen(QSplashScreen):
    def __init__(self) -> None:
        pixmap = QPixmap(520, 300)
        pixmap.fill(QColor('#172033'))
        painter = QPainter(pixmap)
        painter.setPen(QColor('white'))
        painter.drawText(pixmap.rect(), Qt.AlignCenter, 'RecuperaAI\nPreparando ambiente local')
        painter.end()
        super().__init__(pixmap)
        self.setWindowFlag(Qt.WindowStaysOnTopHint)

    def show_message(self, message: str) -> None:
        self.showMessage(message, Qt.AlignBottom | Qt.AlignCenter, QColor('white'))
