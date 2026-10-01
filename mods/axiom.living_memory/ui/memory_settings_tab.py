"""mods/axiom.living_memory/ui/memory_settings_tab.py

UI settings tab component for axiom.living_memory.
Configures symbolic memory extraction, beliefs, mental models, and browsing.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from axiom.config import memory_mode_is_living
from core.localization import tr

try:
    from mods.axiom.help_system.ui.help_system import doc
except ImportError:
    def doc(widget: Any, _: str) -> Any:
        return widget


class MemorySettingsTab(QWidget):
    """Settings tab widget for Living Memory configuration and inspection."""

    tab_id: str = "living_memory"
    title_key: str = "tab_memory"

    extract_now_requested = Signal()
    view_memory_requested = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        db_path: str | None = None,
        can_browse_memory: bool = False,
    ) -> None:
        super().__init__(parent)
        self._db_path = db_path
        self._can_browse_memory = can_browse_memory
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        memory_form = QFormLayout()

        self._memory_mode_combo = doc(QComboBox(), "settings.memory_mode")
        self._memory_mode_combo.addItem(tr("memory_mode_lite"), "lite")
        self._memory_mode_combo.addItem(tr("memory_mode_living"), "living")

        self._memory_interval_spin = doc(QSpinBox(), "settings.memory_interval")
        self._memory_interval_spin.setRange(0, 100)
        self._memory_interval_spin.setSpecialValueText(tr("memory_interval_off"))
        self._memory_interval_spin.setValue(5)

        self._memory_model_edit = doc(QLineEdit(), "settings.memory_model")
        self._memory_model_edit.setPlaceholderText(tr("memory_fact_model_placeholder"))

        self._memory_reranker_cb = doc(
            QCheckBox(tr("memory_reranker_label")), "settings.memory_reranker"
        )
        self._memory_beliefs_cb = doc(
            QCheckBox(tr("memory_beliefs_label")), "settings.memory_beliefs"
        )
        self._memory_mental_models_cb = doc(
            QCheckBox(tr("memory_mental_models_label")), "settings.memory_mental_models"
        )
        self._memory_prompt_cache_cb = doc(
            QCheckBox(tr("memory_prompt_cache_label")), "settings.memory_prompt_cache"
        )

        self._memory_extract_btn = doc(QPushButton(tr("extract_now")), "settings.extract_now")
        self._memory_browse_btn = doc(QPushButton(tr("memory_browser_btn")), "settings.memory_browser")

        self._memory_mode_label = QLabel(tr("memory_mode_label"))
        self._memory_interval_label = QLabel(tr("memory_fact_interval_label"))
        self._memory_model_label = QLabel(tr("memory_fact_model_label"))

        memory_form.addRow(self._memory_mode_label, self._memory_mode_combo)
        memory_form.addRow(self._memory_interval_label, self._memory_interval_spin)
        memory_form.addRow(self._memory_model_label, self._memory_model_edit)
        memory_form.addRow("", self._memory_reranker_cb)
        memory_form.addRow("", self._memory_beliefs_cb)
        memory_form.addRow("", self._memory_mental_models_cb)
        memory_form.addRow("", self._memory_prompt_cache_cb)
        memory_form.addRow("", self._memory_extract_btn)
        memory_form.addRow("", self._memory_browse_btn)

        self._memory_mode_combo.currentIndexChanged.connect(self._on_memory_mode_changed)
        self._memory_beliefs_cb.toggled.connect(self._refresh_memory_controls)
        self._memory_extract_btn.clicked.connect(self._on_extract_now)
        self._memory_browse_btn.clicked.connect(self._on_view_memory)

        layout.addLayout(memory_form)
        layout.addStretch()

        self._refresh_memory_controls()

    def set_session_context(self, db_path: str | None, can_browse_memory: bool) -> None:
        """Update live session info for enabling extraction and browsing."""
        self._db_path = db_path
        self._can_browse_memory = can_browse_memory
        self._refresh_memory_controls()

    def _refresh_memory_controls(self) -> None:
        living = self._memory_mode_combo.currentData() == "living"
        self._memory_interval_spin.setEnabled(living)
        self._memory_model_edit.setEnabled(living)
        self._memory_beliefs_cb.setEnabled(living)
        self._memory_mental_models_cb.setEnabled(living and self._memory_beliefs_cb.isChecked())
        self._memory_extract_btn.setEnabled(living and bool(self._db_path))
        self._memory_browse_btn.setEnabled(self._can_browse_memory)

    @Slot()
    def _on_memory_mode_changed(self) -> None:
        self._refresh_memory_controls()

    @Slot()
    def _on_extract_now(self) -> None:
        self.extract_now_requested.emit()

    @Slot()
    def _on_view_memory(self) -> None:
        self.view_memory_requested.emit()

    def load_from_config(self, config: Any) -> None:
        """Populate controls from AppConfig or dictionary."""
        is_living = False
        if isinstance(config, dict):
            is_living = config.get("memory_mode") == "living"
        else:
            try:
                is_living = memory_mode_is_living(config)
            except Exception:
                is_living = getattr(config, "memory_mode", "lite") == "living"

        mem_idx = self._memory_mode_combo.findData("living" if is_living else "lite")
        if mem_idx >= 0:
            self._memory_mode_combo.setCurrentIndex(mem_idx)

        interval = getattr(config, "memory_fact_interval", None)
        if interval is None and isinstance(config, dict):
            interval = config.get("memory_fact_interval", 5)
        if interval is not None:
            self._memory_interval_spin.setValue(int(interval))

        model = getattr(config, "memory_fact_model", None)
        if model is None and isinstance(config, dict):
            model = config.get("memory_fact_model", "")
        self._memory_model_edit.setText(str(model or ""))

        reranker = getattr(config, "memory_reranker_enabled", None)
        if reranker is None and isinstance(config, dict):
            reranker = config.get("memory_reranker_enabled", False)
        self._memory_reranker_cb.setChecked(bool(reranker))

        beliefs = getattr(config, "memory_beliefs_enabled", None)
        if beliefs is None and isinstance(config, dict):
            beliefs = config.get("memory_beliefs_enabled", False)
        self._memory_beliefs_cb.setChecked(bool(beliefs))

        mental_models = getattr(config, "memory_mental_models_enabled", None)
        if mental_models is None and isinstance(config, dict):
            mental_models = config.get("memory_mental_models_enabled", False)
        self._memory_mental_models_cb.setChecked(bool(mental_models))

        prompt_cache = getattr(config, "memory_prompt_cache_enabled", None)
        if prompt_cache is None and isinstance(config, dict):
            prompt_cache = config.get("memory_prompt_cache_enabled", False)
        self._memory_prompt_cache_cb.setChecked(bool(prompt_cache))

        self._refresh_memory_controls()

    def collect_config(
        self,
        config: Any = None,
        target_dict: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Read UI fields into a dictionary and optionally apply to config/target_dict."""
        data = {
            "memory_mode": self._memory_mode_combo.currentData() or "lite",
            "memory_fact_interval": self._memory_interval_spin.value(),
            "memory_fact_model": self._memory_model_edit.text().strip(),
            "memory_reranker_enabled": self._memory_reranker_cb.isChecked(),
            "memory_beliefs_enabled": self._memory_beliefs_cb.isChecked(),
            "memory_mental_models_enabled": self._memory_mental_models_cb.isChecked(),
            "memory_prompt_cache_enabled": self._memory_prompt_cache_cb.isChecked(),
        }
        if target_dict is not None:
            target_dict.update(data)
        if config is not None:
            for k, v in data.items():
                if hasattr(config, k):
                    setattr(config, k, v)
                elif isinstance(config, dict):
                    config[k] = v
        return data

    def retranslate_ui(self) -> None:
        """Update localized text for all labels and controls."""
        self._memory_mode_label.setText(tr("memory_mode_label"))
        self._memory_mode_combo.setItemText(0, tr("memory_mode_lite"))
        self._memory_mode_combo.setItemText(1, tr("memory_mode_living"))
        self._memory_interval_label.setText(tr("memory_fact_interval_label"))
        self._memory_interval_spin.setSpecialValueText(tr("memory_interval_off"))
        self._memory_model_label.setText(tr("memory_fact_model_label"))
        self._memory_model_edit.setPlaceholderText(tr("memory_fact_model_placeholder"))
        self._memory_reranker_cb.setText(tr("memory_reranker_label"))
        self._memory_beliefs_cb.setText(tr("memory_beliefs_label"))
        self._memory_mental_models_cb.setText(tr("memory_mental_models_label"))
        self._memory_prompt_cache_cb.setText(tr("memory_prompt_cache_label"))
        self._memory_extract_btn.setText(tr("extract_now"))
        self._memory_browse_btn.setText(tr("memory_browser_btn"))
