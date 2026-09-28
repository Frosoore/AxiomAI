"""ui/widgets/rules_inspector.py

Widget for inspecting and searching active game mechanics and universe rules.
"""

from __future__ import annotations

from typing import Any
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from core.localization import tr


class RulesInspectorWidget(QWidget):
    """Widget for inspecting, filtering, and debugging active rules in real time."""

    rule_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rules: list[dict[str, Any]] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Filter:"))
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search rules by name, condition, or tag...")
        self._search_input.textChanged.connect(self._apply_filter)
        search_layout.addWidget(self._search_input)
        layout.addLayout(search_layout)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Rule", "Conditions", "Actions"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._table)

    def set_rules(self, rules: list[dict[str, Any]]) -> None:
        """Populate the table with rules data."""
        self._rules = list(rules)
        self._apply_filter(self._search_input.text())

    def _apply_filter(self, text: str) -> None:
        query = text.strip().lower()
        self._table.setRowCount(0)
        for rule in self._rules:
            name = rule.get("name", rule.get("id", ""))
            conds = str(rule.get("conditions", ""))
            actions = str(rule.get("actions", ""))
            if query and query not in name.lower() and query not in conds.lower() and query not in actions.lower():
                continue
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(name))
            self._table.setItem(row, 1, QTableWidgetItem(conds))
            self._table.setItem(row, 2, QTableWidgetItem(actions))

    def _on_selection_changed(self) -> None:
        items = self._table.selectedItems()
        if items:
            rule_name = self._table.item(items[0].row(), 0).text()
            self.rule_selected.emit(rule_name)
