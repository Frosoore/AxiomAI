"""Read-only browser for a save's living-mode memory (facts + beliefs).

Surfaces what the engine has distilled from the story so the player can inspect
it: the evolving **beliefs** (with their computed trend — strengthening, fading,
stale…) and the atomic **facts** they are built from. Pure read path: it opens
its own short-lived connections via the engine helpers and never mutates state.

Opened from the Settings → Memory tab; only meaningful in Living mode, but it
degrades to friendly "nothing yet" messages otherwise.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.localization import tr

# Trend → display label key + a soft accent colour. None = no tint (stable/new).
_TREND_STYLE: dict[str, tuple[str, QColor | None]] = {
    "strengthening": ("trend_strengthening", QColor(60, 140, 70)),
    "weakening": ("trend_weakening", QColor(170, 110, 40)),
    "stale": ("trend_stale", QColor(130, 130, 130)),
    "new": ("trend_new", None),
    "stable": ("trend_stable", None),
}


def _readonly_table(headers: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    table.setWordWrap(True)
    return table


class MemoryBrowserDialog(QDialog):
    """Lists a save's beliefs (with trend) and facts, bounded by the current turn.

    Args:
        db_path:  The save database path (may be ``None`` → "load a game" notice).
        save_id:  The active save (same).
        now_turn: The current turn id, used to compute each belief's trend at the
                  right "now" and to exclude any future-turn rows.
    """

    def __init__(self, db_path: str | None, save_id: str | None,
                 now_turn: int | None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("memory_browser_title"))
        self.resize(760, 480)
        self._db_path = db_path
        self._save_id = save_id
        self._now_turn = now_turn

        layout = QVBoxLayout(self)

        if not db_path or not save_id:
            layout.addWidget(QLabel(tr("memory_browser_no_session")))
        else:
            tabs = QTabWidget()
            tabs.addTab(self._build_beliefs_tab(), tr("memory_browser_tab_beliefs"))
            tabs.addTab(self._build_facts_tab(), tr("memory_browser_tab_facts"))
            layout.addWidget(tabs)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------ beliefs
    def _build_beliefs_tab(self) -> QWidget:
        from axiom.observations import get_observations

        widget = QWidget()
        vbox = QVBoxLayout(widget)
        try:
            beliefs = get_observations(self._db_path, self._save_id,
                                       max_turn_id=self._now_turn)
        except Exception:
            beliefs = []

        if not beliefs:
            vbox.addWidget(QLabel(tr("memory_browser_empty_beliefs")))
            return widget

        headers = [
            tr("memory_browser_col_subject"),
            tr("memory_browser_col_belief"),
            tr("memory_browser_col_trend"),
            tr("memory_browser_col_proof"),
            tr("memory_browser_col_turn"),
        ]
        table = _readonly_table(headers)
        table.setRowCount(len(beliefs))
        for row, o in enumerate(beliefs):
            subject = o.subject.strip() or tr("memory_browser_world")
            trend = o.trend(self._now_turn)
            label_key, colour = _TREND_STYLE.get(trend, (None, None))
            trend_label = tr(label_key) if label_key else trend

            subject_item = QTableWidgetItem(subject)
            belief_item = QTableWidgetItem(o.statement)
            trend_item = QTableWidgetItem(trend_label)
            if colour is not None:
                trend_item.setForeground(colour)
            proof_item = QTableWidgetItem(str(o.proof_count))
            proof_item.setTextAlignment(Qt.AlignCenter)
            turn_item = QTableWidgetItem(str(o.updated_turn_id))
            turn_item.setTextAlignment(Qt.AlignCenter)

            table.setItem(row, 0, subject_item)
            table.setItem(row, 1, belief_item)
            table.setItem(row, 2, trend_item)
            table.setItem(row, 3, proof_item)
            table.setItem(row, 4, turn_item)

        self._tune_columns(table, stretch_col=1)
        vbox.addWidget(table)
        return widget

    # -------------------------------------------------------------------- facts
    def _build_facts_tab(self) -> QWidget:
        from axiom.facts import get_facts

        widget = QWidget()
        vbox = QVBoxLayout(widget)
        try:
            facts = get_facts(self._db_path, self._save_id, max_turn_id=self._now_turn)
        except Exception:
            facts = []

        if not facts:
            vbox.addWidget(QLabel(tr("memory_browser_empty_facts")))
            return widget

        headers = [
            tr("memory_browser_col_turn"),
            tr("memory_browser_col_type"),
            tr("memory_browser_col_fact"),
            tr("memory_browser_col_entities"),
        ]
        table = _readonly_table(headers)
        table.setRowCount(len(facts))
        for row, f in enumerate(facts):
            turn_item = QTableWidgetItem(str(f.turn_id if f.turn_id is not None else ""))
            turn_item.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, 0, turn_item)
            table.setItem(row, 1, QTableWidgetItem(f.fact_type))
            table.setItem(row, 2, QTableWidgetItem(f.statement))
            table.setItem(row, 3, QTableWidgetItem(", ".join(f.entities)))

        self._tune_columns(table, stretch_col=2)
        vbox.addWidget(table)
        return widget

    @staticmethod
    def _tune_columns(table: QTableWidget, *, stretch_col: int) -> None:
        """Let the main text column take the slack, size the rest to content."""
        header = table.horizontalHeader()
        for col in range(table.columnCount()):
            mode = QHeaderView.Stretch if col == stretch_col else QHeaderView.ResizeToContents
            header.setSectionResizeMode(col, mode)
        table.resizeRowsToContents()
