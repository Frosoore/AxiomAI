"""mods/axiom.living_memory/ui/memory_browser.py

Editable browser for a save's living-mode memory (facts + beliefs + models).

Surfaces what the engine has distilled from the story so the player can inspect
and correct it: mental models, evolving beliefs, and atomic facts. Mutations
go through headless engine helpers (axiom.facts / observations / mental_models)
without raw SQL in the UI.

Opened from Settings -> Memory -> Browse, or the tabletop Memory button.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.localization import tr

# Trend -> display label key + a soft accent colour. None = no tint (stable/new).
_TREND_STYLE: dict[str, tuple[str, QColor | None]] = {
    "strengthening": ("trend_strengthening", QColor(60, 140, 70)),
    "weakening": ("trend_weakening", QColor(170, 110, 40)),
    "stale": ("trend_stale", QColor(130, 130, 130)),
    "new": ("trend_new", None),
    "stable": ("trend_stable", None),
}

_ID_ROLE = Qt.UserRole


def _table(headers: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.SingleSelection)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    table.setWordWrap(True)
    return table


def _tune_columns(table: QTableWidget, *, stretch_col: int) -> None:
    header = table.horizontalHeader()
    for col in range(table.columnCount()):
        mode = QHeaderView.Stretch if col == stretch_col else QHeaderView.ResizeToContents
        header.setSectionResizeMode(col, mode)
    table.resizeRowsToContents()


def _selected_id(table: QTableWidget) -> int | None:
    rows = table.selectionModel().selectedRows()
    if not rows:
        return None
    item = table.item(rows[0].row(), 0)
    if item is None:
        return None
    raw = item.data(_ID_ROLE)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


class _TextEditDialog(QDialog):
    """Small multi-line editor: optional subject line + body text."""

    def __init__(
        self,
        title: str,
        body: str,
        *,
        subject: str | None = None,
        subject_label: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(480, 280)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._subject_edit: QLineEdit | None = None
        if subject is not None:
            self._subject_edit = QLineEdit(subject)
            form.addRow(subject_label or tr("memory_browser_col_subject"), self._subject_edit)
        self._body = QTextEdit()
        self._body.setPlainText(body)
        self._body.setAcceptRichText(False)
        form.addRow(self._body)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def body_text(self) -> str:
        return self._body.toPlainText().strip()

    def subject_text(self) -> str:
        if self._subject_edit is None:
            return ""
        return self._subject_edit.text().strip()


class MemoryBrowserDialog(QDialog):
    """Lists and edits a save's mental models, beliefs, and facts.

    Args:
        db_path:  The save database path (may be None -> 'load a game' notice).
        save_id:  The active save (same).
        now_turn: The current turn id (trend + horizon filter).
    """

    def __init__(
        self,
        db_path: str | None,
        save_id: str | None,
        now_turn: int | None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("memory_browser_title"))
        self.resize(820, 520)
        self._db_path = db_path
        self._save_id = save_id
        self._now_turn = now_turn if now_turn is not None else 0

        layout = QVBoxLayout(self)

        if not db_path or not save_id:
            layout.addWidget(QLabel(tr("memory_browser_no_session")))
            buttons = QDialogButtonBox(QDialogButtonBox.Close)
            buttons.rejected.connect(self.reject)
            buttons.accepted.connect(self.accept)
            layout.addWidget(buttons)
            return

        layout.addWidget(QLabel(tr("memory_browser_editor_hint")))

        self._tabs = QTabWidget()
        self._models_table = _table([
            tr("memory_browser_col_subject"),
            tr("memory_browser_col_profile"),
            tr("memory_browser_col_turn"),
        ])
        self._beliefs_table = _table([
            tr("memory_browser_col_subject"),
            tr("memory_browser_col_belief"),
            tr("memory_browser_col_trend"),
            tr("memory_browser_col_proof"),
            tr("memory_browser_col_turn"),
        ])
        self._facts_table = _table([
            tr("memory_browser_col_turn"),
            tr("memory_browser_col_type"),
            tr("memory_browser_col_fact"),
            tr("memory_browser_col_entities"),
        ])

        self._tabs.addTab(self._wrap_tab(self._models_table, "models"), tr("memory_browser_tab_models"))
        self._tabs.addTab(self._wrap_tab(self._beliefs_table, "beliefs"), tr("memory_browser_tab_beliefs"))
        self._tabs.addTab(self._wrap_tab(self._facts_table, "facts"), tr("memory_browser_tab_facts"))
        layout.addWidget(self._tabs)

        btn_row = QHBoxLayout()
        self._add_btn = QPushButton(tr("memory_browser_add_fact"))
        self._edit_btn = QPushButton(tr("memory_browser_edit"))
        self._delete_btn = QPushButton(tr("memory_browser_delete"))
        self._refresh_btn = QPushButton(tr("memory_browser_refresh"))
        self._add_btn.clicked.connect(self._on_add_fact)
        self._edit_btn.clicked.connect(self._on_edit)
        self._delete_btn.clicked.connect(self._on_delete)
        self._refresh_btn.clicked.connect(self._reload_all)
        btn_row.addWidget(self._add_btn)
        btn_row.addWidget(self._edit_btn)
        btn_row.addWidget(self._delete_btn)
        btn_row.addWidget(self._refresh_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._reload_all()
        self._on_tab_changed(self._tabs.currentIndex())

    def _wrap_tab(self, table: QTableWidget, kind: str) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        empty = QLabel("")
        empty.setObjectName(f"empty_{kind}")
        empty.setWordWrap(True)
        v.addWidget(empty)
        v.addWidget(table)
        return w

    def _empty_label(self, kind: str) -> QLabel | None:
        return self.findChild(QLabel, f"empty_{kind}")

    def _on_tab_changed(self, index: int) -> None:
        # Add fact only on Facts tab
        self._add_btn.setVisible(index == 2)

    # ------------------------------------------------------------------ load
    def _reload_all(self) -> None:
        self._load_models()
        self._load_beliefs()
        self._load_facts()

    def _load_models(self) -> None:
        from mods.axiom.living_memory.mental_models import get_mental_models

        table = self._models_table
        empty = self._empty_label("models")
        try:
            models = get_mental_models(
                self._db_path, self._save_id, max_turn_id=self._now_turn
            )
        except Exception:
            models = []
        table.setRowCount(0)
        if empty:
            empty.setText("" if models else tr("memory_browser_empty_models"))
            empty.setVisible(not models)
        table.setVisible(bool(models))
        if not models:
            return
        table.setRowCount(len(models))
        for row, m in enumerate(models):
            subject = m.subject.strip() or tr("memory_browser_world")
            subj_item = QTableWidgetItem(subject)
            subj_item.setData(_ID_ROLE, m.model_id)
            table.setItem(row, 0, subj_item)
            table.setItem(row, 1, QTableWidgetItem(m.summary))
            turn_item = QTableWidgetItem(str(m.updated_turn_id))
            turn_item.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, 2, turn_item)
        _tune_columns(table, stretch_col=1)

    def _load_beliefs(self) -> None:
        from mods.axiom.living_memory.observations import get_observations

        table = self._beliefs_table
        empty = self._empty_label("beliefs")
        try:
            beliefs = get_observations(
                self._db_path, self._save_id, max_turn_id=self._now_turn
            )
        except Exception:
            beliefs = []
        table.setRowCount(0)
        if empty:
            empty.setText("" if beliefs else tr("memory_browser_empty_beliefs"))
            empty.setVisible(not beliefs)
        table.setVisible(bool(beliefs))
        if not beliefs:
            return
        table.setRowCount(len(beliefs))
        for row, o in enumerate(beliefs):
            subject = o.subject.strip() or tr("memory_browser_world")
            trend = o.trend(self._now_turn)
            label_key, colour = _TREND_STYLE.get(trend, (None, None))
            trend_label = tr(label_key) if label_key else trend

            subj_item = QTableWidgetItem(subject)
            subj_item.setData(_ID_ROLE, o.observation_id)
            table.setItem(row, 0, subj_item)
            table.setItem(row, 1, QTableWidgetItem(o.statement))
            trend_item = QTableWidgetItem(trend_label)
            if colour is not None:
                trend_item.setForeground(colour)
            table.setItem(row, 2, trend_item)
            proof_item = QTableWidgetItem(str(o.proof_count))
            proof_item.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, 3, proof_item)
            turn_item = QTableWidgetItem(str(o.updated_turn_id))
            turn_item.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, 4, turn_item)
        _tune_columns(table, stretch_col=1)

    def _load_facts(self) -> None:
        from mods.axiom.living_memory.facts import get_facts

        table = self._facts_table
        empty = self._empty_label("facts")
        try:
            facts = get_facts(
                self._db_path, self._save_id, max_turn_id=self._now_turn
            )
        except Exception:
            facts = []
        table.setRowCount(0)
        if empty:
            empty.setText("" if facts else tr("memory_browser_empty_facts"))
            empty.setVisible(not facts)
        table.setVisible(bool(facts))
        if not facts:
            return
        table.setRowCount(len(facts))
        for row, f in enumerate(facts):
            turn_item = QTableWidgetItem(str(f.turn_id if f.turn_id is not None else ""))
            turn_item.setTextAlignment(Qt.AlignCenter)
            turn_item.setData(_ID_ROLE, f.fact_id)
            table.setItem(row, 0, turn_item)
            table.setItem(row, 1, QTableWidgetItem(f.fact_type))
            table.setItem(row, 2, QTableWidgetItem(f.statement))
            table.setItem(row, 3, QTableWidgetItem(", ".join(f.entities)))
        _tune_columns(table, stretch_col=2)

    # ---------------------------------------------------------------- actions
    def _current_kind(self) -> str:
        return ("models", "beliefs", "facts")[self._tabs.currentIndex()]

    def _current_table(self) -> QTableWidget:
        return (self._models_table, self._beliefs_table, self._facts_table)[
            self._tabs.currentIndex()
        ]

    def _on_edit(self) -> None:
        kind = self._current_kind()
        table = self._current_table()
        row_id = _selected_id(table)
        if row_id is None:
            QMessageBox.information(self, tr("memory_browser_title"), tr("memory_browser_select_row"))
            return
        if kind == "facts":
            self._edit_fact(row_id)
        elif kind == "beliefs":
            self._edit_belief(row_id)
        else:
            self._edit_model(row_id)

    def _edit_fact(self, fact_id: int) -> None:
        from mods.axiom.living_memory.facts import get_fact, update_fact

        f = get_fact(self._db_path, self._save_id, fact_id)
        if f is None:
            return
        dlg = _TextEditDialog(tr("memory_browser_edit"), f.statement, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        text = dlg.body_text()
        if not text:
            return
        if update_fact(self._db_path, self._save_id, fact_id, statement=text):
            self._load_facts()

    def _edit_belief(self, observation_id: int) -> None:
        from mods.axiom.living_memory.observations import get_observation, update_observation

        o = get_observation(self._db_path, self._save_id, observation_id)
        if o is None:
            return
        dlg = _TextEditDialog(
            tr("memory_browser_edit"),
            o.statement,
            subject=o.subject,
            parent=self,
        )
        if dlg.exec() != QDialog.Accepted:
            return
        text = dlg.body_text()
        if not text:
            return
        if update_observation(
            self._db_path,
            self._save_id,
            observation_id,
            statement=text,
            subject=dlg.subject_text(),
        ):
            self._load_beliefs()

    def _edit_model(self, model_id: int) -> None:
        from mods.axiom.living_memory.mental_models import get_mental_model, update_mental_model

        m = get_mental_model(self._db_path, self._save_id, model_id)
        if m is None:
            return
        dlg = _TextEditDialog(
            tr("memory_browser_edit"),
            m.summary,
            subject=m.subject,
            parent=self,
        )
        if dlg.exec() != QDialog.Accepted:
            return
        text = dlg.body_text()
        if not text:
            return
        if update_mental_model(
            self._db_path,
            self._save_id,
            model_id,
            summary=text,
            subject=dlg.subject_text(),
        ):
            self._load_models()

    def _on_delete(self) -> None:
        kind = self._current_kind()
        table = self._current_table()
        row_id = _selected_id(table)
        if row_id is None:
            QMessageBox.information(self, tr("memory_browser_title"), tr("memory_browser_select_row"))
            return
        if QMessageBox.question(
            self,
            tr("memory_browser_delete"),
            tr("memory_browser_delete_confirm"),
        ) != QMessageBox.Yes:
            return

        ok = False
        if kind == "facts":
            from mods.axiom.living_memory.facts import delete_fact
            ok = delete_fact(self._db_path, self._save_id, row_id)
            if ok:
                self._load_facts()
        elif kind == "beliefs":
            from mods.axiom.living_memory.observations import delete_observation
            ok = delete_observation(self._db_path, self._save_id, row_id)
            if ok:
                self._load_beliefs()
        else:
            from mods.axiom.living_memory.mental_models import delete_mental_model
            ok = delete_mental_model(self._db_path, self._save_id, row_id)
            if ok:
                self._load_models()

    def _on_add_fact(self) -> None:
        from mods.axiom.living_memory.facts import Fact, insert_facts

        text, ok = QInputDialog.getMultiLineText(
            self, tr("memory_browser_add_fact"), tr("memory_browser_col_fact"), ""
        )
        if not ok:
            return
        text = (text or "").strip()
        if not text:
            return
        insert_facts(
            self._db_path,
            self._save_id,
            int(self._now_turn or 0),
            [Fact(statement=text, fact_type="world")],
        )
        self._load_facts()
