"""mods/axiom.illustrations/ui/image_settings_tab.py

UI settings tab component for axiom.illustrations.
Configures scene illustration generation (local SD, ComfyUI, Gemini, Mock).
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QComboBox,
)

from core.localization import tr

try:
    from mods.axiom.help_system.ui.help_system import doc
except ImportError:
    def doc(widget: Any, _: str) -> Any:
        return widget


class ImageSettingsTab(QWidget):
    """Settings tab widget for AI image and scene illustration configuration."""

    tab_id: str = "illustrations"
    title_key: str = "tab_image"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        image_form = QFormLayout()

        self._image_enabled_cb = doc(QCheckBox(tr("image_enable")), "settings.image_enable")

        self._image_backend_combo = doc(QComboBox(), "settings.image_backend")
        self._image_backend_combo.addItem("Mock Generator", "mock")
        self._image_backend_combo.addItem("Stable Diffusion (WebUI)", "stable_diffusion")
        self._image_backend_combo.addItem("ComfyUI", "comfyui")
        self._image_backend_combo.addItem("Google Gemini (cloud)", "gemini")

        self._image_url = doc(QLineEdit(), "settings.image_url")
        self._image_url.setPlaceholderText("e.g. http://127.0.0.1:7860")

        self._image_gemini_model = doc(QLineEdit(), "settings.image_gemini_model")
        self._image_gemini_model.setPlaceholderText("gemini-2.5-flash-image")

        self._image_width_spin = doc(QSpinBox(), "settings.image_size")
        self._image_width_spin.setRange(64, 4096)
        self._image_width_spin.setSingleStep(64)
        self._image_width_spin.setValue(512)

        self._image_height_spin = doc(QSpinBox(), "settings.image_size")
        self._image_height_spin.setRange(64, 4096)
        self._image_height_spin.setSingleStep(64)
        self._image_height_spin.setValue(512)

        self._image_steps_spin = doc(QSpinBox(), "settings.image_steps")
        self._image_steps_spin.setRange(1, 150)
        self._image_steps_spin.setValue(20)

        self._image_cfg_spin = doc(QDoubleSpinBox(), "settings.image_cfg")
        self._image_cfg_spin.setRange(1.0, 30.0)
        self._image_cfg_spin.setSingleStep(0.5)
        self._image_cfg_spin.setValue(7.0)

        self._image_timeout_spin = doc(QSpinBox(), "settings.image_timeout")
        self._image_timeout_spin.setRange(10, 900)
        self._image_timeout_spin.setSingleStep(10)
        self._image_timeout_spin.setSuffix(" s")
        self._image_timeout_spin.setValue(120)

        self._image_workflow = doc(QLineEdit(), "settings.image_workflow")
        self._image_workflow.setPlaceholderText("Path to workflow JSON file or raw JSON template")

        self._image_backend_label = QLabel(tr("image_backend"))
        self._image_url_label = QLabel(tr("image_api_url"))
        self._image_gemini_model_label = QLabel(tr("image_gemini_model"))
        self._image_width_label = QLabel(tr("image_width"))
        self._image_height_label = QLabel(tr("image_height"))
        self._image_steps_label = QLabel(tr("image_steps"))
        self._image_cfg_label = QLabel(tr("image_cfg_scale"))
        self._image_timeout_label = QLabel(tr("image_timeout"))
        self._image_workflow_label = QLabel(tr("image_workflow"))

        image_form.addRow("", self._image_enabled_cb)
        image_form.addRow(self._image_backend_label, self._image_backend_combo)
        image_form.addRow(self._image_url_label, self._image_url)
        image_form.addRow(self._image_gemini_model_label, self._image_gemini_model)
        image_form.addRow(self._image_width_label, self._image_width_spin)
        image_form.addRow(self._image_height_label, self._image_height_spin)
        image_form.addRow(self._image_steps_label, self._image_steps_spin)
        image_form.addRow(self._image_cfg_label, self._image_cfg_spin)
        image_form.addRow(self._image_timeout_label, self._image_timeout_spin)
        image_form.addRow(self._image_workflow_label, self._image_workflow)

        layout.addLayout(image_form)
        layout.addStretch()

    def load_from_config(self, config: Any) -> None:
        """Populate controls from AppConfig or dictionary."""
        enabled = getattr(config, "image_generation_enabled", None)
        if enabled is None and isinstance(config, dict):
            enabled = config.get("image_generation_enabled", False)
        self._image_enabled_cb.setChecked(bool(enabled))

        backend = getattr(config, "image_backend", None)
        if backend is None and isinstance(config, dict):
            backend = config.get("image_backend", "mock")
        idx = self._image_backend_combo.findData(backend or "mock")
        if idx >= 0:
            self._image_backend_combo.setCurrentIndex(idx)

        url = getattr(config, "image_api_url", None)
        if url is None and isinstance(config, dict):
            url = config.get("image_api_url", "")
        self._image_url.setText(str(url or ""))

        model = getattr(config, "image_gemini_model", None)
        if model is None and isinstance(config, dict):
            model = config.get("image_gemini_model", "")
        self._image_gemini_model.setText(str(model or "gemini-2.5-flash-image"))

        width = getattr(config, "image_width", None)
        if width is None and isinstance(config, dict):
            width = config.get("image_width", 512)
        if width is not None:
            self._image_width_spin.setValue(int(width))

        height = getattr(config, "image_height", None)
        if height is None and isinstance(config, dict):
            height = config.get("image_height", 512)
        if height is not None:
            self._image_height_spin.setValue(int(height))

        steps = getattr(config, "image_steps", None)
        if steps is None and isinstance(config, dict):
            steps = config.get("image_steps", 20)
        if steps is not None:
            self._image_steps_spin.setValue(int(steps))

        cfg_scale = getattr(config, "image_cfg_scale", None)
        if cfg_scale is None and isinstance(config, dict):
            cfg_scale = config.get("image_cfg_scale", 7.0)
        if cfg_scale is not None:
            self._image_cfg_spin.setValue(float(cfg_scale))

        timeout = getattr(config, "image_timeout", None)
        if timeout is None and isinstance(config, dict):
            timeout = config.get("image_timeout", 120)
        if timeout is not None:
            self._image_timeout_spin.setValue(int(timeout))

        workflow = getattr(config, "image_comfyui_workflow", None)
        if workflow is None and isinstance(config, dict):
            workflow = config.get("image_comfyui_workflow", "")
        self._image_workflow.setText(str(workflow or ""))

    def collect_config(
        self,
        config: Any = None,
        target_dict: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Read UI fields into a dictionary and optionally apply to config/target_dict."""
        data = {
            "image_generation_enabled": self._image_enabled_cb.isChecked(),
            "image_backend": self._image_backend_combo.currentData(),
            "image_api_url": self._image_url.text().strip(),
            "image_width": self._image_width_spin.value(),
            "image_height": self._image_height_spin.value(),
            "image_steps": self._image_steps_spin.value(),
            "image_cfg_scale": self._image_cfg_spin.value(),
            "image_timeout": self._image_timeout_spin.value(),
            "image_comfyui_workflow": self._image_workflow.text().strip(),
            "image_gemini_model": self._image_gemini_model.text().strip() or "gemini-2.5-flash-image",
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
        self._image_enabled_cb.setText(tr("image_enable"))
        self._image_backend_label.setText(tr("image_backend"))
        self._image_url_label.setText(tr("image_api_url"))
        self._image_gemini_model_label.setText(tr("image_gemini_model"))
        self._image_width_label.setText(tr("image_width"))
        self._image_height_label.setText(tr("image_height"))
        self._image_steps_label.setText(tr("image_steps"))
        self._image_cfg_label.setText(tr("image_cfg_scale"))
        self._image_timeout_label.setText(tr("image_timeout"))
        self._image_workflow_label.setText(tr("image_workflow"))
