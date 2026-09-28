"""
ui/constants_sidebar.py

Dynamic world-state sidebar for the Tabletop screen.

Displays all entity stats in real time, updated after every turn via
the refresh() slot which is connected to DbWorker.stats_loaded.

THREADING RULE: refresh() MUST only be called from the main thread via
the Signal/Slot mechanism.  Never call it directly from a worker thread.
"""

from __future__ import annotations

from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from core.localization import tr


class ConstantsSidebar(QWidget):
    """Live entity stats panel for the Tabletop screen.

    Updated via the refresh() slot which is connected to
    DbWorker.stats_loaded after every Arbitrator turn and rewind.
    """

    def __init__(self, parent=None, config=None) -> None:
        super().__init__(parent)
        self._config = config
        self.setMinimumWidth(200)
        self.setMaximumWidth(320)
        self._setup_ui()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        from PySide6.QtWidgets import QTabWidget
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(4, 4, 4, 4)

        self._header = QLabel(f"<b>{tr('tab_meta')}</b>")
        layout.addWidget(self._header)

        self._tabs = QTabWidget()
        
        # Stats Tab
        self._stats_scroll = QScrollArea()
        self._stats_scroll.setWidgetResizable(True)
        self._stats_content = QWidget()
        self._entities_layout = QVBoxLayout(self._stats_content)
        self._entities_layout.setSpacing(6)
        self._entities_layout.setContentsMargins(2, 2, 2, 2)
        self._entities_layout.addStretch()
        self._stats_scroll.setWidget(self._stats_content)
        
        # Inventory Tab
        self._inv_scroll = QScrollArea()
        self._inv_scroll.setWidgetResizable(True)
        self._inv_content = QWidget()
        self._inv_layout = QVBoxLayout(self._inv_content)
        self._inv_layout.setSpacing(6)
        self._inv_layout.setContentsMargins(2, 2, 2, 2)
        self._inv_layout.addStretch()
        self._inv_scroll.setWidget(self._inv_content)

        # Timeline Tab
        self._time_scroll = QScrollArea()
        self._time_scroll.setWidgetResizable(True)
        self._time_content = QWidget()
        self._time_layout = QVBoxLayout(self._time_content)
        self._time_layout.setSpacing(6)
        self._time_layout.setContentsMargins(2, 2, 2, 2)
        self._time_layout.addStretch()
        self._time_scroll.setWidget(self._time_content)

        from axiom.config import load_config
        from axiom.kernel.loader import is_mod_enabled
        cfg = self._config or load_config()

        self._tabs.addTab(self._stats_scroll, tr("stats"))
        if is_mod_enabled("axiom.inventory", cfg):
            self._tabs.addTab(self._inv_scroll, tr("inventory"))
        if is_mod_enabled("axiom.time", cfg):
            self._tabs.addTab(self._time_scroll, tr("timeline"))

        from ui.help_system import doc_tab
        doc_tab(self._tabs, 0, "tabletop.sidebar_stats")
        inv_idx = self._tabs.indexOf(self._inv_scroll)
        if inv_idx != -1:
            doc_tab(self._tabs, inv_idx, "tabletop.sidebar_inventory")
        time_idx = self._tabs.indexOf(self._time_scroll)
        if time_idx != -1:
            doc_tab(self._tabs, time_idx, "tabletop.sidebar_timeline")
        layout.addWidget(self._tabs)

        # Contributed sidebar widgets from mods (axiom.ui.qt:sidebar_widget)
        from axiom.kernel.registry import get_active_registry
        reg = get_active_registry()
        if reg:
            for item in reg.get_slot_contributions("axiom.ui.qt:sidebar_widget"):
                if isinstance(item, tuple) and len(item) == 2:
                    self._tabs.addTab(item[1], str(item[0]))
                elif isinstance(item, dict) and "title" in item and "widget" in item:
                    self._tabs.addTab(item["widget"], str(item["title"]))

    def update_mod_visibility(self, config=None) -> None:
        """Dynamically add or remove mod-dependent tabs based on active mods."""
        from axiom.config import load_config
        from axiom.kernel.loader import is_mod_enabled
        from core.localization import tr
        if config is not None:
            self._config = config
        cfg = self._config or load_config()

        inv_enabled = is_mod_enabled("axiom.inventory", cfg)
        inv_idx = self._tabs.indexOf(self._inv_scroll)
        if not inv_enabled and inv_idx != -1:
            self._tabs.removeTab(inv_idx)
        elif inv_enabled and inv_idx == -1:
            stats_idx = self._tabs.indexOf(self._stats_scroll)
            insert_pos = stats_idx + 1 if stats_idx != -1 else 0
            self._tabs.insertTab(insert_pos, self._inv_scroll, tr("inventory"))

        time_enabled = is_mod_enabled("axiom.time", cfg)
        time_idx = self._tabs.indexOf(self._time_scroll)
        if not time_enabled and time_idx != -1:
            self._tabs.removeTab(time_idx)
        elif time_enabled and time_idx == -1:
            self._tabs.addTab(self._time_scroll, tr("timeline"))

    def retranslate_ui(self) -> None:
        """Refresh tab titles and header."""
        self._header.setText(f"<b>{tr('tab_meta')}</b>")
        stats_idx = self._tabs.indexOf(self._stats_scroll)
        if stats_idx != -1:
            self._tabs.setTabText(stats_idx, tr("stats"))
        inv_idx = self._tabs.indexOf(self._inv_scroll)
        if inv_idx != -1:
            self._tabs.setTabText(inv_idx, tr("inventory"))
        time_idx = self._tabs.indexOf(self._time_scroll)
        if time_idx != -1:
            self._tabs.setTabText(time_idx, tr("timeline"))

    @Slot(list)
    def refresh(self, entity_snapshots: list[dict]) -> None:
        """Rebuild the stats display from fresh entity snapshot data."""
        from core.localization import tr, fmt_num
        # Remove all existing widgets (except the trailing stretch)
        while self._entities_layout.count() > 1:
            item = self._entities_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not entity_snapshots:
            placeholder = QLabel(f"({tr('no_sessions')})")
            placeholder.setStyleSheet("color: gray;")
            self._entities_layout.insertWidget(0, placeholder)
            return

        for snap in entity_snapshots:
            if not isinstance(snap, dict):
                continue
            entity_id: str = snap.get("entity_id", "unknown")
            name: str = snap.get("name", entity_id)
            entity_type: str = snap.get("entity_type", "")
            stats: dict = snap.get("stats") or {} 

            group_title = f"{name}"
            if entity_type:
                # Localize entity type
                translated_type = tr(f"entity_{entity_type}")
                # Use localized spacing
                from axiom.config import load_config
                lang = getattr(load_config(), "language", "en")
                if lang in ("zh", "ja", "ko"):
                    group_title += f"[{translated_type}]"
                else:
                    group_title += f" [{translated_type}]"
            group = QGroupBox(group_title)
            group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            form = QFormLayout(group)
            form.setSpacing(2)

            if stats:
                for stat_key, stat_value in stats.items():
                    # Use stat_fmt if available
                    label_text = tr("stat_fmt", stat=stat_key, val="").rstrip(":").rstrip(" :").rstrip("：")
                    from axiom.config import load_config
                    lang = getattr(load_config(), "language", "en")
                    colon = "：" if lang in ("zh", "ja") else ":"
                    if lang == "fr": colon = " :"
                    
                    key_label = QLabel(label_text + colon)
                    key_label.setStyleSheet("font-size: 11px;")
                    val_label = QLabel(fmt_num(stat_value))
                    val_label.setStyleSheet("font-size: 11px; font-weight: bold;")
                    form.addRow(key_label, val_label)
            else:
                form.addRow(QLabel(f"({tr('no_sessions')})"))

            # Insert before the trailing stretch
            insert_idx = max(0, self._entities_layout.count() - 1)
            self._entities_layout.insertWidget(insert_idx, group)

    @Slot(dict)
    def refresh_inventory(self, inventory_data: dict) -> None:
        """Rebuild the inventory display."""
        # Remove all existing widgets (except the trailing stretch)
        while self._inv_layout.count() > 1:
            item = self._inv_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not inventory_data:
            placeholder = QLabel(f"({tr('no_sessions')})")
            placeholder.setStyleSheet("color: gray;")
            self._inv_layout.insertWidget(0, placeholder)
            return

        for entity_id, items in inventory_data.items():
            if not items:
                continue
                
            group = QGroupBox(f"{entity_id}")
            group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            form = QFormLayout(group)
            form.setSpacing(2)

            for item in items:
                name = item.get("name", "Unknown")
                qty = item.get("quantity", 1)
                rarity = item.get("rarity", "common")
                
                # Simple color-coding for rarity
                rarity_colors = {
                    "common": "white",
                    "rare": "#4fa3ff",
                    "epic": "#a335ee",
                    "legendary": "#ff8000"
                }
                color = rarity_colors.get(rarity.lower(), "white")
                
                name_label = QLabel(f"<b>{name}</b>")
                name_label.setStyleSheet(f"color: {color}; font-size: 11px;")
                qty_label = QLabel(f"x{qty}")
                qty_label.setStyleSheet("font-size: 11px;")
                
                form.addRow(name_label, qty_label)

            insert_idx = max(0, self._inv_layout.count() - 1)
            self._inv_layout.insertWidget(insert_idx, group)

    @Slot(list)
    def refresh_timeline(self, timeline_events: list[dict]) -> None:
        """Rebuild the timeline display."""
        # Remove all existing widgets (except the trailing stretch)
        while self._time_layout.count() > 1:
            item = self._time_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not timeline_events:
            placeholder = QLabel(f"({tr('no_sessions')})")
            placeholder.setStyleSheet("color: gray;")
            self._time_layout.insertWidget(0, placeholder)
            return

        from axiom.db_helpers import get_time_of_day_context
        for event in timeline_events:
            time_str = get_time_of_day_context(event.get("in_game_time", 0))
            turn_id = event.get("turn_id", 0)
            desc = event.get("description", "")
            
            turn_part = tr("turn_fmt", count=turn_id)
            group = QGroupBox(f"{turn_part} - {time_str}")
            group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            vbox = QVBoxLayout(group)
            
            text_label = QLabel(desc)
            text_label.setWordWrap(True)
            text_label.setStyleSheet("font-size: 11px;")
            vbox.addWidget(text_label)

            insert_idx = max(0, self._time_layout.count() - 1)
            self._time_layout.insertWidget(insert_idx, group)
