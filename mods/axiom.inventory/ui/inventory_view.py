"""mods/axiom.inventory/ui/inventory_view.py

Interactive tree/nested view for entity inventories and container hierarchies.
Contributed to axiom.ui.qt:sidebar_widget by axiom.inventory.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.localization import tr


_RARITY_COLORS: dict[str, str] = {
    "common": "white",
    "uncommon": "#2ecc71",
    "rare": "#4fa3ff",
    "epic": "#a335ee",
    "legendary": "#ff8000",
    "artifact": "#e74c3c",
}


class InventoryTreeView(QWidget):
    """Hierarchical and container-aware inventory view widget."""

    widget_id: str = "inventory"
    title_key: str = "inventory"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setSpacing(6)
        self._content_layout.setContentsMargins(2, 2, 2, 2)
        self._content_layout.addStretch()
        self._scroll.setWidget(self._content)

        layout.addWidget(self._scroll)

        self._placeholder = QLabel(f"({tr('no_sessions')})")
        self._placeholder.setStyleSheet("color: gray;")
        self._content_layout.insertWidget(0, self._placeholder)

    @Slot(dict)
    def refresh_inventory(self, inventory_data: dict[str, Any] | list[dict[str, Any]] | None) -> None:
        """Rebuild the inventory display from dictionary or tree list."""
        # Clear existing item groups
        while self._content_layout.count() > 1:
            child = self._content_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not inventory_data:
            placeholder = QLabel(f"({tr('no_sessions')})")
            placeholder.setStyleSheet("color: gray;")
            self._content_layout.insertWidget(0, placeholder)
            return

        if isinstance(inventory_data, list):
            # Nested tree format
            tree_widget = QTreeWidget()
            tree_widget.setHeaderLabels([tr("inventory"), tr("quantity") if tr("quantity") != "quantity" else "Qty"])
            tree_widget.setColumnCount(2)
            tree_widget.setColumnWidth(0, 180)
            self._populate_tree_nodes(tree_widget.invisibleRootItem(), inventory_data)
            tree_widget.expandAll()
            self._content_layout.insertWidget(0, tree_widget)
            return

        # Map entity_id -> items list
        has_items = False
        for entity_id, items in inventory_data.items():
            if not items:
                continue
            has_items = True
            group = QGroupBox(f"{entity_id}")
            group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            form = QFormLayout(group)
            form.setSpacing(2)

            for item in items:
                name = item.get("name", "Unknown")
                qty = item.get("quantity", 1)
                rarity = str(item.get("rarity", "common")).lower()
                color = _RARITY_COLORS.get(rarity, "white")

                name_label = QLabel(f"<b>{name}</b>")
                name_label.setStyleSheet(f"color: {color}; font-size: 11px;")
                qty_label = QLabel(f"x{qty}")
                qty_label.setStyleSheet("font-size: 11px;")
                form.addRow(name_label, qty_label)

            insert_idx = max(0, self._content_layout.count() - 1)
            self._content_layout.insertWidget(insert_idx, group)

        if not has_items:
            placeholder = QLabel(f"({tr('no_sessions')})")
            placeholder.setStyleSheet("color: gray;")
            self._content_layout.insertWidget(0, placeholder)

    def _populate_tree_nodes(self, parent_item: QTreeWidgetItem, items: list[dict[str, Any]]) -> None:
        for node in items:
            name = node.get("name") or node.get("item_id", "Unknown")
            qty = node.get("quantity", 1)
            rarity = str(node.get("rarity", "common")).lower()

            item = QTreeWidgetItem(parent_item)
            item.setText(0, name)
            item.setText(1, f"x{qty}")

            color = _RARITY_COLORS.get(rarity, "white")
            item.setForeground(0, Qt.GlobalColor.white if color == "white" else Qt.GlobalColor.cyan)

            children = node.get("children") or node.get("contained_items") or []
            if children:
                self._populate_tree_nodes(item, children)

    def refresh(self, data: Any) -> None:
        """Generic slot for refreshing data."""
        self.refresh_inventory(data)

    def retranslate_ui(self) -> None:
        """Retranslate labels."""
        pass
