from __future__ import annotations

import logging
import json
import shutil
import unicodedata
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QGroupBox,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton,
    QMenu, QScrollArea, QSizePolicy, QStackedWidget, QStyle, QTableWidget, QTabWidget,
    QTextEdit, QToolButton, QVBoxLayout, QWidget,
)

from recuperaai.core.logging_config import current_log_path, error_text, log_exception
from recuperaai.security.permissions import ROLE_LABELS, allowed_roles_for_user_creation, can, visible_tabs_for_role
from recuperaai.tools.analysis.analysis_tool import REVIEW_STATUSES
from recuperaai.ui.widgets import fill_table


STATUS_LABELS = {
    'imported': 'Aguardando leitura',
    'parsed': 'Aguardando análise',
    'attention': 'Com atenção',
    'clear': 'Sem inconsistência aparente',
    'parse_error': 'Erro de leitura',
    'stored': 'Armazenado',
    'open': 'Aberta',
    'confirmed': 'Confirmada',
    'rejected': 'Rejeitada',
    'in_review': 'Em revisão',
    'pending_document': 'Pendente de documento',
    'waiting_client': 'Aguardando cliente',
    'exported': 'Exportada em relatório',
    'active': 'Ativo',
    'inactive': 'Inativo',
    'paused': 'Pausado',
    'archived': 'Arquivado',
}

SEVERITY_LABELS = {'critical': 'Crítica', 'warning': 'Atenção', 'info': 'Informativa'}
CATEGORY_LABELS = {
    'contract': 'Contrato',
    'corporate': 'Documento cadastral',
    'report': 'Relatório recebido',
    'other': 'Outro documento',
}


class SidebarNavigation:
    """Controlador leve para trocar as abas superiores por uma navegação lateral.

    A interface antiga usava QTabWidget no topo. Para manter compatibilidade com os
    builders já existentes, esta classe expõe ``addTab`` e cria, por baixo, um botão
    lateral + uma página no QStackedWidget.
    """

    def __init__(self, menu_layout: QVBoxLayout, stack: QStackedWidget) -> None:
        self.menu_layout = menu_layout
        self.stack = stack
        self.buttons: list[QPushButton] = []
        self.labels: list[str] = []

    def addTab(self, page: QWidget, title: str) -> int:
        wrapper = QWidget()
        wrapper.setObjectName('contentPageWrapper')
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(24, 22, 24, 22)
        wrapper_layout.setSpacing(14)
        page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
        wrapper_layout.addWidget(page)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setObjectName('contentPageScroll')
        scroll.setWidget(wrapper)
        index = self.stack.addWidget(scroll)

        button = QPushButton(title)
        button.setObjectName('sidebarButton')
        button.setCheckable(True)
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(lambda checked=False, i=index: self.setCurrentIndex(i))
        self.menu_layout.addWidget(button)
        self.buttons.append(button)
        self.labels.append(title)
        if index == 0:
            self.setCurrentIndex(0)
        return index

    def setCurrentIndex(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for i, button in enumerate(self.buttons):
            button.setChecked(i == index)

    def currentIndex(self) -> int:
        return self.stack.currentIndex()


class NoWheelTabWidget(QTabWidget):
    """Abas que ignoram a roda do mouse para evitar troca acidental."""

    def __init__(self) -> None:
        super().__init__()
        self.tabBar().installEventFilter(self)

    def eventFilter(self, watched: QWidget, event: QEvent) -> bool:
        if watched is self.tabBar() and event.type() == QEvent.Wheel:
            event.ignore()
            return True
        return super().eventFilter(watched, event)


class MainWindow(QMainWindow):
    def __init__(self, engine, session) -> None:
        super().__init__()
        self.engine = engine
        self.session = session
        self.selected_client_id: int | None = None
        self._client_workspace: dict[str, Any] | None = None
        self._workspace_dialog: QDialog | None = None
        self.logger = logging.getLogger('recuperaai.ui.main_window')
        profile = ROLE_LABELS.get(session.user.role, session.user.role)
        self.setWindowTitle(f'RecuperaAI - Central Fiscal Local | {session.user.full_name} ({profile})')
        self.resize(1280, 820)
        try:
            theme_dir = Path(__file__).resolve().parent
            qss = theme_dir.joinpath('styles.qss').read_text(encoding='utf-8')
            qss = qss.replace('__UI_ASSET_DIR__', theme_dir.as_posix())
            self.setStyleSheet(qss)
        except Exception:
            pass

        self._build_modern_shell()
        self.statusBar().showMessage(f'Pronto | Cliente: nenhum | Logs: {self.engine.paths.logs}')
        self._build_allowed_tabs()
        self.refresh_all()

    def _build_modern_shell(self) -> None:
        root = QWidget()
        root.setObjectName('appRoot')
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(222)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(16, 18, 14, 16)
        sidebar_layout.setSpacing(12)

        brand = QLabel('<span style="font-size:28px;font-weight:900;color:#0B63E5;">R</span> '
                       '<span style="font-size:21px;font-weight:900;color:#0F2742;">Recupera</span>'
                       '<span style="font-size:21px;font-weight:900;color:#10B981;">AI</span><br>'
                       '<span style="font-size:12px;color:#64748B;">Central Fiscal Local</span>')
        brand.setObjectName('brandLabel')
        brand.setTextFormat(Qt.RichText)
        sidebar_layout.addWidget(brand)

        self.sidebar_menu_layout = QVBoxLayout()
        self.sidebar_menu_layout.setSpacing(6)
        sidebar_layout.addLayout(self.sidebar_menu_layout)
        sidebar_layout.addStretch()

        profile = ROLE_LABELS.get(self.session.user.role, self.session.user.role)
        user_card = QLabel(f'<b>{self.session.user.full_name}</b><br><span>{profile}</span>')
        user_card.setObjectName('sidebarUserCard')
        user_card.setTextFormat(Qt.RichText)
        sidebar_layout.addWidget(user_card)

        online_card = QLabel('● Sistema operacional<br><b>Online</b>')
        online_card.setObjectName('sidebarStatusCard')
        online_card.setTextFormat(Qt.RichText)
        sidebar_layout.addWidget(online_card)

        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName('contentStack')
        self.tabs = SidebarNavigation(self.sidebar_menu_layout, self.content_stack)

        root_layout.addWidget(sidebar)
        root_layout.addWidget(self.content_stack, 1)
        self.setCentralWidget(root)

    def _metric_card(self, title: str, value: object, subtitle: str = '', tone: str = 'blue') -> QLabel:
        label = QLabel()
        label.setObjectName('metricCard')
        label.setProperty('tone', tone)
        label.setTextFormat(Qt.RichText)
        label.setText(self._metric_card_html(title, value, subtitle, tone))
        label.setMinimumHeight(86)
        label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return label

    @staticmethod
    def _count(value: object) -> str:
        try:
            number = int(value or 0)
        except Exception:
            return str(value or 0)
        if abs(number) >= 1_000_000:
            return f'{number / 1_000_000:.1f} mi'.replace('.', ',')
        if abs(number) >= 10_000:
            return f'{number / 1_000:.1f} mil'.replace('.', ',')
        return f'{number:,}'.replace(',', '.')

    @staticmethod
    def _metric_card_html(title: str, value: object, subtitle: str = '', tone: str = 'blue') -> str:
        badges = {
            'Clientes': 'CLI',
            'Notas com atenção': 'NF',
            'Inconsistências abertas': 'INC',
            'Relatórios': 'REL',
        }
        colors = {
            'blue': '#0B63E5',
            'warning': '#D97706',
            'danger': '#DC2626',
            'success': '#059669',
        }
        bg = {
            'blue': '#EAF3FF',
            'warning': '#FFF4D6',
            'danger': '#FFE8EB',
            'success': '#DDFBF0',
        }
        badge = badges.get(title, title[:3].upper())
        color = colors.get(tone, colors['blue'])
        icon_bg = bg.get(tone, bg['blue'])
        value_text = MainWindow._count(value)
        return (
            '<table width="100%" cellspacing="0" cellpadding="0">'
            '<tr>'
            f'<td width="48" valign="top"><span style="font-size:12px;font-weight:900;color:{color};'
            f'background-color:{icon_bg};padding:7px 7px;border-radius:7px;">{badge}</span></td>'
            '<td valign="middle">'
            f'<div style="font-size:12px;color:#475569;white-space:normal;">{title}</div>'
            f'<div style="font-size:11px;color:#64748B;">{subtitle}</div>'
            '</td>'
            '</tr>'
            f'<tr><td colspan="2" style="padding-top:6px;"><span style="font-size:22px;font-weight:900;'
            f'color:{color};line-height:105%;">{value_text}</span></td></tr>'
            '</table>'
        )

    def _empty_state(self, title: str, subtitle: str = '') -> QLabel:
        label = QLabel(f'📁\n{title}' + (f'\n{subtitle}' if subtitle else ''))
        label.setObjectName('emptyState')
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(True)
        return label

    def _can(self, permission: str) -> bool:
        return can(self.session.role, permission)

    def _build_allowed_tabs(self) -> None:
        for tab in visible_tabs_for_role(self.session.role):
            getattr(self, tab.builder)()
        self._polish_action_buttons()

    def _polish_action_buttons(self, root: QWidget | None = None) -> None:
        root = root or self
        for button in root.findChildren(QPushButton):
            if button.objectName() == 'sidebarButton':
                continue
            button.setCursor(Qt.PointingHandCursor)
            button.setMinimumHeight(max(button.minimumHeight(), 34))
            button.setStyleSheet(
                'QPushButton { background-color: #0B63E5; color: #FFFFFF; '
                'border: 1px solid #084FC1; border-radius: 7px; '
                'font-weight: 800; padding: 9px 14px; }'
                'QPushButton:hover { background-color: #084FC1; }'
                'QPushButton:pressed { background-color: #063F9A; }'
                'QPushButton:disabled { background-color: #AEB7C2; border-color: #AEB7C2; color: #FFFFFF; }'
            )

    def _standard_icon(self, name: str) -> QIcon:
        try:
            pixmap = getattr(QStyle.StandardPixmap, name)
            return self.style().standardIcon(pixmap)
        except Exception:
            return QIcon()

    @staticmethod
    def _ui_asset_url(name: str) -> str:
        return Path(__file__).resolve().parent.joinpath(name).as_posix()

    def _icon_button(self, icon_name: str, tooltip: str, handler=None) -> QToolButton:
        button = QToolButton()
        button.setObjectName('iconButton')
        button.setIcon(self._standard_icon(icon_name))
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setCursor(Qt.PointingHandCursor)
        button.setAutoRaise(True)
        button.setFixedSize(34, 34)
        if handler is not None:
            button.clicked.connect(handler)
        return button

    def _client_selector(self, changed_handler) -> QComboBox:
        combo = QComboBox()
        combo.setObjectName('clientSelectorCombo')
        combo.setMinimumHeight(40)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        chevron = self._ui_asset_url('chevron_down.svg')
        combo.setStyleSheet(
            'QComboBox { background-color: #FFFFFF; color: #102033; '
            'border: 1px solid #94A3B8; border-radius: 7px; '
            'padding: 8px 36px 8px 10px; font-weight: 700; }'
            'QComboBox:hover { border-color: #0B63E5; }'
            'QComboBox:focus { border: 2px solid #0B63E5; }'
            'QComboBox::drop-down { width: 30px; border-left: 1px solid #CBD5E1; }'
            f'QComboBox::down-arrow {{ image: url("{chevron}"); width: 12px; height: 12px; }}'
            'QComboBox QAbstractItemView { background-color: #FFFFFF; color: #102033; '
            'selection-background-color: #E8F2FF; selection-color: #102033; '
            'border: 1px solid #94A3B8; }'
        )
        combo.currentIndexChanged.connect(changed_handler)
        return combo

    def _selection_combo(
        self,
        options: list[tuple[str, str]],
        *,
        object_name: str = 'actionCombo',
        minimum_width: int = 146,
        handler=None,
    ) -> QComboBox:
        combo = QComboBox()
        combo.setObjectName(object_name)
        combo.setMinimumHeight(40)
        combo.setMinimumWidth(minimum_width)
        for label, value in options:
            combo.addItem(label, value)
        if handler is not None:
            combo.currentIndexChanged.connect(lambda *_: handler())
        return combo

    def _action_input(self, placeholder: str, *, minimum_width: int = 260) -> QLineEdit:
        field = QLineEdit()
        field.setObjectName('actionInput')
        field.setPlaceholderText(placeholder)
        field.setMinimumHeight(40)
        field.setMinimumWidth(minimum_width)
        field.setClearButtonEnabled(True)
        return field

    @staticmethod
    def _search_token(value: object) -> str:
        text = '' if value is None else str(value)
        text = unicodedata.normalize('NFKD', text)
        text = ''.join(ch for ch in text if not unicodedata.combining(ch))
        return text.lower().strip()

    def _matches_search(self, term: object, *values: object) -> bool:
        needle = self._search_token(term)
        if not needle:
            return True
        return needle in self._search_token(' '.join('' if value is None else str(value) for value in values))

    def _combo_data(self, name: str, default: str = '') -> str:
        if not hasattr(self, name):
            return default
        value = getattr(self, name).currentData()
        return default if value is None else str(value)

    def _line_text(self, name: str) -> str:
        if not hasattr(self, name):
            return ''
        return getattr(self, name).text().strip()

    def _search_input(self, placeholder: str, handler) -> QLineEdit:
        field = QLineEdit()
        field.setObjectName('filterSearch')
        field.setPlaceholderText(placeholder)
        field.setClearButtonEnabled(True)
        try:
            field.addAction(self._standard_icon('SP_FileDialogContentsView'), QLineEdit.LeadingPosition)
        except Exception:
            pass
        field.textChanged.connect(lambda *_: handler())
        return field

    def _filter_combo(self, options: list[tuple[str, str]], handler) -> QComboBox:
        combo = QComboBox()
        combo.setObjectName('filterCombo')
        combo.setMinimumHeight(40)
        for label, value in options:
            combo.addItem(label, value)
        combo.currentIndexChanged.connect(lambda *_: handler())
        return combo

    def _filter_row(self, *widgets: QWidget) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        for widget in widgets:
            if isinstance(widget, QLabel):
                continue
            if isinstance(widget, QLineEdit):
                widget.setMinimumWidth(260)
                row.addWidget(widget, 1)
                continue
            if isinstance(widget, QComboBox):
                widget.setMinimumWidth(146)
            row.addWidget(widget)
        row.addStretch()
        return row

    def _filter_documents(
        self,
        documents: list[dict[str, Any]],
        *,
        search_name: str = '',
        status_name: str = '',
        type_name: str = '',
        category_name: str = '',
    ) -> list[dict[str, Any]]:
        term = self._line_text(search_name)
        status = self._combo_data(status_name)
        file_type = self._combo_data(type_name)
        category = self._combo_data(category_name)
        filtered = []
        for doc in documents:
            if status and status not in {str(doc.get('processing_status') or ''), str(doc.get('parser_status') or '')}:
                continue
            if file_type and file_type != str(doc.get('file_type') or '').lower():
                continue
            if category and category != str(doc.get('category') or ''):
                continue
            if not self._matches_search(
                term,
                doc.get('original_name'),
                doc.get('invoice_key'),
                doc.get('issue_date'),
                doc.get('issuer_name'),
                doc.get('issuer_document'),
                doc.get('recipient_name'),
                doc.get('recipient_document'),
                doc.get('total_amount'),
                self._status(doc.get('parser_status')),
                self._status(doc.get('processing_status')),
                CATEGORY_LABELS.get(doc.get('category'), doc.get('category')),
            ):
                continue
            filtered.append(doc)
        return filtered

    def _filter_findings(
        self,
        findings: list[dict[str, Any]],
        *,
        search_name: str = '',
        severity_name: str = '',
        status_name: str = '',
    ) -> list[dict[str, Any]]:
        term = self._line_text(search_name)
        severity = self._combo_data(severity_name)
        status = self._combo_data(status_name)
        filtered = []
        for item in findings:
            if severity and severity != str(item.get('severity') or ''):
                continue
            if status and status != str(item.get('status') or ''):
                continue
            if not self._matches_search(
                term,
                self._severity(item.get('severity')),
                self._source(item.get('source')),
                item.get('original_name'),
                item.get('invoice_key'),
                item.get('title'),
                item.get('message'),
                item.get('amount'),
                item.get('total_amount'),
                self._status(item.get('status')),
                item.get('review_note'),
            ):
                continue
            filtered.append(item)
        return filtered

    def _filter_rows(self, rows: list[dict[str, Any]], search_name: str) -> list[dict[str, Any]]:
        term = self._line_text(search_name)
        if not term:
            return rows
        return [row for row in rows if self._matches_search(term, *row.values())]

    def _filter_reports(self, reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
        term = self._line_text('client_reports_search')
        fmt = self._combo_data('client_reports_format_filter')
        filtered = []
        for report in reports:
            if fmt and fmt != str(report.get('format') or ''):
                continue
            if not self._matches_search(term, report.get('name'), report.get('format'), report.get('modified_at'), report.get('path')):
                continue
            filtered.append(report)
        return filtered

    def _refresh_cached_client_tables(self) -> None:
        if self._client_workspace:
            self._apply_client_workspace_filters(self._client_workspace)

    def _page(self, title: str, subtitle: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        profile = ROLE_LABELS.get(self.session.user.role, self.session.user.role)
        h = QLabel(title)
        h.setObjectName('title')
        s = QLabel(f'{subtitle}\nPerfil atual: {profile}.')
        s.setObjectName('subtitle')
        s.setWordWrap(True)
        layout.addWidget(h)
        layout.addWidget(s)
        return page, layout

    def _group(self, title: str) -> tuple[QGroupBox, QVBoxLayout]:
        box = QGroupBox(title)
        box.setObjectName('card')
        layout = QVBoxLayout(box)
        return box, layout

    def _content_card(self, spacing: int = 12) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName('contentCard')
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(spacing)
        return card, layout

    @staticmethod
    def _money(value: object) -> str:
        if value in (None, ''):
            return 'R$ 0,00'
        try:
            return f'R$ {float(value):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
        except Exception:
            return str(value)

    def _note_ref(self, item: dict[str, Any]) -> str:
        name = self._value(item.get('original_name'))
        key = self._value(item.get('invoice_key'))
        if key:
            return f'{name} | {key}' if name else key
        return name or 'Nota fiscal'

    @staticmethod
    def _value(value: object) -> str:
        return '' if value is None else str(value)

    @staticmethod
    def _status(value: object) -> str:
        return STATUS_LABELS.get(str(value or ''), str(value or ''))

    @staticmethod
    def _severity(value: object) -> str:
        return SEVERITY_LABELS.get(str(value or ''), str(value or ''))

    @staticmethod
    def _source(value: object) -> str:
        return 'Análise avançada' if str(value or '').lower() == 'api' else 'Conferência local'

    def _advanced_analysis_text(self) -> str:
        cfg = self.engine.config_store.config
        if cfg.api_enabled and cfg.api_base_url:
            return 'Análise avançada: ativa para novas conferências.'
        return 'Análise avançada: desativada. As notas serão avaliadas apenas pela conferência local.'

    def _show_error(self, title: str, exc: BaseException, action: str) -> None:
        log_exception(
            action,
            exc,
            user=getattr(self.session.user, 'username', ''),
            role=getattr(self.session.user, 'role', ''),
            client_id=self.selected_client_id,
        )
        self.statusBar().showMessage(f'Erro: {action}. Consulte o diagnóstico.', 10000)
        QMessageBox.warning(self, title, error_text(exc, action))

    def _show_message(self, text: str, timeout: int = 8000) -> None:
        self.statusBar().showMessage(text, timeout)

    def _confirm_destructive_action(self, title: str, message: str, confirm_text: str = 'Excluir') -> bool:
        dialog = QDialog(self)
        dialog.setObjectName('confirmDialog')
        dialog.setWindowTitle(title)
        dialog.setModal(True)
        dialog.setMinimumWidth(460)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(16)

        body = QHBoxLayout()
        body.setSpacing(14)

        icon = QLabel()
        icon.setObjectName('confirmIcon')
        icon.setFixedSize(42, 42)
        icon.setAlignment(Qt.AlignCenter)
        icon.setPixmap(self._standard_icon('SP_MessageBoxWarning').pixmap(24, 24))
        body.addWidget(icon, 0, Qt.AlignTop)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(6)
        title_label = QLabel(title)
        title_label.setObjectName('confirmTitle')
        title_label.setWordWrap(True)
        message_label = QLabel(message)
        message_label.setObjectName('confirmText')
        message_label.setWordWrap(True)
        text_layout.addWidget(title_label)
        text_layout.addWidget(message_label)
        body.addLayout(text_layout, 1)
        layout.addLayout(body)

        actions = QHBoxLayout()
        actions.addStretch()
        cancel = QPushButton('Cancelar')
        cancel.setObjectName('secondaryButton')
        confirm = QPushButton(confirm_text)
        confirm.setObjectName('dangerButton')
        cancel.clicked.connect(dialog.reject)
        confirm.clicked.connect(dialog.accept)
        actions.addWidget(cancel)
        actions.addWidget(confirm)
        layout.addLayout(actions)

        return dialog.exec() == QDialog.Accepted

    def open_logs_folder(self) -> None:
        path = self.engine.paths.logs
        try:
            path.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
            self._show_message(f'Pasta de diagnóstico aberta: {path}')
        except Exception as exc:
            self._show_error('Diagnóstico', exc, 'abrir pasta de diagnóstico')

    def copy_log_path(self) -> None:
        log_path = current_log_path() or (self.engine.paths.logs / 'recuperaai_app.log')
        QApplication.clipboard().setText(str(log_path))
        self._show_message(f'Caminho do diagnóstico copiado: {log_path}')

    def _selected_table_id(self, table: QTableWidget) -> int | None:
        row = table.currentRow()
        if row < 0:
            return None
        item = table.item(row, 0)
        if not item:
            return None
        try:
            return int(item.text())
        except Exception:
            return None

    def _document_id_from_finding_table(self, table: QTableWidget) -> int | None:
        finding_id = self._selected_table_id(table)
        if finding_id is None:
            return None
        finding = self.engine.findings.get(finding_id)
        if not finding:
            return None
        return int(finding.get('document_id'))

    def _selected_invoice_id(self, table: QTableWidget) -> int | None:
        return self._selected_table_id(table)

    def _document_preview_text(self, document) -> str:
        parts = []
        if document.payload_json:
            try:
                payload = json.loads(document.payload_json)
                parts.append('Dados lidos da nota:\n' + json.dumps(payload, ensure_ascii=False, indent=2))
            except Exception:
                parts.append('Dados lidos da nota:\n' + document.payload_json)

        path = Path(document.storage_path)
        if path.exists() and path.is_file():
            if document.file_type.lower() == 'xml':
                try:
                    parts.append('\nArquivo XML:\n' + path.read_text(encoding='utf-8', errors='replace')[:20000])
                except Exception as exc:
                    parts.append(f'\nNão foi possível ler o XML: {exc}')
            elif document.file_type.lower() == 'pdf':
                try:
                    from pypdf import PdfReader

                    reader = PdfReader(str(path))
                    text = '\n'.join((page.extract_text() or '') for page in reader.pages[:5])
                    parts.append('\nTexto extraído do PDF:\n' + (text[:20000] or 'Nenhum texto extraível encontrado.'))
                except Exception as exc:
                    parts.append(f'\nNão foi possível extrair texto do PDF: {exc}')
            else:
                parts.append(f'\nArquivo original disponível em:\n{path}')
        else:
            parts.append('\nArquivo original não encontrado no armazenamento local.')
        return '\n\n'.join(parts)

    def open_document_dialog(self, document_id: int | None) -> None:
        if document_id is None:
            QMessageBox.information(self, 'Nota fiscal', 'Selecione uma nota para abrir.')
            return
        try:
            document = self.engine.tool('documents').get_document(self.session, document_id)
        except Exception as exc:
            self._show_error('Nota fiscal', exc, 'abrir nota fiscal')
            return
        if not document:
            QMessageBox.warning(self, 'Nota fiscal', 'Nota fiscal não encontrada.')
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f'Nota fiscal - {document.original_name}')
        dialog.resize(900, 680)
        dialog.setStyleSheet(self.styleSheet())
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        header = QLabel(
            f'<b>{document.original_name}</b><br>'
            f'Chave: {self._value(document.invoice_key) or "não identificada"}<br>'
            f'Emissão: {self._value(document.issue_date) or "não identificada"} | '
            f'Valor: {self._money(document.total_amount)} | '
            f'Situação: {self._status(document.processing_status)}'
        )
        header.setObjectName('sectionHint')
        header.setWordWrap(True)
        layout.addWidget(header)

        preview = QTextEdit()
        preview.setReadOnly(True)
        preview.setPlainText(self._document_preview_text(document))
        layout.addWidget(preview, 1)

        actions = QHBoxLayout()
        open_btn = QPushButton('Abrir arquivo original')
        save_btn = QPushButton('Salvar cópia')
        close_btn = QPushButton('Fechar')
        actions.addWidget(open_btn)
        actions.addWidget(save_btn)
        actions.addStretch()
        actions.addWidget(close_btn)
        layout.addLayout(actions)

        def open_original() -> None:
            path = Path(document.storage_path)
            if not path.exists():
                QMessageBox.warning(dialog, 'Nota fiscal', 'Arquivo original não encontrado.')
                return
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

        def save_copy() -> None:
            source = Path(document.storage_path)
            if not source.exists():
                QMessageBox.warning(dialog, 'Nota fiscal', 'Arquivo original não encontrado.')
                return
            target, _ = QFileDialog.getSaveFileName(dialog, 'Salvar cópia da nota', document.original_name)
            if not target:
                return
            shutil.copy2(source, target)
            QMessageBox.information(dialog, 'Nota fiscal', 'Cópia salva com sucesso.')

        open_btn.clicked.connect(open_original)
        save_btn.clicked.connect(save_copy)
        close_btn.clicked.connect(dialog.close)
        self._polish_action_buttons(dialog)
        dialog.exec()

    def open_selected_invoice_from_table(self, table: QTableWidget) -> None:
        self.open_document_dialog(self._selected_invoice_id(table))

    def open_selected_finding_document_from_table(self, table: QTableWidget) -> None:
        self.open_document_dialog(self._document_id_from_finding_table(table))

    def _enable_document_context_menu(self, table: QTableWidget, *, invoice: bool) -> None:
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(
            lambda pos, t=table, inv=invoice: self._show_document_context_menu(t, pos, invoice=inv)
        )

    def _show_document_context_menu(self, table: QTableWidget, pos, *, invoice: bool) -> None:
        row = table.rowAt(pos.y())
        if row >= 0:
            table.selectRow(row)
        document_id = self._selected_table_id(table)
        if document_id is None:
            return

        menu = QMenu(table)
        preview_action = menu.addAction(self._standard_icon('SP_FileDialogDetailedView'), 'Visualizar')
        open_action = menu.addAction(self._standard_icon('SP_DialogOpenButton'), 'Abrir arquivo')
        download_action = menu.addAction(self._standard_icon('SP_DialogSaveButton'), 'Baixar cópia')
        delete_action = None
        can_delete = self._can('invoices_delete') if invoice else self._can('documents_delete')
        if can_delete:
            menu.addSeparator()
            delete_action = menu.addAction(self._standard_icon('SP_TrashIcon'), 'Excluir')

        selected = menu.exec(table.viewport().mapToGlobal(pos))
        if selected == preview_action:
            self.open_document_dialog(document_id)
        elif selected == open_action:
            self.open_document_file(document_id)
        elif selected == download_action:
            self.download_document(document_id)
        elif delete_action is not None and selected == delete_action:
            self.delete_document(document_id)

    def _enable_report_context_menu(self, table: QTableWidget) -> None:
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(lambda pos, t=table: self._show_report_context_menu(t, pos))

    def _selected_report_path(self, table: QTableWidget) -> Path | None:
        row = table.currentRow()
        if row < 0:
            return None
        item = table.item(row, 4)
        if not item:
            return None
        text = item.text().strip()
        return Path(text) if text else None

    def _show_report_context_menu(self, table: QTableWidget, pos) -> None:
        row = table.rowAt(pos.y())
        if row >= 0:
            table.selectRow(row)
        path = self._selected_report_path(table)
        if not path:
            return
        menu = QMenu(table)
        open_action = menu.addAction(self._standard_icon('SP_DialogOpenButton'), 'Abrir')
        download_action = menu.addAction(self._standard_icon('SP_DialogSaveButton'), 'Baixar cópia')
        selected = menu.exec(table.viewport().mapToGlobal(pos))
        if selected == open_action:
            self.open_report_path(path)
        elif selected == download_action:
            self.download_report_path(path)

    def open_document_file(self, document_id: int | None) -> None:
        if document_id is None:
            QMessageBox.information(self, 'Documento', 'Selecione um documento.')
            return
        try:
            document = self.engine.tool('documents').get_document(self.session, document_id)
            if not document:
                QMessageBox.warning(self, 'Documento', 'Documento não encontrado.')
                return
            path = Path(document.storage_path)
            if not path.exists():
                QMessageBox.warning(self, 'Documento', 'Arquivo original não encontrado.')
                return
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        except Exception as exc:
            self._show_error('Documento', exc, 'abrir arquivo')

    def download_document(self, document_id: int | None) -> None:
        if document_id is None:
            QMessageBox.information(self, 'Documento', 'Selecione um documento.')
            return
        try:
            document = self.engine.tool('documents').get_document(self.session, document_id)
            if not document:
                QMessageBox.warning(self, 'Documento', 'Documento não encontrado.')
                return
            source = Path(document.storage_path)
            if not source.exists():
                QMessageBox.warning(self, 'Documento', 'Arquivo original não encontrado.')
                return
            target, _ = QFileDialog.getSaveFileName(self, 'Baixar cópia', document.original_name)
            if not target:
                return
            shutil.copy2(source, target)
            self._show_message('Cópia baixada.')
        except Exception as exc:
            self._show_error('Documento', exc, 'baixar cópia')

    def open_report_path(self, path: Path) -> None:
        if not path.exists():
            QMessageBox.warning(self, 'Relatórios', 'O arquivo do relatório não foi encontrado no armazenamento local.')
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def download_report_path(self, path: Path) -> None:
        if not path.exists():
            QMessageBox.warning(self, 'Relatórios', 'O arquivo do relatório não foi encontrado no armazenamento local.')
            return
        target, _ = QFileDialog.getSaveFileName(self, 'Baixar relatório', path.name)
        if not target:
            return
        try:
            shutil.copy2(path, target)
            self._show_message('Relatório baixado.')
        except Exception as exc:
            self._show_error('Relatórios', exc, 'baixar relatório')

    def delete_document(self, document_id: int | None) -> None:
        if document_id is None:
            QMessageBox.information(self, 'Documento', 'Selecione um documento.')
            return
        try:
            document = self.engine.tool('documents').get_document(self.session, document_id)
        except Exception as exc:
            self._show_error('Documento', exc, 'carregar documento para exclusão')
            return
        if not document:
            QMessageBox.warning(self, 'Documento', 'Documento não encontrado.')
            return
        title = 'nota fiscal' if document.category == 'invoice' else 'documento'
        confirmed = self._confirm_destructive_action(
            f'Excluir {title}',
            f'"{document.original_name}" será removido junto com os apontamentos vinculados e o arquivo armazenado.',
        )
        if not confirmed:
            return
        try:
            if document.category == 'invoice':
                self.engine.tool('invoices').delete_invoice(self.session, document_id)
            else:
                self.engine.tool('documents').delete_document(self.session, document_id)
            self.refresh_client_workspace()
            self.refresh_findings()
            self.refresh_top_level_invoices()
            self.refresh_top_level_findings()
            self.refresh_dashboard()
            self._show_message('Documento excluído.')
        except Exception as exc:
            self._show_error('Excluir', exc, f'excluir {title}')

    # ---------------------------------------------------------------------
    # Abas principais
    # ---------------------------------------------------------------------
    def _build_dashboard(self) -> None:
        page, layout = self._page(
            'Oportunidades estimadas',
            'Valores calculados automaticamente a partir das notas fiscais e dos apontamentos de análise.',
        )
        kpis = QGridLayout()
        kpis.setSpacing(12)
        self.dashboard_estimated_card = self._metric_card('Reembolso estimado', 'R$ 0,00', 'não rejeitado', 'success')
        self.dashboard_confirmed_card = self._metric_card('Confirmado', 'R$ 0,00', 'revisado', 'blue')
        self.dashboard_review_card = self._metric_card('Em validação', 'R$ 0,00', 'aberto ou em revisão', 'warning')
        self.dashboard_api_card = self._metric_card('Origem API', 'R$ 0,00', 'apontado pela integração', 'danger')
        for index, card in enumerate([
            self.dashboard_estimated_card,
            self.dashboard_confirmed_card,
            self.dashboard_review_card,
            self.dashboard_api_card,
        ]):
            kpis.addWidget(card, index, 0)
        layout.addLayout(kpis)

        box, box_layout = self._content_card()
        header = QHBoxLayout()
        title = QLabel('Clientes com valores estimados')
        title.setObjectName('cardTitle')
        header.addWidget(title)
        header.addWidget(self._icon_button('SP_BrowserReload', 'Atualizar oportunidades', self.refresh_dashboard))
        if self._can('settings_read') or self._can('backup_create'):
            header.addWidget(self._icon_button('SP_DirOpenIcon', 'Abrir diagnóstico', self.open_logs_folder))
            header.addWidget(self._icon_button('SP_DialogSaveButton', 'Copiar caminho do diagnóstico', self.copy_log_path))
        header.addStretch()
        box_layout.addLayout(header)
        self.dashboard_priority_table = QTableWidget()
        box_layout.addWidget(self.dashboard_priority_table)
        layout.addWidget(box)

        if self._can('settings_read') or self._can('backup_create'):
            self.diagnostics_label = QLabel(f'Arquivo técnico de diagnóstico: {current_log_path() or self.engine.paths.logs / "recuperaai_app.log"}')
        else:
            self.diagnostics_label = QLabel('Se ocorrer falha, avise o supervisor e informe qual tela estava sendo usada.')
        self.diagnostics_label.setObjectName('hint')
        layout.addWidget(self.diagnostics_label)
        self.tabs.addTab(page, 'Oportunidades')

    def _build_clients(self) -> None:
        page, layout = self._page('Clientes', 'Área central do cliente: dados, documentos, notas, análises, relatórios e histórico em um só lugar.')
        kpis = QGridLayout()
        kpis.setSpacing(12)
        self.clients_kpi_total = self._metric_card('Clientes', '0', 'cadastrado(s)', 'blue')
        self.clients_kpi_attention = self._metric_card('Notas com atenção', '0', 'requer atenção', 'warning')
        self.clients_kpi_findings = self._metric_card('Inconsistências abertas', '0', 'pendentes', 'danger')
        self.clients_kpi_reports = self._metric_card('Relatórios', '0', 'gerados', 'success')
        for index, card in enumerate([self.clients_kpi_total, self.clients_kpi_attention, self.clients_kpi_findings, self.clients_kpi_reports]):
            kpis.addWidget(card, index // 2, index % 2)
        layout.addLayout(kpis)

        clients_list_card = QFrame()
        clients_list_card.setObjectName('contentCard')
        clients_list_layout = QVBoxLayout(clients_list_card)
        clients_list_layout.setContentsMargins(12, 12, 12, 12)
        clients_list_layout.setSpacing(12)
        if self._can('clients_write'):
            form = QGridLayout()
            form.setSpacing(10)
            self.client_name = QLineEdit(); self.client_name.setPlaceholderText('Nome da empresa')
            self.client_document = QLineEdit(); self.client_document.setPlaceholderText('CNPJ')
            self.client_contact = QLineEdit(); self.client_contact.setPlaceholderText('Responsável')
            self.client_email = QLineEdit(); self.client_email.setPlaceholderText('Contato / e-mail')
            add_btn = QPushButton('Cadastrar cliente')
            add_btn.clicked.connect(self.create_client)
            form.addWidget(self.client_name, 0, 0)
            form.addWidget(self.client_document, 0, 1)
            form.addWidget(self.client_contact, 1, 0)
            form.addWidget(self.client_email, 1, 1)
            form.addWidget(add_btn, 2, 0, 1, 2, Qt.AlignLeft)
            form.setColumnStretch(0, 1)
            form.setColumnStretch(1, 1)
            clients_list_layout.addLayout(form)
        else:
            clients_list_layout.addWidget(QLabel('Seu perfil permite consultar clientes, mas não cadastrar ou editar.'))

        self.clients_search = self._search_input('Buscar por cliente, CNPJ, responsável ou contato', self.refresh_clients)
        self.clients_status_filter = self._filter_combo(
            [('Clientes operacionais', ''), ('Ativos', 'active'), ('Inativos', 'inactive'), ('Pausados', 'paused'), ('Arquivados', 'archived')],
            self.refresh_clients,
        )
        clients_list_layout.addLayout(self._filter_row(QLabel('Busca:'), self.clients_search, QLabel('Situação:'), self.clients_status_filter))

        self.clients_table = QTableWidget()
        self.clients_table.cellClicked.connect(self.select_client_row)
        self.clients_table.cellDoubleClicked.connect(self.open_client_workspace_dialog)
        clients_list_layout.addWidget(self.clients_table)
        self.clients_table_footer = QLabel('')
        self.clients_table_footer.setObjectName('tableFooter')
        clients_list_layout.addWidget(self.clients_table_footer)
        layout.addWidget(clients_list_card)

        hint = QLabel('Clique duas vezes em um cliente para abrir a central operacional em uma janela própria.')
        hint.setObjectName('sectionHint')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.tabs.addTab(page, 'Clientes')

    def _ensure_client_workspace_dialog(self) -> QDialog:
        if self._workspace_dialog is not None:
            return self._workspace_dialog

        dialog = QDialog(self)
        dialog.setWindowTitle('Central operacional do cliente')
        dialog.resize(1120, 760)
        dialog.setStyleSheet(self.styleSheet())
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        self.client_detail_title = QLabel('Central operacional do cliente')
        self.client_detail_title.setObjectName('title')
        self.client_summary = QLabel('')
        self.client_summary.setObjectName('clientSummaryCard')
        self.client_summary.setWordWrap(True)
        layout.addWidget(self.client_detail_title)
        layout.addWidget(self.client_summary)

        self.client_detail_tabs = NoWheelTabWidget()
        self.client_detail_tabs.setMinimumHeight(420)
        self.client_detail_tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._build_client_overview_tab()
        self._build_client_data_tab()
        self._build_client_contracts_tab()
        self._build_client_documents_tab()
        self._build_client_invoices_tab()
        self._build_client_imports_tab()
        self._build_client_findings_tab()
        self._build_client_reports_tab()
        self._build_client_history_tab()
        layout.addWidget(self.client_detail_tabs, 1)

        self._workspace_dialog = dialog
        self._polish_action_buttons(dialog)
        return dialog

    def open_client_workspace_dialog(self, row: int | None = None, col: int | None = None) -> None:
        if row is not None and row >= 0:
            self.select_client_row(row, col or 0)
        if not self.selected_client_id:
            QMessageBox.information(self, 'Clientes', 'Selecione um cliente para abrir a central operacional.')
            return
        dialog = self._ensure_client_workspace_dialog()
        self.refresh_client_workspace()
        client_name = self._current_client_display_name()
        dialog.setWindowTitle(f'Central operacional - {client_name or self.selected_client_id}')
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _build_client_overview_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.client_overview = QLabel('Selecione um cliente para ver o resumo operacional.')
        self.client_overview.setObjectName('dashboardCards')
        self.client_overview.setWordWrap(True)
        self.client_overview.setMinimumHeight(160)
        self.client_overview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout.addWidget(self.client_overview)
        self.client_next_steps = QLabel('')
        self.client_next_steps.setWordWrap(True)
        self.client_next_steps.setMinimumHeight(72)
        layout.addWidget(self.client_next_steps)
        layout.addStretch()
        self.client_detail_tabs.addTab(page, 'Resumo')

    def _build_client_data_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        self.detail_name = QLineEdit()
        self.detail_document = QLineEdit()
        self.detail_contact = QLineEdit()
        self.detail_email = QLineEdit()
        self.detail_phone = QLineEdit()
        self.detail_status = self._selection_combo(
            [('Ativo', 'active'), ('Inativo', 'inactive'), ('Pausado', 'paused')],
            object_name='formCombo',
        )
        self.detail_notes = QTextEdit(); self.detail_notes.setPlaceholderText('Observações internas, contrato, particularidades fiscais e pendências.')
        for row, (label, widget) in enumerate([
            ('Nome da empresa', self.detail_name), ('CNPJ', self.detail_document), ('Responsável', self.detail_contact),
            ('E-mail', self.detail_email), ('Telefone', self.detail_phone), ('Situação', self.detail_status),
            ('Observações', self.detail_notes),
        ]):
            field_label = QLabel(label)
            field_label.setObjectName('formLabel')
            form.addWidget(field_label, row, 0, Qt.AlignTop)
            form.addWidget(widget, row, 1)
        form.setColumnMinimumWidth(0, 128)
        form.setColumnStretch(1, 1)
        layout.addLayout(form)
        if self._can('clients_write'):
            actions = QHBoxLayout()
            actions.setSpacing(10)
            self.detail_save_btn = QPushButton('Salvar dados do cliente')
            self.detail_save_btn.setMinimumWidth(180)
            self.detail_save_btn.clicked.connect(self.update_selected_client)
            self.detail_archive_btn = QPushButton('Arquivar cliente')
            self.detail_archive_btn.setObjectName('dangerButton')
            self.detail_archive_btn.clicked.connect(self.archive_or_restore_selected_client)
            actions.addWidget(self.detail_save_btn)
            actions.addWidget(self.detail_archive_btn)
            actions.addStretch()
            layout.addLayout(actions)
        else:
            for widget in [self.detail_name, self.detail_document, self.detail_contact, self.detail_email, self.detail_phone, self.detail_notes]:
                widget.setReadOnly(True)
            self.detail_status.setEnabled(False)
        layout.addStretch()
        self.client_detail_tabs.addTab(page, 'Dados cadastrais')

    def _build_client_contracts_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        if self._can('documents_write'):
            btn = QPushButton('Adicionar contrato')
            btn.clicked.connect(lambda: self.add_client_document('contract'))
            layout.addWidget(btn, 0, Qt.AlignLeft)
        else:
            layout.addWidget(QLabel('Seu perfil permite consultar contratos, mas não anexar novos arquivos.'))
        self.client_contracts_search = self._search_input('Buscar contrato por nome ou tipo', self._refresh_cached_client_tables)
        layout.addLayout(self._filter_row(QLabel('Busca:'), self.client_contracts_search))
        self.client_contracts_table = QTableWidget()
        self._enable_document_context_menu(self.client_contracts_table, invoice=False)
        layout.addWidget(self.client_contracts_table)
        self.client_contracts_empty = self._empty_state('Nenhum contrato anexado', 'Anexe o contrato do cliente para centralizar os documentos.')
        layout.addWidget(self.client_contracts_empty)
        self.client_detail_tabs.addTab(page, 'Contratos')

    def _build_client_documents_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        if self._can('documents_write'):
            actions = QHBoxLayout()
            self.client_doc_category = self._selection_combo(
                [('Documento cadastral', 'corporate'), ('Relatório recebido', 'report'), ('Outro documento', 'other')],
                object_name='actionCombo',
                minimum_width=180,
            )
            add_doc_btn = QPushButton('Adicionar documento')
            add_doc_btn.clicked.connect(lambda: self.add_client_document(self.client_doc_category.currentData() or self.client_doc_category.currentText()))
            actions.addWidget(QLabel('Categoria:'))
            actions.addWidget(self.client_doc_category)
            actions.addWidget(add_doc_btn)
            actions.addStretch()
            layout.addLayout(actions)
        else:
            layout.addWidget(QLabel('Seu perfil permite consultar documentos enviados, mas não anexar novos arquivos.'))
        self.client_documents_search = self._search_input('Buscar documento por nome, categoria ou tipo', self._refresh_cached_client_tables)
        self.client_documents_category_filter = self._filter_combo(
            [('Todas as categorias', ''), ('Documento cadastral', 'corporate'), ('Relatório recebido', 'report'), ('Outro documento', 'other')],
            self._refresh_cached_client_tables,
        )
        layout.addLayout(self._filter_row(QLabel('Busca:'), self.client_documents_search, QLabel('Categoria:'), self.client_documents_category_filter))
        self.client_documents_table = QTableWidget()
        self._enable_document_context_menu(self.client_documents_table, invoice=False)
        layout.addWidget(self.client_documents_table)
        self.client_documents_empty = self._empty_state('Nenhum documento enviado ainda', 'Adicione documentos para manter as informações do cliente organizadas.')
        layout.addWidget(self.client_documents_empty)
        self.client_detail_tabs.addTab(page, 'Documentos')

    def _build_client_invoices_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.client_invoices_hint = QLabel('As notas são separadas por situação para evitar conferência manual arquivo por arquivo.')
        self.client_invoices_hint.setObjectName('hint')
        layout.addWidget(self.client_invoices_hint)
        self.client_invoices_search = self._search_input('Buscar por arquivo, chave, emitente, destinatário ou valor', self._refresh_cached_client_tables)
        self.client_invoices_status_filter = self._filter_combo(
            [('Todas as situações', ''), ('Aguardando análise', 'parsed'), ('Com atenção', 'attention'), ('Sem inconsistência aparente', 'clear'), ('Erro de leitura', 'parse_error'), ('Aguardando leitura', 'imported')],
            self._refresh_cached_client_tables,
        )
        self.client_invoices_type_filter = self._filter_combo(
            [('Todos os tipos', ''), ('XML', 'xml'), ('PDF', 'pdf')],
            self._refresh_cached_client_tables,
        )
        layout.addLayout(self._filter_row(QLabel('Busca:'), self.client_invoices_search, QLabel('Situação:'), self.client_invoices_status_filter, QLabel('Tipo:'), self.client_invoices_type_filter))
        self.client_invoices_table = QTableWidget()
        self._enable_document_context_menu(self.client_invoices_table, invoice=True)
        self.client_invoices_table.cellDoubleClicked.connect(
            lambda row, col: self.open_selected_invoice_from_table(self.client_invoices_table)
        )
        layout.addWidget(self.client_invoices_table)
        self.client_invoices_empty = self._empty_state('Nenhuma nota fiscal importada', 'Importe XML/PDF para iniciar a análise fiscal deste cliente.')
        layout.addWidget(self.client_invoices_empty)
        self.client_detail_tabs.addTab(page, 'Notas fiscais')

    def _build_client_imports_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        header = QHBoxLayout()
        title = QLabel('Importações fiscais do cliente')
        title.setObjectName('cardTitle')
        header.addWidget(title)
        header.addStretch()
        if self._can('invoices_import'):
            header.addWidget(self._icon_button('SP_DialogOpenButton', 'Anexar XML/PDF fiscal', self.import_files))
        else:
            title.setText('Histórico de importações fiscais')
        layout.addLayout(header)
        self.client_import_result = QTextEdit()
        self.client_import_result.setReadOnly(True)
        self.client_import_result.setMaximumHeight(112)
        self.client_import_result.setPlaceholderText('O resultado da última importação aparecerá aqui.')
        if self._can('invoices_import'):
            layout.addWidget(self.client_import_result)
        self.client_imports_search = self._search_input('Buscar por data, usuário ou resultado', self._refresh_cached_client_tables)
        layout.addLayout(self._filter_row(QLabel('Busca:'), self.client_imports_search))
        self.client_imports_table = QTableWidget()
        layout.addWidget(self.client_imports_table)
        self.client_detail_tabs.addTab(page, 'Importações')

    def _build_client_findings_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        actions = QHBoxLayout()
        self.review_status = self._selection_combo(
            [(label, key) for key, label in REVIEW_STATUSES.items()],
            object_name='actionCombo',
            minimum_width=180,
        )
        self.review_note = self._action_input('Observação da revisão humana')
        review_btn = QPushButton('Atualizar revisão')
        review_btn.clicked.connect(self.review_selected_finding)
        actions.addWidget(QLabel('Marcar como:'))
        actions.addWidget(self.review_status)
        actions.addWidget(self.review_note)
        actions.addWidget(review_btn)
        actions.addStretch()
        if self._can('findings_review'):
            layout.addLayout(actions)
        else:
            layout.addWidget(QLabel('Seu perfil permite consultar inconsistências, mas não revisar casos.'))
        self.client_findings_search = self._search_input('Buscar por nota, motivo, detalhe, origem ou observação', self._refresh_cached_client_tables)
        self.client_findings_severity_filter = self._filter_combo(
            [('Todas as gravidades', ''), ('Críticas', 'critical'), ('Atenção', 'warning'), ('Informativas', 'info')],
            self._refresh_cached_client_tables,
        )
        self.client_findings_status_filter = self._filter_combo(
            [('Todos os status', ''), *[(label, key) for key, label in REVIEW_STATUSES.items()]],
            self._refresh_cached_client_tables,
        )
        layout.addLayout(self._filter_row(QLabel('Busca:'), self.client_findings_search, QLabel('Gravidade:'), self.client_findings_severity_filter, QLabel('Status:'), self.client_findings_status_filter))
        self.client_findings_table = QTableWidget()
        self.client_findings_table.cellDoubleClicked.connect(
            lambda row, col: self.open_selected_finding_document_from_table(self.client_findings_table)
        )
        layout.addWidget(self.client_findings_table)
        self.client_detail_tabs.addTab(page, 'Inconsistências')

    def _build_client_reports_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        actions = QHBoxLayout()
        pdf_btn = self._icon_button('SP_FileIcon', 'Gerar PDF', lambda: self._export('pdf'))
        xlsx_btn = self._icon_button('SP_DriveHDIcon', 'Gerar Excel', lambda: self._export('xlsx'))
        csv_btn = self._icon_button('SP_FileDialogListView', 'Gerar CSV', lambda: self._export('csv'))
        open_folder_btn = self._icon_button('SP_DirOpenIcon', 'Abrir pasta de relatórios', self.open_reports_folder)
        open_selected_btn = self._icon_button('SP_DialogOpenButton', 'Abrir relatório selecionado', self.open_selected_report)
        for w in [pdf_btn, xlsx_btn, csv_btn, open_folder_btn, open_selected_btn]:
            actions.addWidget(w)
        actions.addStretch()
        if self._can('reports_export'):
            layout.addLayout(actions)
        else:
            layout.addWidget(QLabel('Seu perfil permite consultar o cliente, mas não gerar relatórios finais.'))
        self.client_reports_search = self._search_input('Buscar relatório por nome, formato ou caminho', self._refresh_cached_client_tables)
        self.client_reports_format_filter = self._filter_combo(
            [('Todos os formatos', ''), ('PDF', 'PDF'), ('Excel', 'XLSX'), ('CSV', 'CSV'), ('Texto', 'TXT')],
            self._refresh_cached_client_tables,
        )
        layout.addLayout(self._filter_row(QLabel('Busca:'), self.client_reports_search, QLabel('Formato:'), self.client_reports_format_filter))
        self.client_reports_table = QTableWidget()
        self._enable_report_context_menu(self.client_reports_table)
        layout.addWidget(self.client_reports_table)
        self.client_detail_tabs.addTab(page, 'Relatórios')

    def _build_client_history_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.client_history_search = self._search_input('Buscar por data, usuário, ação, origem ou detalhe', self._refresh_cached_client_tables)
        layout.addLayout(self._filter_row(QLabel('Busca:'), self.client_history_search))
        self.client_history_table = QTableWidget()
        layout.addWidget(self.client_history_table)
        self.client_detail_tabs.addTab(page, 'Histórico')

    def _build_invoices(self) -> None:
        page, layout = self._page('Notas Fiscais', 'Consulte as notas do cliente selecionado por situação, valor e leitura.')
        self.invoices_client_label = QLabel('Cliente selecionado: nenhum')
        self.invoices_client_label.setObjectName('dashboardCards')
        layout.addWidget(self.invoices_client_label)
        card, card_layout = self._content_card()
        self.invoices_client_combo = self._client_selector(self.select_context_client)
        card_layout.addWidget(QLabel('Cliente'))
        card_layout.addWidget(self.invoices_client_combo)
        self.invoices_search = self._search_input('Buscar por arquivo, chave, emitente, destinatário ou valor', self.refresh_top_level_invoices)
        self.invoices_status_filter = self._filter_combo(
            [('Todas as situações', ''), *[(self._status(key), key) for key in ['parsed', 'attention', 'clear', 'parse_error', 'imported']]],
            self.refresh_top_level_invoices,
        )
        self.invoices_type_filter = self._filter_combo(
            [('Todos os tipos', ''), ('XML', 'xml'), ('PDF', 'pdf')],
            self.refresh_top_level_invoices,
        )
        card_layout.addLayout(self._filter_row(
            QLabel('Busca:'), self.invoices_search,
            QLabel('Filtro:'), self.invoices_status_filter,
            QLabel('Tipo:'), self.invoices_type_filter,
        ))
        self.invoices_table = QTableWidget()
        self._enable_document_context_menu(self.invoices_table, invoice=True)
        self.invoices_table.cellDoubleClicked.connect(
            lambda row, col: self.open_selected_invoice_from_table(self.invoices_table)
        )
        card_layout.addWidget(self.invoices_table)
        layout.addWidget(card)
        self.tabs.addTab(page, 'Notas Fiscais')

    def _build_findings(self) -> None:
        page, layout = self._page('Inconsistências', 'Revise somente os casos que precisam de ação humana.')
        self.findings_client_label = QLabel('Cliente selecionado: nenhum')
        self.findings_client_label.setObjectName('dashboardCards')
        layout.addWidget(self.findings_client_label)
        card, card_layout = self._content_card()
        self.findings_client_combo = self._client_selector(self.select_context_client)
        card_layout.addWidget(QLabel('Cliente'))
        card_layout.addWidget(self.findings_client_combo)
        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.global_review_status = self._selection_combo(
            [(label, key) for key, label in REVIEW_STATUSES.items()],
            object_name='actionCombo',
            minimum_width=180,
        )
        self.global_review_note = self._action_input('Observação da revisão humana')
        global_review_btn = QPushButton('Atualizar revisão selecionada')
        global_review_btn.clicked.connect(self.review_selected_global_finding)
        actions.addWidget(QLabel('Marcar como:'))
        actions.addWidget(self.global_review_status)
        actions.addWidget(self.global_review_note)
        actions.addWidget(global_review_btn)
        actions.addStretch()
        if self._can('findings_review'):
            card_layout.addLayout(actions)
        else:
            card_layout.addWidget(QLabel('Seu perfil permite consultar inconsistências, mas não revisar casos.'))
        self.inconsistencies_table = QTableWidget()
        card_layout.addWidget(self.inconsistencies_table)
        layout.addWidget(card)
        self.tabs.addTab(page, 'Inconsistências')

    def _build_backup(self) -> None:
        page, layout = self._page('Backup', 'Crie uma cópia local do banco de dados, documentos importados, contratos e relatórios.')
        self.backup_info = QLabel('Nenhum backup criado nesta sessão.')
        self.backup_info.setObjectName('dashboardCards')
        backup_btn = QPushButton('Criar backup local agora')
        backup_btn.clicked.connect(self.create_backup)
        open_logs = QPushButton('Abrir diagnóstico')
        open_logs.clicked.connect(self.open_logs_folder)
        layout.addWidget(self.backup_info)
        card, card_layout = self._content_card()
        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addWidget(backup_btn)
        actions.addWidget(open_logs)
        actions.addStretch()
        card_layout.addLayout(actions)
        layout.addWidget(card)

        archive_card, archive_layout = self._content_card()
        archive_header = QHBoxLayout()
        archive_title = QLabel('Arquivo de clientes')
        archive_title.setObjectName('cardTitle')
        archive_header.addWidget(archive_title)
        archive_header.addStretch()
        archive_header.addWidget(self._icon_button('SP_BrowserReload', 'Atualizar clientes arquivados', self.refresh_archived_clients))
        if self._can('clients_write'):
            archive_header.addWidget(self._icon_button('SP_DialogApplyButton', 'Restaurar cliente selecionado', self.restore_archived_client_from_backup))
        archive_layout.addLayout(archive_header)
        archive_hint = QLabel('Clientes arquivados ficam fora das telas operacionais, mas mantêm documentos, relatórios e histórico para consulta ou restauração.')
        archive_hint.setObjectName('sectionHint')
        archive_hint.setWordWrap(True)
        archive_layout.addWidget(archive_hint)
        self.archived_clients_table = QTableWidget()
        self.archived_clients_table.cellDoubleClicked.connect(self.open_archived_client_from_backup)
        archive_layout.addWidget(self.archived_clients_table)
        layout.addWidget(archive_card)
        layout.addStretch()
        self.tabs.addTab(page, 'Backup')

    def _build_analysis(self) -> None:
        page, layout = self._page('Análises', 'Priorize notas com atenção, erro de leitura ou pendentes de revisão.')
        self.advanced_analysis_status = QLabel(self._advanced_analysis_text())
        self.advanced_analysis_status.setObjectName('sectionHint')
        self.advanced_analysis_status.setWordWrap(True)
        layout.addWidget(self.advanced_analysis_status)
        card, card_layout = self._content_card()
        self.analysis_client_combo = self._client_selector(self.select_context_client)
        card_layout.addWidget(QLabel('Cliente'))
        card_layout.addWidget(self.analysis_client_combo)
        self.analysis_search = self._search_input('Buscar por nota, motivo, detalhe, origem ou observação', self.refresh_findings)
        self.analysis_severity_filter = self._filter_combo(
            [('Todas as gravidades', ''), ('Críticas', 'critical'), ('Atenção', 'warning'), ('Informativas', 'info')],
            self.refresh_findings,
        )
        self.analysis_status_filter = self._filter_combo(
            [('Todos os status', ''), *[(label, key) for key, label in REVIEW_STATUSES.items()]],
            self.refresh_findings,
        )
        card_layout.addLayout(self._filter_row(QLabel('Busca:'), self.analysis_search, QLabel('Gravidade:'), self.analysis_severity_filter, QLabel('Status:'), self.analysis_status_filter))
        if self._can('analysis_run'):
            actions = QHBoxLayout()
            btn = QPushButton('Analisar cliente selecionado')
            btn.clicked.connect(self.analyze_selected_client)
            actions.addWidget(btn)
            actions.addStretch()
            card_layout.addLayout(actions)
        else:
            card_layout.addWidget(QLabel('Seu perfil permite consultar análises, mas não executar reanálise.'))
        if self._can('findings_review'):
            review_actions = QHBoxLayout()
            review_actions.setSpacing(10)
            self.global_review_status = self._selection_combo(
                [(label, key) for key, label in REVIEW_STATUSES.items()],
                object_name='actionCombo',
                minimum_width=180,
            )
            self.global_review_note = self._action_input('Observação da revisão humana')
            review_btn = QPushButton('Atualizar revisão selecionada')
            review_btn.clicked.connect(self.review_selected_global_finding)
            review_actions.addWidget(QLabel('Revisão:'))
            review_actions.addWidget(self.global_review_status)
            review_actions.addWidget(self.global_review_note)
            review_actions.addWidget(review_btn)
            review_actions.addStretch()
            card_layout.addLayout(review_actions)
        self.findings_table = QTableWidget()
        self.findings_table.cellDoubleClicked.connect(
            lambda row, col: self.open_selected_finding_document_from_table(self.findings_table)
        )
        card_layout.addWidget(self.findings_table)
        layout.addWidget(card)
        self.tabs.addTab(page, 'Análises')

    def _build_reports(self) -> None:
        page, layout = self._page('Relatórios', 'Gere relatórios profissionais do cliente selecionado.')
        card, card_layout = self._content_card()
        self.reports_client_combo = self._client_selector(self.select_context_client)
        card_layout.addWidget(QLabel('Cliente'))
        card_layout.addWidget(self.reports_client_combo)
        h = QHBoxLayout()
        h.setSpacing(10)
        pdf_btn = QPushButton('Gerar PDF')
        xlsx_btn = QPushButton('Gerar Excel')
        csv_btn = QPushButton('Gerar CSV')
        pdf_btn.clicked.connect(lambda: self._export('pdf'))
        xlsx_btn.clicked.connect(lambda: self._export('xlsx'))
        csv_btn.clicked.connect(lambda: self._export('csv'))
        h.addWidget(pdf_btn); h.addWidget(xlsx_btn); h.addWidget(csv_btn); h.addStretch()
        self.report_result = QLabel('Selecione um cliente antes de gerar relatórios.')
        self.report_result.setWordWrap(True)
        self.report_result.setObjectName('sectionHint')
        card_layout.addLayout(h)
        card_layout.addWidget(self.report_result)
        layout.addWidget(card)
        layout.addStretch()
        self.tabs.addTab(page, 'Relatórios')

    def _build_users(self) -> None:
        page, layout = self._page('Usuários', 'Controle de acesso da equipe interna.')
        allowed_roles = allowed_roles_for_user_creation(self.session.role)
        card, card_layout = self._content_card()
        if allowed_roles:
            form = QHBoxLayout()
            form.setSpacing(10)
            self.new_username = QLineEdit(); self.new_username.setPlaceholderText('Usuário')
            self.new_full_name = QLineEdit(); self.new_full_name.setPlaceholderText('Nome')
            self.new_role = self._selection_combo(
                [(ROLE_LABELS.get(role, role), role) for role in allowed_roles],
                object_name='actionCombo',
                minimum_width=170,
            )
            self.new_password = QLineEdit(); self.new_password.setPlaceholderText('Senha provisória'); self.new_password.setEchoMode(QLineEdit.Password)
            btn = QPushButton('Criar usuário')
            btn.clicked.connect(self.create_user)
            for w in [self.new_username, self.new_full_name, self.new_role, self.new_password, btn]:
                form.addWidget(w)
            card_layout.addLayout(form)
        else:
            card_layout.addWidget(QLabel('Seu perfil permite visualizar usuários, mas não criar ou alterar acessos.'))
        self.users_table = QTableWidget()
        card_layout.addWidget(self.users_table)
        layout.addWidget(card)
        self.tabs.addTab(page, 'Usuários')

    def _build_settings(self) -> None:
        page, layout = self._page('Configurações', 'Área administrativa de integração externa, backup e manutenção local.')
        card, card_layout = self._content_card()
        self.api_enabled = QCheckBox('Ativar análise avançada')
        self.api_url = QLineEdit(); self.api_url.setPlaceholderText('Endereço da análise avançada')
        self.api_token = QLineEdit(); self.api_token.setPlaceholderText('Chave de acesso'); self.api_token.setEchoMode(QLineEdit.Password)
        btn = QPushButton('Salvar configurações')
        btn.clicked.connect(self.save_settings)
        self.backup_btn = QPushButton('Criar backup local')
        self.backup_btn.clicked.connect(self.create_backup)
        self.settings_logs_btn = QPushButton('Abrir diagnóstico')
        self.settings_logs_btn.clicked.connect(self.open_logs_folder)
        self.settings_info = QLabel('')
        self.settings_info.setObjectName('sectionHint')
        integration_hint = QLabel('Quando ativa, a conferência das notas também poderá retornar possíveis oportunidades e inconsistências para revisão.')
        integration_hint.setObjectName('sectionHint')
        integration_hint.setWordWrap(True)
        card_layout.addWidget(self.api_enabled)
        card_layout.addWidget(integration_hint)
        card_layout.addWidget(self.api_url)
        card_layout.addWidget(self.api_token)
        actions = QHBoxLayout()
        actions.setSpacing(10)
        for w in [btn, self.backup_btn, self.settings_logs_btn]:
            actions.addWidget(w)
        actions.addStretch()
        card_layout.addLayout(actions)
        card_layout.addWidget(self.settings_info)
        layout.addWidget(card)
        layout.addStretch()
        self.tabs.addTab(page, 'Configurações')

    # ---------------------------------------------------------------------
    # Atualização de tela
    # ---------------------------------------------------------------------
    def refresh_all(self) -> None:
        if hasattr(self, 'dashboard_priority_table'):
            self.refresh_dashboard()
        if hasattr(self, 'clients_table'):
            self.refresh_clients()
            self.refresh_client_workspace()
            self.refresh_clients_kpis()
        if hasattr(self, 'findings_table'):
            self.refresh_findings()
        if hasattr(self, 'invoices_table'):
            self.refresh_top_level_invoices()
        if hasattr(self, 'inconsistencies_table'):
            self.refresh_top_level_findings()
        if hasattr(self, 'users_table'):
            self.refresh_users()
        if hasattr(self, 'archived_clients_table'):
            self.refresh_archived_clients()
        if hasattr(self, 'api_enabled'):
            self.refresh_settings()

    def refresh_clients_kpis(self) -> None:
        if not hasattr(self, 'clients_kpi_total'):
            return
        try:
            data = self.engine.tool('analysis').dashboard(self.session)
            clients = data.get('clients', {})
            docs = data.get('documents', {})
            findings = data.get('findings', {})
            by_status = docs.get('by_status', {})
            self.clients_kpi_total.setText(self._metric_card_html('Clientes', clients.get('active', 0), 'cadastrado(s)', 'blue'))
            self.clients_kpi_attention.setText(self._metric_card_html('Notas com atenção', by_status.get('attention', 0), 'requer atenção', 'warning'))
            open_findings = findings.get('open', 0) or findings.get('critical', 0) + findings.get('warning', 0) + findings.get('info', 0)
            self.clients_kpi_findings.setText(self._metric_card_html('Inconsistências abertas', open_findings, 'pendentes', 'danger'))
            reports_total = 0
            if self._client_workspace:
                reports_total = self._client_workspace.get('summary', {}).get('reports_total', 0)
            self.clients_kpi_reports.setText(self._metric_card_html('Relatórios', reports_total, 'gerados', 'success'))
        except Exception:
            pass

    def refresh_dashboard(self) -> None:
        try:
            data = self.engine.tool('analysis').dashboard(self.session)
            opportunities = data.get('opportunities', {})
            if hasattr(self, 'dashboard_estimated_card'):
                self.dashboard_estimated_card.setText(self._metric_card_html(
                    'Reembolso estimado',
                    self._money(opportunities.get('estimated_total')),
                    f"{self._count(opportunities.get('impacted_invoices', 0))} nota(s) com apontamento",
                    'success',
                ))
                self.dashboard_confirmed_card.setText(self._metric_card_html(
                    'Confirmado',
                    self._money(opportunities.get('confirmed_total')),
                    'revisado como procedente',
                    'blue',
                ))
                self.dashboard_review_card.setText(self._metric_card_html(
                    'Em validação',
                    self._money(opportunities.get('in_review_total')),
                    'aberto, aguardando ou em revisão',
                    'warning',
                ))
                self.dashboard_api_card.setText(self._metric_card_html(
                    'Origem API',
                    self._money(opportunities.get('api_estimated_total')),
                    'retornado pela integração externa',
                    'danger',
                ))

            rows = []
            for item in data.get('opportunities_by_client', []):
                rows.append([
                    item.get('client_id'),
                    item.get('name'),
                    item.get('document'),
                    item.get('invoices'),
                    item.get('findings'),
                    self._money(item.get('estimated')),
                    self._money(item.get('confirmed')),
                    self._money(item.get('api_estimated')),
                    item.get('last_issue_date') or '',
                ])
            if rows:
                fill_table(
                    self.dashboard_priority_table,
                    ['ID', 'Cliente', 'CNPJ', 'Notas', 'Apontamentos', 'Estimado', 'Confirmado', 'API', 'Última emissão'],
                    rows,
                )
            else:
                fill_table(
                    self.dashboard_priority_table,
                    ['Aviso'],
                    [['Nenhuma oportunidade de reembolso estimada com os dados atuais.']],
                )
        except Exception as exc:
            log_exception('atualizar painel', exc, user=getattr(self.session.user, 'username', ''), role=getattr(self.session.user, 'role', ''))
            fill_table(self.dashboard_priority_table, ['Aviso'], [[error_text(exc, 'atualizar oportunidades')]])

    def refresh_clients(self) -> None:
        try:
            term = self._line_text('clients_search')
            status_filter = self._combo_data('clients_status_filter')
            show_archived = status_filter == 'archived'
            all_clients = self.engine.tool('clients').list_clients(
                self.session,
                include_archived=show_archived,
                archived_only=show_archived,
            )
            clients = []
            for client in all_clients:
                if status_filter and status_filter != 'archived' and client.status != status_filter:
                    continue
                if not self._matches_search(term, client.name, client.document, client.contact_name, client.email, client.phone, self._status(client.status)):
                    continue
                clients.append(client)
            self._clients = clients
            fill_table(self.clients_table, ['ID', 'Cliente', 'CNPJ', 'Responsável', 'Contato', 'Situação'],
                       [[c.id, c.name, c.document, c.contact_name, c.email, self._status(c.status)] for c in clients])
            active_clients = self.engine.tool('clients').list_clients(self.session)
            self._refresh_client_selectors(active_clients)
            if hasattr(self, 'clients_table_footer'):
                total = len(all_clients)
                shown = len(clients)
                self.clients_table_footer.setText(f'Mostrando {shown} de {total} cliente' + ('' if total == 1 else 's'))
            self.refresh_clients_kpis()
        except Exception as exc:
            self._show_error('Clientes', exc, 'listar clientes')

    def _refresh_client_selectors(self, clients: list[Any]) -> None:
        for combo_name in (
            'invoices_client_combo',
            'analysis_client_combo',
            'findings_client_combo',
            'reports_client_combo',
        ):
            if not hasattr(self, combo_name):
                continue
            combo = getattr(self, combo_name)
            combo.blockSignals(True)
            try:
                combo.clear()
                combo.addItem('Selecione um cliente', None)
                for client in clients:
                    document = f' - {client.document}' if client.document else ''
                    combo.addItem(f'{client.name}{document}', client.id)
                if self.selected_client_id:
                    index = combo.findData(self.selected_client_id)
                    if index >= 0:
                        combo.setCurrentIndex(index)
            finally:
                combo.blockSignals(False)

    def select_context_client(self) -> None:
        sender = self.sender()
        if not isinstance(sender, QComboBox):
            return
        client_id = sender.currentData()
        if not client_id:
            self.selected_client_id = None
            self.refresh_client_workspace()
            if hasattr(self, 'invoices_table'):
                self.refresh_top_level_invoices()
            if hasattr(self, 'findings_table'):
                self.refresh_findings()
            if hasattr(self, 'inconsistencies_table'):
                self.refresh_top_level_findings()
            return
        self.selected_client_id = int(client_id)
        self.refresh_client_workspace()
        if hasattr(self, 'invoices_table'):
            self.refresh_top_level_invoices()
        if hasattr(self, 'findings_table'):
            self.refresh_findings()
        if hasattr(self, 'inconsistencies_table'):
            self.refresh_top_level_findings()

    def select_client_row(self, row: int, col: int) -> None:
        item = self.clients_table.item(row, 0)
        if not item:
            return
        self.selected_client_id = int(item.text())
        self.refresh_client_workspace()
        if hasattr(self, 'findings_table'):
            self.refresh_findings()
        if hasattr(self, 'invoices_table'):
            self.refresh_top_level_invoices()
        if hasattr(self, 'inconsistencies_table'):
            self.refresh_top_level_findings()
        client_name = self._current_client_display_name()
        self.statusBar().showMessage(f'Cliente selecionado: {client_name or self.selected_client_id}')

    def _current_client_display_name(self) -> str:
        if not self._client_workspace:
            return ''
        return self._client_workspace.get('client', {}).get('name', '') or ''

    def _selected_client_is_archived(self) -> bool:
        if not self._client_workspace:
            return False
        return self._client_workspace.get('client', {}).get('status') == 'archived'

    def _sync_selected_client_labels(self) -> None:
        client_name = self._current_client_display_name()
        if self.selected_client_id and self._selected_client_is_archived():
            text = f'Cliente arquivado: {client_name or self.selected_client_id}'
        else:
            text = f'Cliente selecionado: {client_name or self.selected_client_id}' if self.selected_client_id else 'Cliente selecionado: nenhum'
        for label_name in ('invoices_client_label', 'findings_client_label'):
            if hasattr(self, label_name):
                getattr(self, label_name).setText(text)
        for combo_name in (
            'invoices_client_combo',
            'analysis_client_combo',
            'findings_client_combo',
            'reports_client_combo',
        ):
            if not hasattr(self, combo_name):
                continue
            combo = getattr(self, combo_name)
            combo.blockSignals(True)
            try:
                index = combo.findData(self.selected_client_id) if self.selected_client_id else 0
                if index >= 0:
                    combo.setCurrentIndex(index)
                else:
                    combo.setCurrentIndex(0)
            finally:
                combo.blockSignals(False)
        if self.selected_client_id:
            self.statusBar().showMessage(f'{text} | Logs: {self.engine.paths.logs}')

    def refresh_client_workspace(self) -> None:
        if not self.selected_client_id:
            self._client_workspace = None
            if hasattr(self, 'client_detail_title'):
                self.client_detail_title.setText('Selecione um cliente para abrir a central operacional.')
                self.client_summary.setText('')
                self._clear_client_tables()
            self._sync_selected_client_labels()
            return
        try:
            workspace = self.engine.tool('clients').get_client_workspace(self.session, self.selected_client_id)
            self._client_workspace = workspace
        except Exception as exc:
            log_exception('carregar central do cliente', exc, client_id=self.selected_client_id)
            if hasattr(self, 'client_detail_title'):
                self.client_detail_title.setText('Não foi possível carregar a central do cliente.')
                self.client_summary.setText(error_text(exc, 'carregar central do cliente'))
            return

        if not hasattr(self, 'client_detail_title'):
            self._sync_selected_client_labels()
            self.refresh_clients_kpis()
            if hasattr(self, 'invoices_table'):
                self.refresh_top_level_invoices()
            if hasattr(self, 'findings_table'):
                self.refresh_findings()
            if hasattr(self, 'inconsistencies_table'):
                self.refresh_top_level_findings()
            return

        client = workspace['client']
        summary = workspace['summary']
        self._sync_selected_client_labels()
        status_label = self._status(client.get('status') or 'active')
        archived = client.get('status') == 'archived'
        status_color = '#475569' if archived else '#059669'
        status_bg = '#E2E8F0' if archived else '#DCFCE7'
        attention_total = self._count(summary.get('attention_documents', 0))
        open_findings_total = self._count(summary.get('open_findings_total', 0))
        opportunities = summary.get('opportunities', {})
        refund_estimated = self._money(opportunities.get('estimated_total'))
        refund_api = self._money(opportunities.get('api_estimated_total'))
        total_invoice_amount = self._money(summary.get('total_invoice_amount'))
        self.client_detail_title.setText('Central operacional')
        self.client_summary.setText(
            '<table width="100%" cellspacing="0" cellpadding="0">'
            '<tr>'
            '<td width="64" rowspan="2" valign="middle">'
            '<span style="font-size:13px;font-weight:900;color:#0B63E5;background-color:#EAF3FF;'
            'padding:12px 10px;border-radius:8px;">CLI</span></td>'
            '<td valign="middle">'
            f'<div style="font-size:22px;font-weight:900;color:#0F2742;">{client.get("name", "")}</div>'
            f'<div style="font-size:12px;color:#64748B;">CNPJ: {client.get("document", "")} &nbsp; '
            f'<span style="color:{status_color};background-color:{status_bg};"> {status_label} </span></div>'
            '</td>'
            '</tr>'
            '<tr><td style="padding-top:10px;">'
            '<table width="100%" cellspacing="0" cellpadding="0">'
            '<tr>'
            '<td width="22%" style="color:#64748B;font-size:12px;">Notas com atenção</td>'
            '<td width="22%" style="color:#64748B;font-size:12px;">Inconsistências abertas</td>'
            '<td width="28%" style="color:#64748B;font-size:12px;">Reembolso estimado</td>'
            '<td width="28%" style="color:#64748B;font-size:12px;">Valor total das notas</td>'
            '</tr>'
            '<tr>'
            f'<td style="padding-top:3px;"><b style="color:#D97706;font-size:17px;">{attention_total}</b></td>'
            f'<td style="padding-top:3px;"><b style="color:#DC2626;font-size:17px;">{open_findings_total}</b></td>'
            f'<td style="padding-top:3px;"><b style="color:#059669;font-size:16px;">{refund_estimated}</b>'
            f'<span style="color:#64748B;font-size:11px;"> &nbsp; API: {refund_api}</span></td>'
            f'<td style="padding-top:3px;"><b style="color:#0F2742;font-size:16px;">{total_invoice_amount}</b></td>'
            '</tr>'
            '</table>'
            '</td></tr></table>'
        )
        self.refresh_clients_kpis()
        self._fill_client_overview(workspace)
        self._fill_client_data(client)
        self._apply_client_workspace_filters(workspace)
        self.refresh_top_level_invoices()
        self.refresh_top_level_findings()

    def _clear_client_tables(self) -> None:
        for name, headers in [
            ('client_contracts_table', ['ID', 'Arquivo', 'Tipo', 'Situação']),
            ('client_documents_table', ['ID', 'Categoria', 'Arquivo', 'Tipo', 'Situação']),
            ('client_invoices_table', ['ID', 'Arquivo', 'Chave', 'Emissão', 'Valor', 'Situação']),
            ('client_imports_table', ['Data', 'Usuário', 'Resultado']),
            ('client_findings_table', ['ID', 'Gravidade', 'Origem', 'Nota', 'Motivo', 'Status']),
            ('client_reports_table', ['Arquivo', 'Formato', 'Data', 'Tamanho', 'Caminho']),
            ('client_history_table', ['Data', 'Usuário', 'Ação', 'Detalhes']),
            ('invoices_table', ['Aviso']),
            ('inconsistencies_table', ['Aviso']),
        ]:
            if hasattr(self, name):
                fill_table(getattr(self, name), headers, [])

    def _apply_client_workspace_filters(self, workspace: dict[str, Any]) -> None:
        self._fill_client_invoices(self._filter_documents(
            list(workspace.get('invoices', [])),
            search_name='client_invoices_search',
            status_name='client_invoices_status_filter',
            type_name='client_invoices_type_filter',
        ))
        self._fill_client_documents(
            self._filter_documents(list(workspace.get('contracts', [])), search_name='client_contracts_search'),
            self._filter_documents(
                list(workspace.get('client_documents', [])),
                search_name='client_documents_search',
                category_name='client_documents_category_filter',
            ),
        )
        self._fill_client_imports(self._filter_rows(list(workspace.get('import_history', [])), 'client_imports_search'))
        self._fill_client_findings(self._filter_findings(
            list(workspace.get('all_findings', [])),
            search_name='client_findings_search',
            severity_name='client_findings_severity_filter',
            status_name='client_findings_status_filter',
        ))
        self._fill_client_reports(self._filter_reports(list(workspace.get('reports', []))))
        self._fill_client_history(self._filter_rows(list(workspace.get('history', [])), 'client_history_search'))

    def _fill_client_overview(self, workspace: dict[str, Any]) -> None:
        client = workspace.get('client', {})
        summary = workspace.get('summary', {})
        findings = summary.get('findings', {})
        status = summary.get('finding_status', {})
        opportunities = summary.get('opportunities', {})
        archived = client.get('status') == 'archived'
        self.client_overview.setText(
            (f"Situação do cadastro: {self._status(client.get('status'))}\n" if archived else "") +
            f"Documentos totais: {summary.get('documents_total', 0)}\n"
            f"Notas fiscais: {summary.get('invoices_total', 0)}\n"
            f"Contratos: {summary.get('contracts_total', 0)}\n"
            f"Documentos enviados: {summary.get('client_documents_total', 0)}\n"
            f"Reembolso estimado: {self._money(opportunities.get('estimated_total'))} "
            f"(API: {self._money(opportunities.get('api_estimated_total'))})\n"
            f"Reembolso confirmado: {self._money(opportunities.get('confirmed_total'))}\n"
            f"Notas sem inconsistência aparente: {summary.get('clear_documents', 0)}\n"
            f"Notas com atenção: {summary.get('attention_documents', 0)}\n"
            f"Arquivos com erro de leitura: {summary.get('parse_errors', 0)}\n"
            f"Inconsistências abertas: {summary.get('open_findings_total', 0)} "
            f"(críticas: {findings.get('critical', 0)}, atenção: {findings.get('warning', 0)}, informativas: {findings.get('info', 0)})\n"
            f"Revisadas/confirmadas: {status.get('confirmed', 0)} | Rejeitadas: {status.get('rejected', 0)} | Em revisão: {status.get('in_review', 0)}"
        )
        next_steps = []
        if archived:
            next_steps.append('• Cliente arquivado: restaure o cadastro para novas importações, anexos ou análises.')
        elif summary.get('parse_errors', 0):
            next_steps.append('• Corrigir ou solicitar novamente arquivos com erro de leitura.')
        if summary.get('open_findings_total', 0):
            next_steps.append('• Revisar inconsistências abertas e marcar cada caso.')
        if summary.get('waiting_analysis', 0):
            next_steps.append('• Executar análise das notas aguardando processamento.')
        if not next_steps:
            next_steps.append('• Nenhuma ação crítica pendente para este cliente no momento.')
        self.client_next_steps.setText('Próximas ações:\n' + '\n'.join(next_steps))

    def _fill_client_data(self, client: dict[str, Any]) -> None:
        self.detail_name.setText(self._value(client.get('name')))
        self.detail_document.setText(self._value(client.get('document')))
        self.detail_contact.setText(self._value(client.get('contact_name')))
        self.detail_email.setText(self._value(client.get('email')))
        self.detail_phone.setText(self._value(client.get('phone')))
        self.detail_notes.setPlainText(self._value(client.get('notes')))
        for widget in [self.detail_name, self.detail_document, self.detail_contact, self.detail_email, self.detail_phone]:
            widget.setCursorPosition(0)
        status = self._value(client.get('status')) or 'active'
        archived_index = self.detail_status.findData('archived')
        if status != 'archived' and archived_index >= 0:
            self.detail_status.removeItem(archived_index)
        index = self.detail_status.findData(status)
        if index < 0:
            self.detail_status.addItem(self._status(status), status)
            index = self.detail_status.findData(status)
        self.detail_status.setCurrentIndex(index)
        self._apply_client_archive_state(status == 'archived')

    def _apply_client_archive_state(self, archived: bool) -> None:
        can_write = self._can('clients_write')
        editable = can_write and not archived
        for widget in [self.detail_name, self.detail_document, self.detail_contact, self.detail_email, self.detail_phone]:
            widget.setReadOnly(not editable)
        self.detail_notes.setReadOnly(not editable)
        self.detail_status.setEnabled(editable)
        if hasattr(self, 'detail_save_btn'):
            self.detail_save_btn.setEnabled(editable)
        if hasattr(self, 'detail_archive_btn'):
            self.detail_archive_btn.setText('Restaurar cliente' if archived else 'Arquivar cliente')
            self.detail_archive_btn.setObjectName('secondaryButton' if archived else 'dangerButton')
            self.detail_archive_btn.style().unpolish(self.detail_archive_btn)
            self.detail_archive_btn.style().polish(self.detail_archive_btn)

    def _fill_client_invoices(self, invoices: list[dict[str, Any]]) -> None:
        if hasattr(self, 'client_invoices_empty'):
            self.client_invoices_empty.setVisible(not invoices)
        if hasattr(self, 'client_invoices_table'):
            self.client_invoices_table.setVisible(bool(invoices))
        fill_table(
            self.client_invoices_table,
            ['ID', 'Arquivo', 'Chave', 'Emissão', 'Emitente', 'Destinatário', 'Valor', 'Leitura', 'Situação'],
            [[
                d.get('id'), d.get('original_name'), d.get('invoice_key'), d.get('issue_date'),
                d.get('issuer_name'), d.get('recipient_name'), self._money(d.get('total_amount')),
                self._status(d.get('parser_status')), self._status(d.get('processing_status')),
            ] for d in invoices],
        )

    def _fill_client_documents(self, contracts: list[dict[str, Any]], documents: list[dict[str, Any]]) -> None:
        if hasattr(self, 'client_contracts_empty'):
            self.client_contracts_empty.setVisible(not contracts)
        if hasattr(self, 'client_contracts_table'):
            self.client_contracts_table.setVisible(bool(contracts))
        if hasattr(self, 'client_documents_empty'):
            self.client_documents_empty.setVisible(not documents)
        if hasattr(self, 'client_documents_table'):
            self.client_documents_table.setVisible(bool(documents))
        fill_table(
            self.client_contracts_table,
            ['ID', 'Arquivo', 'Tipo', 'Situação'],
            [[d.get('id'), d.get('original_name'), d.get('file_type'), self._status(d.get('processing_status'))] for d in contracts],
        )
        fill_table(
            self.client_documents_table,
            ['ID', 'Categoria', 'Arquivo', 'Tipo', 'Situação'],
            [[d.get('id'), CATEGORY_LABELS.get(d.get('category'), d.get('category')), d.get('original_name'), d.get('file_type'), self._status(d.get('processing_status'))] for d in documents],
        )

    def _fill_client_imports(self, imports: list[dict[str, Any]]) -> None:
        fill_table(
            self.client_imports_table,
            ['Data', 'Usuário', 'Resultado'],
            [[i.get('created_at'), i.get('full_name') or i.get('username') or '', i.get('details')] for i in imports],
        )

    def _fill_client_findings(self, findings: list[dict[str, Any]]) -> None:
        rows = [[
            i.get('id'),
            self._severity(i.get('severity')),
            self._source(i.get('source')),
            self._note_ref(i),
            i.get('title'),
            i.get('message'),
            self._money(i.get('total_amount')),
            self._money(i.get('amount')),
            self._status(i.get('status')),
            i.get('review_note') or '',
        ] for i in findings]
        fill_table(self.client_findings_table, ['ID', 'Gravidade', 'Origem', 'Nota', 'Motivo', 'Detalhe', 'Valor da nota', 'Valor apontado', 'Status', 'Observação'], rows)

    def _fill_client_reports(self, reports: list[dict[str, Any]]) -> None:
        fill_table(
            self.client_reports_table,
            ['Arquivo', 'Formato', 'Data', 'Tamanho', 'Caminho'],
            [[r.get('name'), r.get('format'), r.get('modified_at'), r.get('size_bytes'), r.get('path')] for r in reports],
        )

    def _fill_client_history(self, history: list[dict[str, Any]]) -> None:
        fill_table(
            self.client_history_table,
            ['Data', 'Usuário', 'Ação', 'Origem', 'Detalhes'],
            [[h.get('created_at'), h.get('full_name') or h.get('username') or '', h.get('action'), h.get('entity'), h.get('details')] for h in history],
        )

    # ---------------------------------------------------------------------
    # Ações do usuário
    # ---------------------------------------------------------------------
    def archive_or_restore_selected_client(self) -> None:
        if not self._can('clients_write'):
            QMessageBox.warning(self, 'Cliente', 'Seu perfil não permite arquivar ou restaurar clientes.')
            return
        if not self.selected_client_id:
            QMessageBox.information(self, 'Cliente', 'Selecione um cliente antes de continuar.')
            return
        if self._selected_client_is_archived():
            try:
                client = self.engine.tool('clients').restore_client(self.session, self.selected_client_id)
                self.selected_client_id = client.id
                self.refresh_clients()
                self.refresh_archived_clients()
                self.refresh_client_workspace()
                self.refresh_dashboard()
                self._show_message('Cliente restaurado para as telas operacionais.')
            except Exception as exc:
                self._show_error('Cliente', exc, 'restaurar cliente')
            return

        client_name = self._current_client_display_name() or str(self.selected_client_id)
        confirmed = self._confirm_destructive_action(
            'Arquivar cliente',
            f'"{client_name}" deixará de aparecer nas abas operacionais. Documentos, relatórios e histórico serão preservados no arquivo de clientes.',
            confirm_text='Arquivar',
        )
        if not confirmed:
            return
        try:
            archived_id = self.selected_client_id
            self.engine.tool('clients').archive_client(self.session, archived_id)
            self.selected_client_id = None
            self._client_workspace = None
            if self._workspace_dialog is not None:
                self._workspace_dialog.hide()
            self.refresh_clients()
            self.refresh_archived_clients()
            self.refresh_client_workspace()
            self.refresh_dashboard()
            self._show_message('Cliente arquivado. Ele pode ser consultado ou restaurado na aba Backup.')
        except Exception as exc:
            self._show_error('Cliente', exc, 'arquivar cliente')

    def refresh_archived_clients(self) -> None:
        if not hasattr(self, 'archived_clients_table'):
            return
        try:
            archived = self.engine.tool('clients').list_clients(
                self.session,
                include_archived=True,
                archived_only=True,
            )
            fill_table(
                self.archived_clients_table,
                ['ID', 'Cliente', 'CNPJ', 'Responsável', 'Contato', 'Situação'],
                [[c.id, c.name, c.document, c.contact_name, c.email, self._status(c.status)] for c in archived],
            )
        except Exception as exc:
            self._show_error('Backup', exc, 'listar clientes arquivados')

    def restore_archived_client_from_backup(self) -> None:
        if not self._can('clients_write'):
            QMessageBox.warning(self, 'Backup', 'Seu perfil não permite restaurar clientes.')
            return
        client_id = self._selected_table_id(self.archived_clients_table)
        if client_id is None:
            QMessageBox.information(self, 'Backup', 'Selecione um cliente arquivado para restaurar.')
            return
        try:
            client = self.engine.tool('clients').restore_client(self.session, client_id)
            self.selected_client_id = client.id
            self.refresh_clients()
            self.refresh_archived_clients()
            self.refresh_client_workspace()
            self.refresh_dashboard()
            self._show_message('Cliente restaurado para as telas operacionais.')
        except Exception as exc:
            self._show_error('Backup', exc, 'restaurar cliente arquivado')

    def open_archived_client_from_backup(self, row: int | None = None, col: int | None = None) -> None:
        if row is not None and row >= 0:
            item = self.archived_clients_table.item(row, 0)
            if item:
                self.selected_client_id = int(item.text())
        if not self.selected_client_id:
            QMessageBox.information(self, 'Backup', 'Selecione um cliente arquivado para consultar.')
            return
        self.open_client_workspace_dialog()

    def update_selected_client(self) -> None:
        if not self._can('clients_write'):
            QMessageBox.warning(self, 'Cliente', 'Seu perfil não permite editar clientes.')
            return
        if not self.selected_client_id:
            QMessageBox.information(self, 'Cliente', 'Selecione um cliente antes de salvar.')
            return
        try:
            self.engine.tool('clients').update_client(
                self.session,
                self.selected_client_id,
                name=self.detail_name.text(),
                document=self.detail_document.text(),
                contact_name=self.detail_contact.text(),
                email=self.detail_email.text(),
                phone=self.detail_phone.text(),
                notes=self.detail_notes.toPlainText(),
                status=self.detail_status.currentData() or self.detail_status.currentText(),
            )
            self.refresh_clients()
            self.refresh_client_workspace()
            self.refresh_dashboard()
            self._show_message('Dados do cliente salvos.')
        except Exception as exc:
            self._show_error('Cliente', exc, 'salvar dados do cliente')

    def add_client_document(self, category: str) -> None:
        if not self.selected_client_id:
            QMessageBox.information(self, 'Documentos', 'Selecione um cliente antes de adicionar documentos.')
            return
        if self._selected_client_is_archived():
            QMessageBox.information(self, 'Documentos', 'Restaure o cliente antes de anexar novos documentos.')
            return
        files, _ = QFileDialog.getOpenFileNames(self, 'Adicionar documentos do cliente', '', 'Documentos (*.pdf *.doc *.docx *.png *.jpg *.jpeg *.txt)')
        if not files:
            return
        added = 0
        failures: list[str] = []
        for file_path in files:
            try:
                self.engine.tool('documents').add_client_document(self.session, self.selected_client_id, file_path, category)
                added += 1
            except Exception as exc:
                log_exception('adicionar documento do cliente', exc, client_id=self.selected_client_id, file=Path(file_path).name)
                failures.append(f'{Path(file_path).name}: {str(exc).strip() or exc.__class__.__name__}')
        self.refresh_client_workspace()
        self.refresh_dashboard()
        if failures:
            QMessageBox.warning(self, 'Documentos', f'Documentos adicionados: {added}\nCom falha: {len(failures)}\n\n' + '\n'.join(failures))
        else:
            QMessageBox.information(self, 'Documentos', f'Documentos adicionados: {added}')

    def create_client(self) -> None:
        if not self._can('clients_write'):
            QMessageBox.warning(self, 'Cadastrar cliente', 'Seu perfil não permite cadastrar clientes.')
            return
        try:
            client = self.engine.tool('clients').create_client(
                self.session,
                self.client_name.text(),
                self.client_document.text(),
                self.client_contact.text(),
                self.client_email.text(),
            )
            self.selected_client_id = client.id
            self.client_name.clear(); self.client_document.clear(); self.client_contact.clear(); self.client_email.clear()
            self.refresh_clients(); self.refresh_client_workspace(); self.refresh_dashboard()
            self._show_message('Cliente cadastrado e selecionado.')
        except Exception as exc:
            self._show_error('Cadastrar cliente', exc, 'cadastrar cliente')

    def import_files(self) -> None:
        if not self.selected_client_id:
            QMessageBox.information(self, 'Importações do cliente', 'Abra ou selecione um cliente antes de importar documentos fiscais.')
            return
        if self._selected_client_is_archived():
            QMessageBox.information(self, 'Importações do cliente', 'Restaure o cliente antes de importar novas notas fiscais.')
            return
        files, _ = QFileDialog.getOpenFileNames(self, 'Selecionar documentos fiscais', '', 'Documentos fiscais (*.xml *.pdf)')
        if not files:
            return
        try:
            result = self.engine.tool('invoices').import_files(self.session, self.selected_client_id, files)
        except Exception as exc:
            self._show_error('Importações do cliente', exc, 'importar documentos fiscais')
            return
        imported = len(result['imported'])
        skipped = len(result['skipped'])
        failed = len(result['failed'])
        details = []
        if skipped:
            details.append('Duplicados/ignorados:')
            details.extend(f"- {Path(item['file']).name}: {item['message']}" for item in result['skipped'][:30])
        if failed:
            details.append('Com erro de leitura/importação:')
            details.extend(f"- {Path(item['file']).name}: {item['message']}" for item in result['failed'][:30])
        if not details:
            details.append('Todos os arquivos foram importados e analisados com sucesso.')
        result_text = (
            'Importação do cliente concluída.\n\n'
            f'Arquivos selecionados: {len(files)}\n'
            f'Importados: {imported}\n'
            f'Duplicados/ignorados: {skipped}\n'
            f'Com erro: {failed}\n\n'
            + '\n'.join(details)
        )
        for output_name in ('import_result', 'client_import_result'):
            if hasattr(self, output_name):
                getattr(self, output_name).setText(result_text)
        self.refresh_client_workspace(); self.refresh_findings(); self.refresh_dashboard()
        self._show_message('Importação do cliente concluída. Verifique importações, notas fiscais e inconsistências do cliente.')

    def analyze_selected_client(self) -> None:
        if not self.selected_client_id:
            QMessageBox.information(self, 'Análises', 'Selecione um cliente nesta tela antes de analisar.')
            return
        if self._selected_client_is_archived():
            QMessageBox.information(self, 'Análises', 'Restaure o cliente antes de executar novas análises.')
            return
        try:
            result = self.engine.tool('analysis').analyze_client(self.session, self.selected_client_id)
        except Exception as exc:
            self._show_error('Análises', exc, 'analisar cliente')
            return
        QMessageBox.information(
            self,
            'Análises',
            f"Documentos analisados: {result['analyzed']}\n"
            f"Inconsistências/apontamentos: {result['findings']}\n"
            f"Falhas: {len(result['failed'])}",
        )
        self.refresh_client_workspace(); self.refresh_findings(); self.refresh_dashboard()

    def review_selected_finding(self) -> None:
        if not self.selected_client_id:
            QMessageBox.information(self, 'Revisão', 'Selecione um cliente antes de revisar.')
            return
        if self._selected_client_is_archived():
            QMessageBox.information(self, 'Revisão', 'Restaure o cliente antes de alterar revisões.')
            return
        finding_id = self._selected_table_id(self.client_findings_table)
        if finding_id is None:
            QMessageBox.information(self, 'Revisão', 'Selecione uma inconsistência na tabela.')
            return
        try:
            status = self.review_status.currentData() or self.review_status.currentText()
            self.engine.tool('analysis').review_finding(self.session, finding_id, status, self.review_note.text())
            self.review_note.clear()
            self.refresh_client_workspace(); self.refresh_findings(); self.refresh_dashboard()
            self._show_message('Revisão atualizada.')
        except Exception as exc:
            self._show_error('Revisão', exc, 'atualizar revisão da inconsistência')

    def refresh_top_level_invoices(self) -> None:
        if not hasattr(self, 'invoices_table'):
            return
        if not self.selected_client_id or not self._client_workspace:
            fill_table(self.invoices_table, ['Aviso'], [['Selecione um cliente para ver as notas fiscais.']])
            if hasattr(self, 'invoices_client_label'):
                self.invoices_client_label.setText('Cliente selecionado: nenhum')
            return
        if self._selected_client_is_archived():
            fill_table(self.invoices_table, ['Aviso'], [['Cliente arquivado. Consulte o registro pela central do cliente ou restaure para uso operacional.']])
            return
        invoices = self._filter_documents(
            list(self._client_workspace.get('invoices', [])),
            search_name='invoices_search',
            status_name='invoices_status_filter',
            type_name='invoices_type_filter',
        )
        if not invoices:
            fill_table(self.invoices_table, ['Aviso'], [['Nenhuma nota fiscal encontrada para o filtro selecionado.']])
            return
        fill_table(
            self.invoices_table,
            ['ID', 'Arquivo', 'Chave', 'Emissão', 'Emitente', 'Destinatário', 'Valor', 'Leitura', 'Situação'],
            [[
                d.get('id'), d.get('original_name'), d.get('invoice_key'), d.get('issue_date'),
                d.get('issuer_name'), d.get('recipient_name'), self._money(d.get('total_amount')),
                self._status(d.get('parser_status')), self._status(d.get('processing_status')),
            ] for d in invoices],
        )

    def refresh_top_level_findings(self) -> None:
        if not hasattr(self, 'inconsistencies_table'):
            return
        if not self.selected_client_id:
            fill_table(self.inconsistencies_table, ['Aviso'], [['Selecione um cliente para ver as inconsistências.']])
            if hasattr(self, 'findings_client_label'):
                self.findings_client_label.setText('Cliente selecionado: nenhum')
            return
        if self._selected_client_is_archived():
            fill_table(self.inconsistencies_table, ['Aviso'], [['Cliente arquivado. Consulte o histórico pela central do cliente ou restaure para uso operacional.']])
            return
        try:
            items = self.engine.tool('analysis').list_for_client(self.session, self.selected_client_id)
            if not items:
                fill_table(self.inconsistencies_table, ['Aviso'], [['Nenhuma inconsistência encontrada para este cliente.']])
                return
            fill_table(self.inconsistencies_table, ['ID', 'Gravidade', 'Nota', 'Valor da nota', 'Valor apontado', 'Motivo', 'Status'],
                       [[i['id'], self._severity(i['severity']), i.get('original_name'), self._money(i.get('total_amount')), self._money(i.get('amount')), i['title'], self._status(i['status'])] for i in items])
        except Exception as exc:
            log_exception('listar inconsistências', exc, client_id=self.selected_client_id)
            fill_table(self.inconsistencies_table, ['Aviso'], [[error_text(exc, 'listar inconsistências')]])

    def review_selected_global_finding(self) -> None:
        if not self.selected_client_id:
            QMessageBox.information(self, 'Revisão', 'Selecione um cliente antes de revisar.')
            return
        if self._selected_client_is_archived():
            QMessageBox.information(self, 'Revisão', 'Restaure o cliente antes de alterar revisões.')
            return
        table = self.findings_table if hasattr(self, 'findings_table') else self.inconsistencies_table
        finding_id = self._selected_table_id(table)
        if finding_id is None:
            QMessageBox.information(self, 'Revisão', 'Selecione um apontamento na tabela.')
            return
        try:
            status = self.global_review_status.currentData() or self.global_review_status.currentText()
            self.engine.tool('analysis').review_finding(self.session, finding_id, status, self.global_review_note.text())
            self.global_review_note.clear()
            self.refresh_client_workspace(); self.refresh_findings(); self.refresh_top_level_findings(); self.refresh_dashboard()
            self._show_message('Revisão atualizada.')
        except Exception as exc:
            self._show_error('Revisão', exc, 'atualizar revisão da inconsistência')

    def refresh_findings(self) -> None:
        if not hasattr(self, 'findings_table'):
            return
        if not self.selected_client_id:
            fill_table(self.findings_table, ['ID', 'Gravidade', 'Nota', 'Motivo', 'Valor da nota', 'Status'], [])
            return
        if self._selected_client_is_archived():
            fill_table(self.findings_table, ['Aviso'], [['Cliente arquivado. Consulte o histórico pela central do cliente ou restaure para uso operacional.']])
            if hasattr(self, 'inconsistencies_table'):
                self.refresh_top_level_findings()
            return
        try:
            items = self._filter_findings(
                self.engine.tool('analysis').list_for_client(self.session, self.selected_client_id),
                search_name='analysis_search',
                severity_name='analysis_severity_filter',
                status_name='analysis_status_filter',
            )
            fill_table(self.findings_table, ['ID', 'Gravidade', 'Nota', 'Valor da nota', 'Valor apontado', 'Motivo', 'Status'],
                       [[i['id'], self._severity(i['severity']), i.get('original_name'), self._money(i.get('total_amount')), self._money(i.get('amount')), i['title'], self._status(i['status'])] for i in items])
            if hasattr(self, 'inconsistencies_table'):
                self.refresh_top_level_findings()
        except Exception as exc:
            log_exception('listar inconsistências', exc, client_id=self.selected_client_id)
            fill_table(self.findings_table, ['Aviso'], [[error_text(exc, 'listar inconsistências')]])

    def refresh_users(self) -> None:
        try:
            users = self.engine.tool('users').list_users(self.session)
            fill_table(self.users_table, ['ID', 'Usuário', 'Nome', 'Perfil', 'Ativo'],
                       [[u.id, u.username, u.full_name, ROLE_LABELS.get(u.role, u.role), 'Sim' if u.is_active else 'Não'] for u in users])
        except Exception as exc:
            log_exception('listar usuários', exc, user=getattr(self.session.user, 'username', ''), role=getattr(self.session.user, 'role', ''))
            fill_table(self.users_table, ['Aviso'], [[error_text(exc, 'listar usuários')]])

    def create_user(self) -> None:
        if not self._can('users_write'):
            QMessageBox.warning(self, 'Usuários', 'Seu perfil não permite criar usuários.')
            return
        try:
            role = self.new_role.currentData() or self.new_role.currentText()
            self.engine.tool('users').create_user(self.session, self.new_username.text(), self.new_full_name.text(), role, self.new_password.text())
            self.new_username.clear(); self.new_full_name.clear(); self.new_password.clear()
            self.refresh_users()
            self._show_message('Usuário criado.')
        except Exception as exc:
            self._show_error('Usuários', exc, 'criar usuário')

    def refresh_settings(self) -> None:
        try:
            cfg = self.engine.tool('settings').get_config(self.session)
            self.api_enabled.setChecked(cfg.api_enabled)
            self.api_url.setText(cfg.api_base_url)
            self.api_token.setText(cfg.api_token)
            self.settings_info.setText('Configurações carregadas.')
            if hasattr(self, 'advanced_analysis_status'):
                self.advanced_analysis_status.setText(self._advanced_analysis_text())
        except Exception as exc:
            log_exception('carregar configurações', exc, user=getattr(self.session.user, 'username', ''), role=getattr(self.session.user, 'role', ''))
            self.settings_info.setText(error_text(exc, 'carregar configurações'))

    def save_settings(self) -> None:
        try:
            self.engine.tool('settings').update_api(self.session, self.api_enabled.isChecked(), self.api_url.text(), self.api_token.text())
            self.settings_info.setText('Configurações salvas. A análise avançada será usada nas próximas conferências quando estiver ativa.')
            if hasattr(self, 'advanced_analysis_status'):
                self.advanced_analysis_status.setText(self._advanced_analysis_text())
            self._show_message('Configurações salvas.')
        except Exception as exc:
            self._show_error('Configurações', exc, 'salvar configurações')

    def create_backup(self) -> None:
        try:
            path = self.engine.tool('settings').create_backup(self.session)
            if hasattr(self, 'settings_info'):
                self.settings_info.setText(f'Backup criado: {path}')
            if hasattr(self, 'backup_info'):
                self.backup_info.setText(f'Backup criado com sucesso:\n{path}')
            self._show_message(f'Backup criado: {path}')
        except Exception as exc:
            self._show_error('Backup', exc, 'criar backup')

    def export_pdf(self) -> None:
        self._export('pdf')

    def export_xlsx(self) -> None:
        self._export('xlsx')

    def _export(self, kind: str) -> None:
        if not self.selected_client_id:
            QMessageBox.information(self, 'Relatórios', 'Selecione um cliente nesta tela antes de gerar relatórios.')
            return
        if self._selected_client_is_archived():
            QMessageBox.information(self, 'Relatórios', 'Restaure o cliente antes de gerar novos relatórios.')
            return
        try:
            if kind == 'pdf':
                path = self.engine.tool('reports').export_client_pdf(self.session, self.selected_client_id)
            elif kind == 'xlsx':
                path = self.engine.tool('reports').export_client_xlsx(self.session, self.selected_client_id)
            else:
                path = self.engine.tool('reports').export_client_csv(self.session, self.selected_client_id)
            if hasattr(self, 'report_result'):
                self.report_result.setText(f'Relatório gerado: {path}')
            self.refresh_client_workspace()
            self._show_message(f'Relatório gerado: {path}')
        except Exception as exc:
            self._show_error('Relatórios', exc, 'gerar relatório')

    def open_reports_folder(self) -> None:
        try:
            self.engine.paths.reports.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.engine.paths.reports)))
        except Exception as exc:
            self._show_error('Relatórios', exc, 'abrir pasta de relatórios')

    def open_selected_report(self) -> None:
        path = self._selected_report_path(self.client_reports_table)
        if not path:
            QMessageBox.information(self, 'Relatórios', 'Selecione um relatório na tabela.')
            return
        self.open_report_path(path)
