"""mods/axiom.providers/ui/providers_settings_tabs.py

UI settings tabs for axiom.providers:
- UniversalLLMSettingsTab: local & OpenAI-compatible LLM endpoints
- CloudSettingsTab: cloud LLM providers (Gemini, Claude, Venice, Fireworks, OpenAI, OpenRouter)
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from axiom.config import (
    AppConfig,
    CLOUD_BACKENDS,
    OPENAI_COMPAT_PROVIDERS,
    build_llm_from_config,
    get_builtin_keys,
)
from core.localization import tr

try:
    from mods.axiom.help_system.ui.help_system import doc
except ImportError:
    def doc(widget: Any, _: str) -> Any:
        return widget


_CLOUD_PROVIDERS: tuple[tuple[str, str], ...] = (
    ("Google Gemini", "gemini"),
    ("Anthropic Claude", "claude"),
    ("Venice AI", "venice"),
    ("Fireworks AI", "fireworks"),
    ("OpenAI", "openai"),
    ("OpenRouter", "openrouter"),
)

_CLOUD_MODEL_PLACEHOLDERS: dict[str, str] = {
    "gemini": "e.g. gemini-2.0-flash",
    "claude": "e.g. claude-opus-4-8",
    "venice": "e.g. zai-org-glm-4.7",
    "fireworks": "e.g. accounts/fireworks/models/gpt-oss-120b",
    "openai": "e.g. gpt-4.1-mini",
    "openrouter": "e.g. openrouter/auto",
}


class UniversalLLMSettingsTab(QWidget):
    """Settings tab for OpenAI-compatible local or custom endpoints."""

    tab_id: str = "universal_llm"
    title_key: str = "tab_llm"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._test_worker: Any = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        univ_form = QFormLayout()
        self._univ_url = doc(QLineEdit(), "settings.base_url")
        self._univ_url.setPlaceholderText("http://localhost:11434/v1")
        self._univ_key = doc(QLineEdit(), "settings.api_key")
        self._univ_key.setEchoMode(QLineEdit.Password)
        self._univ_key.setPlaceholderText(tr("optional_key"))
        self._univ_model = doc(QLineEdit(), "settings.main_model")
        self._univ_model.setPlaceholderText("e.g. llama3.2 or gpt-4")
        self._extraction_model = doc(QLineEdit(), "settings.extraction_model")
        self._extraction_model.setPlaceholderText("e.g. llama3.1:8b")
        self._time_model = doc(QLineEdit(), "settings.time_model")
        self._time_model.setPlaceholderText("e.g. llama3.2:1b")

        self._default_verbosity_combo = doc(QComboBox(), "settings.default_verbosity")
        for level in ("short", "balanced", "talkative"):
            self._default_verbosity_combo.addItem(tr(level), level)

        self._univ_test_btn = doc(QPushButton(tr("test_connection")), "settings.test_connection")
        self._univ_status = QLabel("")

        self._univ_url_label = QLabel(tr("base_url"))
        self._univ_key_label = QLabel(tr("api_key"))
        self._univ_model_label = QLabel(tr("main_model"))
        self._univ_extraction_label = QLabel(tr("extraction_model"))
        self._univ_time_label = QLabel(tr("time_model"))
        self._default_verbosity_label = QLabel(tr("default_verbosity"))

        univ_form.addRow(self._univ_url_label, self._univ_url)
        univ_form.addRow(self._univ_key_label, self._univ_key)
        univ_form.addRow(self._univ_model_label, self._univ_model)
        univ_form.addRow(self._default_verbosity_label, self._default_verbosity_combo)
        univ_form.addRow(self._univ_extraction_label, self._extraction_model)
        univ_form.addRow(self._univ_time_label, self._time_model)

        test_row = QHBoxLayout()
        test_row.addWidget(self._univ_test_btn)
        test_row.addWidget(self._univ_status)
        test_row.addStretch()
        univ_form.addRow(test_row)

        layout.addLayout(univ_form)
        layout.addStretch()

        self._univ_test_btn.clicked.connect(self._test_universal)

    def load_from_config(self, config: Any) -> None:
        """Populate fields from AppConfig or dict."""
        url = getattr(config, "universal_base_url", None)
        if url is None and isinstance(config, dict):
            url = config.get("universal_base_url", "")
        self._univ_url.setText(str(url or "http://localhost:11434/v1"))

        key = getattr(config, "universal_api_key", None)
        if key is None and isinstance(config, dict):
            key = config.get("universal_api_key", "")
        self._univ_key.setText(str(key or ""))

        model = getattr(config, "universal_model", None)
        if model is None and isinstance(config, dict):
            model = config.get("universal_model", "")
        self._univ_model.setText(str(model or "llama3.2"))

        try:
            from axiom.config import get_default_verbosity
            v = get_default_verbosity(config) if not isinstance(config, dict) else config.get("default_verbosity", "balanced")
        except Exception:
            v = getattr(config, "default_verbosity", "balanced")
        v_idx = self._default_verbosity_combo.findData(v)
        if v_idx >= 0:
            self._default_verbosity_combo.setCurrentIndex(v_idx)

        ext_model = getattr(config, "extraction_model", None)
        if ext_model is None and isinstance(config, dict):
            ext_model = config.get("extraction_model", "")
        self._extraction_model.setText(str(ext_model or "llama3.1:8b"))

        t_model = getattr(config, "time_model", None)
        if t_model is None and isinstance(config, dict):
            t_model = config.get("time_model", "")
        self._time_model.setText(str(t_model or "llama3.2:1b"))

    def collect_config(
        self,
        config: Any = None,
        target_dict: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Read fields into dictionary and optionally update config/target_dict."""
        data = {
            "universal_base_url": self._univ_url.text().strip() or "http://localhost:11434/v1",
            "universal_api_key": self._univ_key.text().strip(),
            "universal_model": self._univ_model.text().strip() or "llama3.2",
            "default_verbosity": self._default_verbosity_combo.currentData() or "balanced",
            "extraction_model": self._extraction_model.text().strip() or "llama3.1:8b",
            "time_model": self._time_model.text().strip() or "llama3.2:1b",
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
        """Update localized text for labels and controls."""
        self._univ_url_label.setText(tr("base_url"))
        self._univ_key_label.setText(tr("api_key"))
        self._univ_model_label.setText(tr("main_model"))
        self._default_verbosity_label.setText(tr("default_verbosity"))
        for i in range(self._default_verbosity_combo.count()):
            level = self._default_verbosity_combo.itemData(i)
            if level:
                self._default_verbosity_combo.setItemText(i, tr(level))
        self._univ_extraction_label.setText(tr("extraction_model"))
        self._univ_time_label.setText(tr("time_model"))
        self._univ_key.setPlaceholderText(tr("optional_key"))
        self._univ_test_btn.setText(tr("test_connection"))

    @Slot()
    def _test_universal(self) -> None:
        self._univ_status.setText(tr("testing"))
        self._univ_test_btn.setEnabled(False)
        from workers.connection_test_worker import ConnectionTestWorker

        data = self.collect_config()
        cfg = AppConfig(
            llm_backend="universal",
            universal_base_url=data["universal_base_url"],
            universal_api_key=data["universal_api_key"],
            universal_model=data["universal_model"],
        )
        try:
            llm = build_llm_from_config(cfg)
        except ValueError as exc:
            self._univ_status.setText(f"{tr('failed')} {exc}")
            self._univ_test_btn.setEnabled(True)
            return

        self._test_worker = ConnectionTestWorker(llm)
        self._test_worker.result_ready.connect(self._on_test_result)
        self._test_worker.start()

    @Slot(bool, str)
    def _on_test_result(self, ok: bool, msg: str) -> None:
        color = "#27ae60" if ok else "#c0392b"
        self._univ_status.setText(f'<span style="color:{color};">{msg}</span>')
        self._univ_test_btn.setEnabled(True)


class CloudSettingsTab(QWidget):
    """Settings tab for commercial cloud LLM providers."""

    tab_id: str = "cloud_llm"
    title_key: str = "tab_cloud"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._test_worker: Any = None
        self._model_worker: Any = None
        self._cloud_values: dict[str, dict[str, str]] = {
            provider: {"key": "", "model": ""} for _, provider in _CLOUD_PROVIDERS
        }
        self._cloud_current_provider: str | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self._cloud_form = QFormLayout()

        self._cloud_provider_combo = doc(QComboBox(), "settings.cloud_provider")
        for label, provider in _CLOUD_PROVIDERS:
            self._cloud_provider_combo.addItem(label, provider)
        self._cloud_provider_label = QLabel(tr("cloud_provider"))

        self._cloud_key = doc(QLineEdit(), "settings.cloud_key")
        self._cloud_key.setEchoMode(QLineEdit.Password)
        self._cloud_model = doc(QLineEdit(), "settings.cloud_model")
        self._browse_models_btn = doc(QPushButton(tr("browse_models")), "settings.browse_models")
        self._cloud_test_btn = doc(QPushButton(tr("test_connection")), "settings.test_connection")
        self._cloud_status = QLabel("")

        self._cloud_key_label = QLabel(tr("api_key"))
        self._cloud_model_label = QLabel(tr("model_name"))

        self._gemini_fallback = doc(QLineEdit(), "settings.gemini_fallback")
        self._gemini_fallback.setPlaceholderText("e.g. gemini-2.0-flash-lite")
        self._gemini_fallback_label = QLabel(tr("gemini_fallback_label"))
        self._llm_rpm_spin = doc(QSpinBox(), "settings.llm_rpm")
        self._llm_rpm_spin.setRange(0, 600)
        self._llm_rpm_spin.setSpecialValueText(tr("rpm_unlimited"))
        self._llm_rpm_label = QLabel(tr("llm_rpm_label"))

        self._cloud_form.addRow(self._cloud_provider_label, self._cloud_provider_combo)
        self._cloud_form.addRow(self._cloud_key_label, self._cloud_key)
        model_row = QHBoxLayout()
        model_row.addWidget(self._cloud_model, stretch=1)
        model_row.addWidget(self._browse_models_btn)
        self._cloud_form.addRow(self._cloud_model_label, model_row)
        self._cloud_form.addRow(self._gemini_fallback_label, self._gemini_fallback)
        self._cloud_form.addRow(self._llm_rpm_label, self._llm_rpm_spin)

        test_row = QHBoxLayout()
        test_row.addWidget(self._cloud_test_btn)
        test_row.addWidget(self._cloud_status)
        test_row.addStretch()
        self._cloud_form.addRow(test_row)

        layout.addLayout(self._cloud_form)
        layout.addStretch()

        self._sync_cloud_fields()

        self._cloud_provider_combo.currentIndexChanged.connect(self._on_cloud_provider_changed)
        self._cloud_test_btn.clicked.connect(self._test_cloud)
        self._browse_models_btn.clicked.connect(self._browse_models)

    def _stash_cloud_fields(self) -> None:
        provider = self._cloud_current_provider
        if provider:
            self._cloud_values[provider] = {
                "key": self._cloud_key.text().strip(),
                "model": self._cloud_model.text().strip(),
            }

    def _sync_cloud_fields(self) -> None:
        provider = self._cloud_provider_combo.currentData()
        self._cloud_current_provider = provider
        values = self._cloud_values.get(provider, {"key": "", "model": ""})
        self._cloud_key.setText(values["key"])
        self._cloud_model.setText(values["model"])
        if provider == "gemini":
            key_placeholder = tr("gemini_key_placeholder")
        elif get_builtin_keys(provider):
            key_placeholder = tr("builtin_keys_placeholder")
        else:
            key_placeholder = tr("api_key").rstrip(" :")
        self._cloud_key.setPlaceholderText(key_placeholder)
        self._cloud_model.setPlaceholderText(_CLOUD_MODEL_PLACEHOLDERS.get(provider, ""))
        is_gemini = provider == "gemini"
        self._cloud_form.setRowVisible(self._gemini_fallback, is_gemini)
        self._cloud_form.setRowVisible(self._llm_rpm_spin, is_gemini)

    @Slot()
    def _on_cloud_provider_changed(self) -> None:
        self._stash_cloud_fields()
        self._cloud_status.setText("")
        self._sync_cloud_fields()

    def load_from_config(self, config: Any) -> None:
        """Populate fields from AppConfig or dict."""
        self._cloud_values = {
            "gemini": {
                "key": getattr(config, "gemini_api_key", ""),
                "model": getattr(config, "gemini_model", "gemini-2.0-flash"),
            },
            "claude": {
                "key": getattr(config, "anthropic_api_key", ""),
                "model": getattr(config, "anthropic_model", "claude-opus-4-8"),
            },
            "venice": {
                "key": getattr(config, "venice_api_key", ""),
                "model": getattr(config, "venice_model", "zai-org-glm-4.7"),
            },
            "fireworks": {
                "key": getattr(config, "fireworks_api_key", ""),
                "model": getattr(config, "fireworks_model", "accounts/fireworks/models/gpt-oss-120b"),
            },
            "openai": {
                "key": getattr(config, "openai_api_key", ""),
                "model": getattr(config, "openai_model", "gpt-4.1-mini"),
            },
            "openrouter": {
                "key": getattr(config, "openrouter_api_key", ""),
                "model": getattr(config, "openrouter_model", "openrouter/auto"),
            },
        }
        backend = getattr(config, "llm_backend", "gemini")
        provider = backend if backend in CLOUD_BACKENDS else "gemini"
        self._cloud_current_provider = None
        idx = self._cloud_provider_combo.findData(provider)
        if idx >= 0:
            self._cloud_provider_combo.setCurrentIndex(idx)
        self._sync_cloud_fields()

        fallback = getattr(config, "gemini_fallback_model", "")
        self._gemini_fallback.setText(str(fallback or ""))

        rpm = getattr(config, "llm_requests_per_minute", 0)
        self._llm_rpm_spin.setValue(int(rpm or 0))

    def collect_config(
        self,
        config: Any = None,
        target_dict: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Read fields into dictionary and optionally update config/target_dict."""
        self._stash_cloud_fields()
        cloud = self._cloud_values

        data = {
            "llm_backend": self._cloud_provider_combo.currentData() or "gemini",
            "gemini_api_key": cloud["gemini"]["key"],
            "gemini_model": cloud["gemini"]["model"] or "gemini-2.0-flash",
            "anthropic_api_key": cloud["claude"]["key"],
            "anthropic_model": cloud["claude"]["model"] or "claude-opus-4-8",
            "venice_api_key": cloud["venice"]["key"],
            "venice_model": cloud["venice"]["model"] or "zai-org-glm-4.7",
            "fireworks_api_key": cloud["fireworks"]["key"],
            "fireworks_model": cloud["fireworks"]["model"] or "accounts/fireworks/models/gpt-oss-120b",
            "openai_api_key": cloud["openai"]["key"],
            "openai_model": cloud["openai"]["model"] or "gpt-4.1-mini",
            "openrouter_api_key": cloud["openrouter"]["key"],
            "openrouter_model": cloud["openrouter"]["model"] or "openrouter/auto",
            "gemini_fallback_model": self._gemini_fallback.text().strip(),
            "llm_requests_per_minute": self._llm_rpm_spin.value(),
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
        """Update localized text for labels and controls."""
        self._cloud_provider_label.setText(tr("cloud_provider"))
        self._cloud_key_label.setText(tr("api_key"))
        self._cloud_model_label.setText(tr("model_name"))
        self._cloud_test_btn.setText(tr("test_connection"))
        self._browse_models_btn.setText(tr("browse_models"))
        self._stash_cloud_fields()
        self._sync_cloud_fields()

    @Slot()
    def _test_cloud(self) -> None:
        self._cloud_status.setText(tr("testing"))
        self._cloud_test_btn.setEnabled(False)
        from workers.connection_test_worker import ConnectionTestWorker

        data = self.collect_config()
        cfg = AppConfig(**{k: v for k, v in data.items() if hasattr(AppConfig, k)})
        cfg.llm_backend = self._cloud_provider_combo.currentData()
        try:
            llm = build_llm_from_config(cfg)
        except ValueError as exc:
            self._cloud_status.setText(f"{tr('failed')} {exc}")
            self._cloud_test_btn.setEnabled(True)
            return

        probe = cfg.llm_backend in OPENAI_COMPAT_PROVIDERS
        self._test_worker = ConnectionTestWorker(llm, probe_model=probe)
        self._test_worker.result_ready.connect(self._on_test_result)
        self._test_worker.start()

    @Slot(bool, str)
    def _on_test_result(self, ok: bool, msg: str) -> None:
        color = "#27ae60" if ok else "#c0392b"
        self._cloud_status.setText(f'<span style="color:{color};">{msg}</span>')
        self._cloud_test_btn.setEnabled(True)

    @Slot()
    def _browse_models(self) -> None:
        from workers.model_list_worker import ModelListWorker

        data = self.collect_config()
        cfg = AppConfig(**{k: v for k, v in data.items() if hasattr(AppConfig, k)})
        cfg.llm_backend = self._cloud_provider_combo.currentData()
        try:
            llm = build_llm_from_config(cfg)
        except ValueError as exc:
            self._cloud_status.setText(f"{tr('failed')} {exc}")
            return
        self._cloud_status.setText(tr("loading_models"))
        self._browse_models_btn.setEnabled(False)
        self._model_worker = ModelListWorker(llm)
        self._model_worker.models_ready.connect(self._on_models_listed)
        self._model_worker.start()

    @Slot(list)
    def _on_models_listed(self, models: list) -> None:
        self._browse_models_btn.setEnabled(True)
        self._cloud_status.setText("")
        if not models:
            return
        from PySide6.QtWidgets import QInputDialog
        current_model = self._cloud_model.text().strip()
        items = [str(m) for m in models]
        initial_idx = items.index(current_model) if current_model in items else 0
        chosen, ok = QInputDialog.getItem(
            self, tr("browse_models"), tr("model_name"), items, initial_idx, False
        )
        if ok and chosen:
            self._cloud_model.setText(chosen)
            self._stash_cloud_fields()
