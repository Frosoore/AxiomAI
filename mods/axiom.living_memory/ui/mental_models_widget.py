"""mods/axiom.living_memory/ui/mental_models_widget.py

Widget displaying mental models (NPC/character beliefs & profiles) for a session.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.localization import tr

_ID_ROLE = Qt.UserRole


class MentalModelsWidget(QWidget):
    """Widget displaying living memory mental models."""

    def __init__(
        self,
        parent: QWidget | None = None,
        db_path: str | None = None,
        save_id: str | None = None,
        now_turn: int | None = None,
    ) -> None:
        super().__init__(parent)
        self._db_path = db_path
        self._save_id = save_id
        self._now_turn = now_turn if now_turn is not None else 0
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._empty_label = QLabel(tr("memory_browser_empty_models"))
        self._empty_label.setWordWrap(True)
        layout.addWidget(self._empty_label)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels([
            tr("memory_browser_col_subject"),
            tr("memory_browser_col_profile"),
            tr("memory_browser_col_turn"),
        ])
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setWordWrap(True)
        layout.addWidget(self._table)

        self.refresh()

    def set_session(
        self,
        db_path: str | None,
        save_id: str | None,
        now_turn: int | None = None,
    ) -> None:
        self._db_path = db_path
        self._save_id = save_id
        if now_turn is not None:
            self._now_turn = now_turn
        self.refresh()

    def refresh(self) -> None:
        if not self._db_path or not self._save_id:
            self._table.setRowCount(0)
            self._table.setVisible(False)
            self._empty_label.setText(tr("memory_browser_no_session"))
            self._empty_label.setVisible(True)
            return

        from axiom.mental_models import get_mental_models

        try:
            models = get_mental_models(
                self._db_path, self._save_id, max_turn_id=self._now_turn
            )
        except Exception:
            models = []

        self._table.setRowCount(0)
        if not models:
            self._table.setVisible(False)
            self._empty_label.setText(tr("memory_browser_empty_models"))
            self._empty_label.setVisible(True)
            return

        self._empty_label.setVisible(False)
        self._table.setVisible(True)
        self._table.setRowCount(len(models))

        for row, m in enumerate(models):
            subject = m.subject.strip() or tr("memory_browser_world")
            subj_item = QTableWidgetItem(subject)
            subj_item.setData(_ID_ROLE, m.model_id)
            self._table.setItem(row, 0, subj_item)
            self._table.setItem(row, 1, QTableWidgetItem(m.summary))
            turn_item = QTableWidgetItem(str(m.updated_turn_id))
            turn_item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(row, 2, turn_item)

        header = self._table.horizontalHeader()
        for col in range(self._table.columnCount()):
            mode = QHeaderView.Stretch if col == 1 else QHeaderView.ResizeToContents
            header.setSectionResizeMode(col, mode)
        self._table.resizeRowsToContents()

    def retranslate_ui(self) -> None:
        self._table.setHorizontalHeaderLabels([
            tr("memory_browser_col_subject"),
            tr("memory_browser_col_profile"),
            tr("memory_browser_col_turn"),
        ])
        if not self._db_path or not self._save_id:
            self._empty_label.setText(tr("memory_browser_no_session"))
        else:
            self._empty_label.setText(tr("memory_browser_empty_models"))
        self.refresh()
