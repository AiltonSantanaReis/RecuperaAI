from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem


def fill_table(table: QTableWidget, headers: list[str], rows: list[list[object]]) -> None:
    """Preenche tabela de forma padronizada para a UI operacional.

    A primeira coluna ``ID`` continua disponível para ações internas, mas fica
    oculta para o usuário final. Isso mantém revisão/abertura de registros sem
    expor identificadores técnicos na experiência do operador.
    """
    table.clear()
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setRowCount(len(rows))
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.SingleSelection)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(36)
    table.horizontalHeader().setHighlightSections(False)
    table.setWordWrap(False)

    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            item = QTableWidgetItem('' if value is None else str(value))
            item.setToolTip(item.text())
            item.setForeground(QColor('#102033'))
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            table.setItem(r, c, item)

    if headers:
        table.setColumnHidden(0, headers[0].strip().upper() == 'ID')
        table.resizeColumnsToContents()
        if len(headers) <= 7:
            for index in range(len(headers)):
                if not table.isColumnHidden(index):
                    table.horizontalHeader().setSectionResizeMode(index, QHeaderView.Stretch)
        else:
            table.horizontalHeader().setStretchLastSection(True)
