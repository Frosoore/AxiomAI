"""
ui/widgets/diff_preview_dialog.py

TICKET-030 — Dialogue de prévisualisation d'un changement de source d'univers.
Affiche la liste des fichiers texte impactés (ajout/modif/suppression) et le
diff unifié de chacun ; l'utilisateur Applique ou Annule. Utilisé par le
Populate ciblé (Creator Studio) et la canonisation in-game (Tabletop).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColor, QFontDatabase
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QSplitter,
    QVBoxLayout,
)

from core.localization import tr

_STATUS_PREFIX = {"added": "+ ", "modified": "± ", "removed": "− "}
_STATUS_COLOR = {"added": "#4CAF50", "modified": "#FFC107", "removed": "#FF4B4B"}


class DiffPreviewDialog(QDialog):
    """Liste des fichiers changés + diff unifié, avec Appliquer/Annuler."""

    def __init__(self, diffs: list[dict], parent=None, title: str | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title or tr("diff_preview_title"))
        self.setMinimumSize(720, 480)
        self._diffs = diffs

        layout = QVBoxLayout(self)
        hint = QLabel(tr("diff_preview_hint", count=len(diffs)))
        hint.setStyleSheet("color: #888;")
        layout.addWidget(hint)

        splitter = QSplitter(Qt.Horizontal)
        self._file_list = QListWidget()
        for d in diffs:
            item = QListWidgetItem(_STATUS_PREFIX.get(d["status"], "") + d["path"])
            item.setForeground(QColor(_STATUS_COLOR.get(d["status"], "#ffffff")))
            item.setData(Qt.UserRole, d)
            self._file_list.addItem(item)
        self._file_list.currentItemChanged.connect(self._on_file_selected)
        splitter.addWidget(self._file_list)

        self._diff_view = QPlainTextEdit()
        self._diff_view.setReadOnly(True)
        self._diff_view.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        splitter.addWidget(self._diff_view)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText(tr("apply_changes_btn"))
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        if diffs:
            self._file_list.setCurrentRow(0)

    @Slot()
    def _on_file_selected(self, current: QListWidgetItem | None, _previous=None) -> None:
        d = current.data(Qt.UserRole) if current else None
        self._diff_view.setPlainText(d["diff"] if d else "")
