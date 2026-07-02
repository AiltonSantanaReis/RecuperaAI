from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox

from recuperaai.core.logging_config import error_text, log_exception


class LoginWindow(QDialog):
    def __init__(self, engine) -> None:
        super().__init__()
        self.engine = engine
        self.session = None
        self.logger = logging.getLogger("recuperaai.ui.login")
        self.setWindowTitle('RecuperaAI - Acesso')
        self.setMinimumWidth(440)
        self.setObjectName('loginWindow')
        try:
            theme_dir = Path(__file__).resolve().parent
            qss = theme_dir.joinpath('styles.qss').read_text(encoding='utf-8')
            qss = qss.replace('__UI_ASSET_DIR__', theme_dir.as_posix())
            self.setStyleSheet(qss)
        except Exception:
            self.logger.exception("Não foi possível carregar o tema visual do login.")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(12)
        title = QLabel('RecuperaAI')
        title.setObjectName('title')
        subtitle = QLabel('Ambiente local de análise fiscal')
        subtitle.setObjectName('subtitle')
        hint = QLabel('Use seu usuário interno. Em falha, consulte o arquivo de diagnóstico.')
        hint.setObjectName('hint')
        self.user = QLineEdit()
        self.user.setPlaceholderText('Usuário')
        self.password = QLineEdit()
        self.password.setPlaceholderText('Senha')
        self.password.setEchoMode(QLineEdit.Password)
        btn = QPushButton('Entrar')
        btn.clicked.connect(self.try_login)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(hint)
        layout.addSpacing(10)
        layout.addWidget(self.user)
        layout.addWidget(self.password)
        layout.addSpacing(8)
        layout.addWidget(btn)
        self.user.setText('admin')

    def try_login(self) -> None:
        username = self.user.text().strip()
        self.logger.info("Tentativa de login: usuario=%s", username)
        try:
            self.session = self.engine.auth.login(username, self.password.text())
            if self.session.user.must_change_password and not self._change_initial_password():
                self.session = None
                return
            self.logger.info("Login autorizado: usuario=%s perfil=%s", self.session.user.username, self.session.role)
            self.accept()
        except Exception as exc:
            log_exception("login", exc, username=username)
            QMessageBox.warning(self, 'Acesso negado', error_text(exc, 'entrar no sistema'))

    def _change_initial_password(self) -> bool:
        dialog = QDialog(self)
        dialog.setWindowTitle('Troca obrigatória de senha')
        dialog.setMinimumWidth(420)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(10)
        title = QLabel('Defina uma nova senha para continuar.')
        title.setObjectName('subtitle')
        current = QLineEdit()
        current.setPlaceholderText('Senha atual')
        current.setEchoMode(QLineEdit.Password)
        new_password = QLineEdit()
        new_password.setPlaceholderText('Nova senha')
        new_password.setEchoMode(QLineEdit.Password)
        confirm = QLineEdit()
        confirm.setPlaceholderText('Confirmar nova senha')
        confirm.setEchoMode(QLineEdit.Password)
        save_btn = QPushButton('Salvar nova senha')
        cancel_btn = QPushButton('Cancelar')
        layout.addWidget(title)
        layout.addWidget(current)
        layout.addWidget(new_password)
        layout.addWidget(confirm)
        layout.addWidget(save_btn)
        layout.addWidget(cancel_btn)

        def save() -> None:
            if new_password.text() != confirm.text():
                QMessageBox.warning(dialog, 'Senha', 'A confirmação da nova senha não confere.')
                return
            try:
                self.engine.auth.change_password(self.session, current.text(), new_password.text())
                dialog.accept()
            except Exception as exc:
                log_exception('trocar senha inicial', exc, username=self.session.user.username if self.session else '')
                QMessageBox.warning(dialog, 'Senha', error_text(exc, 'trocar senha inicial'))

        save_btn.clicked.connect(save)
        cancel_btn.clicked.connect(dialog.reject)
        return bool(dialog.exec())
