"""mods/axiom.time/ui/timeline_view.py

Interactive timeline and chronological narrative log view.
Contributed to axiom.ui.qt:sidebar_widget by axiom.time.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QGroupBox,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.localization import tr


class TimelineView(QWidget):
    """Chronological event timeline sidebar widget."""

    widget_id: str = "timeline"
    title_key: str = "timeline"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._time_scroll = QScrollArea()
        self._time_scroll.setWidgetResizable(True)
        self._time_content = QWidget()
        self._time_layout = QVBoxLayout(self._time_content)
        self._time_layout.setSpacing(6)
        self._time_layout.setContentsMargins(2, 2, 2, 2)
        self._time_layout.addStretch()
        self._time_scroll.setWidget(self._time_content)

        layout.addWidget(self._time_scroll)

        self._placeholder = QLabel(f"({tr('no_sessions')})")
        self._placeholder.setStyleSheet("color: gray;")
        self._time_layout.insertWidget(0, self._placeholder)

    @Slot(list)
    def refresh_timeline(self, timeline_events: list[dict[str, Any]] | None) -> None:
        """Rebuild the timeline display from event list."""
        while self._time_layout.count() > 1:
            item = self._time_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not timeline_events:
            placeholder = QLabel(f"({tr('no_sessions')})")
            placeholder.setStyleSheet("color: gray;")
            self._time_layout.insertWidget(0, placeholder)
            return

        try:
            from axiom.db_helpers import get_time_of_day_context
        except ImportError:
            def get_time_of_day_context(m: int) -> str:
                return f"{m}m"

        for event in timeline_events:
            time_str = get_time_of_day_context(event.get("in_game_time", 0))
            turn_id = event.get("turn_id", 0)
            desc = event.get("description", "")

            try:
                turn_part = tr("turn_fmt", count=turn_id)
            except Exception:
                turn_part = f"Turn {turn_id}"

            group = QGroupBox(f"{turn_part} - {time_str}")
            group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            vbox = QVBoxLayout(group)

            text_label = QLabel(desc)
            text_label.setWordWrap(True)
            text_label.setStyleSheet("font-size: 11px;")
            vbox.addWidget(text_label)

            insert_idx = max(0, self._time_layout.count() - 1)
            self._time_layout.insertWidget(insert_idx, group)

    def refresh(self, data: Any) -> None:
        """Generic slot for refreshing data."""
        self.refresh_timeline(data)

    def retranslate_ui(self) -> None:
        """Retranslate labels."""
        pass


TimelineWidget = TimelineView
