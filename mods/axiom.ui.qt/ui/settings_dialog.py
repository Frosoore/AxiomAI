"""
ui/settings_dialog.py

Settings dialog for Axiom AI - LLM backend configuration.

Allows the user to switch between Ollama (local) and Gemini (cloud),
configure model names and URLs, and test the connection.

THREADING RULE: "Test Connection" spawns ConnectionTestWorker.
No network calls on the main thread.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QComboBox,
    QCheckBox,
    QTextEdit,
)

from axiom.config import (
    AppConfig,
    CLOUD_BACKENDS,
    OPENAI_COMPAT_PROVIDERS,
    build_llm_from_config,
    get_builtin_keys,
    memory_mode_is_living,
    save_config,
    uses_builtin_keys,
    GLOBAL_DB_FILE,
    load_config,
)
from axiom.kernel.loader import is_mod_enabled
from core.localization import tr, SUPPORTED_LANGUAGES
from ui.widgets.persona_editor import PersonaEditorWidget
from workers.connection_test_worker import ConnectionTestWorker
from workers.db_worker import DbWorker
from workers.model_list_worker import ModelListWorker

# Cloud tab dropdown: display label + placeholders per provider. The key
# placeholder for "gemini" is localized (tr("gemini_key_placeholder")).
_CLOUD_PROVIDERS: tuple[tuple[str, str], ...] = (
    ("Google Gemini", "gemini"),
    ("Anthropic Claude", "claude"),
    ("Venice AI", "venice"),
    ("Fireworks AI", "fireworks"),
    ("OpenAI", "openai"),
    ("OpenRouter", "openrouter"),
)


def _fireworks_model_entries(models: list[str], builtin: bool) -> list[tuple[str, str]]:
    """(model id, display label) pairs for the Fireworks model picker.

    The /models listing is incomplete (it omits serverless models like
    gpt-oss-20b that do answer), so it is merged with the hand-maintained
    price table; on the shared beta keys, only affordable models remain
    (TICKET-062).
    """
    from core.builtin_keys import FIREWORKS_MODEL_PRICES, is_affordable_on_builtin

    ids = sorted(set(models) | set(FIREWORKS_MODEL_PRICES))
    if builtin:
        ids = [m for m in ids if is_affordable_on_builtin(m)]
    entries = []
    for mid in ids:
        prices = FIREWORKS_MODEL_PRICES.get(mid)
        label = (f"{mid}   (${prices[0]:.2f} in / ${prices[1]:.2f} out per 1M)"
                 if prices else mid)
        entries.append((mid, label))
    return entries


_CLOUD_MODEL_PLACEHOLDERS: dict[str, str] = {
    "gemini": "e.g. gemini-2.0-flash",
    "claude": "e.g. claude-opus-4-8",
    "venice": "e.g. zai-org-glm-4.7",
    "fireworks": "e.g. accounts/fireworks/models/gpt-oss-120b",
    "openai": "e.g. gpt-4.1-mini",
    "openrouter": "e.g. openrouter/auto",
}


class SettingsDialog(QDialog):
    """LLM backend and application settings dialog.

    Loads its fields from an AppConfig on construction, and returns the
    updated AppConfig via collect_config() when the user presses Save.

    Args:
        config:  The current AppConfig to display.
        db_path: Optional path to the active universe database.
        parent:  Optional Qt parent widget.

    Signals:
        extract_now_requested(): The user clicked "Extract memory now" on the
            Memory tab; the owner wires this to the live session's extractor.
        view_memory_requested(): The user clicked "Browse memory"; the owner opens
            the read-only memory browser on the live session (it has the save id /
            current turn the dialog does not).
    """

    extract_now_requested = Signal()
    view_memory_requested = Signal()

    def __init__(self, config: AppConfig, db_path: str | None = None, parent=None,
                 can_browse_memory: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("settings_title"))
        self.setMinimumWidth(460)
        self._config = config
        self._db_path = db_path
        self._can_browse_memory = can_browse_memory
        self._test_worker: ConnectionTestWorker | None = None
        self._db_worker: DbWorker | None = None
        self._universe_meta: dict = {}

        self._setup_ui()
        self.load_from_config(config)

        # Asynchronously load global personas from SQLite
        self._load_personas_async()
        
        # Asynchronously load universe meta if available
        if self._db_path:
            self._load_universe_meta_async()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        from ui.help_system import doc, doc_tab

        layout = QVBoxLayout(self)

        self._tabs = QTabWidget()

        # ---- 1 & 2. Mod-contributed LLM & Cloud tabs (axiom.providers) ----
        if is_mod_enabled("axiom.providers", self._config):
            self._setup_providers_tabs()
        else:
            self._univ_widget = None
            self._cloud_widget = None

        # ---- 3. Universe Parameters tab (Core) ----
        self._univ_params_widget = QWidget()
        univ_params_form = QFormLayout(self._univ_params_widget)
        self._temp_spin = doc(QDoubleSpinBox(), "settings.llm_temp")
        self._temp_spin.setRange(0.0, 1.0)
        self._temp_spin.setSingleStep(0.05)
        self._temp_spin.setValue(0.7)
        self._top_p_spin = doc(QDoubleSpinBox(), "settings.llm_top_p")
        self._top_p_spin.setRange(0.0, 1.0)
        self._top_p_spin.setSingleStep(0.05)
        self._top_p_spin.setValue(1.0)
        
        self._llm_temp_label = QLabel(tr("llm_temp"))
        self._llm_top_p_label = QLabel(tr("llm_top_p"))

        univ_params_form.addRow(self._llm_temp_label, self._temp_spin)
        univ_params_form.addRow(self._llm_top_p_label, self._top_p_spin)
        
        self._univ_params_info = QLabel(tr("univ_params_info"))
        self._univ_params_info.setWordWrap(True)
        univ_params_form.addRow(self._univ_params_info)
        
        self._tabs.addTab(self._univ_params_widget, tr("univ_params"))
        doc_tab(self._tabs, self._tabs.indexOf(self._univ_params_widget), "settings.tab_params")
        if not self._db_path:
            self._tabs.setTabEnabled(self._tabs.indexOf(self._univ_params_widget), False)
            self._univ_params_info.setText(f"<span style='color:#c0392b;'>{tr('no_universe_loaded')}</span>")

        # ---- 4. Personas tab (Core) ----
        self._persona_editor = PersonaEditorWidget()
        self._tabs.addTab(self._persona_editor, tr("persona_template").replace(":", ""))
        doc_tab(self._tabs, self._tabs.indexOf(self._persona_editor), "settings.tab_personas")

        # ---- 5. Image Generation tab (axiom.illustrations) ----
        if is_mod_enabled("axiom.illustrations", self._config):
            self._setup_image_tab()
        else:
            self._image_widget = None

        # ---- 6. Memory tab (axiom.living_memory) ----
        if is_mod_enabled("axiom.living_memory", self._config):
            self._setup_memory_tab()
        else:
            self._memory_widget = None

        # ---- 7. Audio & Sound tab (Core) ----
        self._audio_widget = QWidget()
        audio_form = QFormLayout(self._audio_widget)
        self._audio_cb = doc(QCheckBox(tr("enable_audio")), "settings.audio")
        audio_form.addRow("", self._audio_cb)
        self._tabs.addTab(self._audio_widget, tr("enable_audio"))
        doc_tab(self._tabs, self._tabs.indexOf(self._audio_widget), "settings.audio")

        # ---- 8. Display & UI tab (Core) ----
        self._ui_widget = QWidget()
        ui_layout = QVBoxLayout(self._ui_widget)
        self._general_group = QGroupBox(tr("tab_general"))
        general_form = QFormLayout(self._general_group)

        self._lang_combo = doc(QComboBox(), "settings.language")
        for code, name in SUPPORTED_LANGUAGES.items():
            self._lang_combo.addItem(name, code)

        self._chronicler_spin = doc(QSpinBox(), "settings.chronicler")
        self._chronicler_spin.setRange(5, 100000)
        self._chronicler_spin.setSuffix(" min")

        self._font_size_spin = doc(QSpinBox(), "settings.font_size")
        self._font_size_spin.setRange(8, 36)

        self._rag_chunk_spin = doc(QSpinBox(), "settings.rag_chunks")
        self._rag_chunk_spin.setRange(1, 20)

        self._timekeeper_cb = doc(QCheckBox(tr("timekeeper_enabled")), "settings.timekeeper")
        self._doc_tooltips_cb = doc(QCheckBox(tr("show_doc_tooltips")), "settings.doc_tooltips")
        self._trim_sentences_cb = doc(QCheckBox(tr("trim_sentences")), "settings.trim_sentences")

        self._wallpaper_edit = doc(QLineEdit(), "settings.wallpaper")
        self._wallpaper_edit.setPlaceholderText(tr("wallpaper_placeholder"))
        self._wallpaper_btn = doc(QPushButton(tr("browse")), "settings.wallpaper")
        self._wallpaper_btn.clicked.connect(self._on_browse_wallpaper)

        self._wallpaper_layout = QHBoxLayout()
        self._wallpaper_layout.addWidget(self._wallpaper_edit)
        self._wallpaper_layout.addWidget(self._wallpaper_btn)

        self._basic_prompt = doc(QTextEdit(), "settings.basic_prompt")
        self._basic_prompt.setAcceptRichText(False)
        self._basic_prompt.setMaximumHeight(80)
        self._basic_prompt.setPlaceholderText(tr("basic_prompt_placeholder"))

        self._negative_prompt = doc(QTextEdit(), "settings.negative_prompt")
        self._negative_prompt.setAcceptRichText(False)
        self._negative_prompt.setMaximumHeight(80)
        self._negative_prompt.setPlaceholderText(tr("negative_prompt_placeholder"))

        self._lang_label = QLabel(tr("language"))
        self._chronicler_label = QLabel(tr("chronicler_minutes_label"))
        self._font_size_label = QLabel(tr("ui_font_size"))
        self._rag_chunks_label = QLabel(tr("rag_chunks"))
        self._wallpaper_label = QLabel(tr("custom_wallpaper"))
        self._basic_prompt_label = QLabel(tr("basic_prompt_label"))
        self._negative_prompt_label = QLabel(tr("negative_prompt_label"))

        general_form.addRow(self._lang_label, self._lang_combo)
        general_form.addRow(self._chronicler_label, self._chronicler_spin)
        general_form.addRow(self._font_size_label, self._font_size_spin)
        general_form.addRow(self._rag_chunks_label, self._rag_chunk_spin)
        general_form.addRow("", self._timekeeper_cb)
        general_form.addRow("", self._doc_tooltips_cb)
        general_form.addRow("", self._trim_sentences_cb)
        general_form.addRow(self._wallpaper_label, self._wallpaper_layout)
        general_form.addRow(self._basic_prompt_label, self._basic_prompt)
        general_form.addRow(self._negative_prompt_label, self._negative_prompt)

        ui_layout.addWidget(self._general_group)
        self._tabs.addTab(self._ui_widget, tr("tab_general"))
        doc_tab(self._tabs, self._tabs.indexOf(self._ui_widget), "settings.language")

        # ---- Contributed settings tabs from mods (axiom.ui.qt:settings_tab) ----
        from axiom.kernel.registry import get_active_registry
        reg = get_active_registry()
        if reg:
            for tab_contrib in reg.get_slot_contributions("axiom.ui.qt:settings_tab"):
                if isinstance(tab_contrib, tuple) and len(tab_contrib) == 2:
                    self._tabs.addTab(tab_contrib[1], str(tab_contrib[0]))
                elif isinstance(tab_contrib, dict) and "title" in tab_contrib and "widget" in tab_contrib:
                    self._tabs.addTab(tab_contrib["widget"], str(tab_contrib["title"]))
                elif isinstance(tab_contrib, dict) and "title" in tab_contrib and "factory" in tab_contrib:
                    w = tab_contrib["factory"](self._config)
                    if w:
                        self._tabs.addTab(w, str(tab_contrib["title"]))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._tabs)
        layout.addWidget(scroll)

        # ---- Buttons ----
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel | QDialogButtonBox.Help
        )
        self._buttons.button(QDialogButtonBox.Save).setText(tr("save"))
        self._buttons.button(QDialogButtonBox.Cancel).setText(tr("cancel"))
        help_btn = self._buttons.button(QDialogButtonBox.Help)
        help_btn.setText("?")
        help_btn.setToolTip(tr("explain_page_btn"))
        self._buttons.helpRequested.connect(self._show_help)

        self._buttons.accepted.connect(self._on_save)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    def _setup_providers_tabs(self) -> None:
        """Setup Universal API tab and Cloud tab contributed by axiom.providers."""
        from ui.help_system import doc, doc_tab

        # Universal API tab
        self._univ_widget = QWidget()
        univ_form = QFormLayout(self._univ_widget)
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
        self._tabs.addTab(self._univ_widget, tr("tab_llm"))
        doc_tab(self._tabs, self._tabs.indexOf(self._univ_widget), "settings.tab_llm")

        # Cloud tab
        self._cloud_widget = QWidget()
        self._cloud_form = QFormLayout(self._cloud_widget)
        self._cloud_provider_combo = doc(QComboBox(), "settings.cloud_provider")
        for label, provider in _CLOUD_PROVIDERS:
            self._cloud_provider_combo.addItem(label, provider)
        self._cloud_provider_label = QLabel(tr("cloud_provider"))

        self._cloud_key = doc(QLineEdit(), "settings.cloud_key")
        self._cloud_key.setEchoMode(QLineEdit.Password)
        self._cloud_model = doc(QLineEdit(), "settings.cloud_model")
        self._browse_models_btn = doc(
            QPushButton(tr("browse_models")), "settings.browse_models"
        )
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

        test_row2 = QHBoxLayout()
        test_row2.addWidget(self._cloud_test_btn)
        test_row2.addWidget(self._cloud_status)
        test_row2.addStretch()
        self._cloud_form.addRow(test_row2)
        self._tabs.addTab(self._cloud_widget, tr("tab_cloud"))
        doc_tab(self._tabs, self._tabs.indexOf(self._cloud_widget), "settings.tab_cloud")

        self._cloud_values = {
            provider: {"key": "", "model": ""} for _, provider in _CLOUD_PROVIDERS
        }
        self._cloud_current_provider = None
        self._sync_cloud_fields()

        # Connections
        self._univ_test_btn.clicked.connect(self._test_universal)
        self._cloud_test_btn.clicked.connect(self._test_cloud)
        self._browse_models_btn.clicked.connect(self._browse_models)
        self._cloud_provider_combo.currentIndexChanged.connect(
            self._on_cloud_provider_changed
        )

    def _setup_image_tab(self) -> None:
        """Setup Image Generation tab contributed by axiom.illustrations."""
        from ui.help_system import doc, doc_tab
        self._image_widget = QWidget()
        image_form = QFormLayout(self._image_widget)

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

        self._image_height_spin = doc(QSpinBox(), "settings.image_size")
        self._image_height_spin.setRange(64, 4096)
        self._image_height_spin.setSingleStep(64)

        self._image_steps_spin = doc(QSpinBox(), "settings.image_steps")
        self._image_steps_spin.setRange(1, 150)

        self._image_cfg_spin = doc(QDoubleSpinBox(), "settings.image_cfg")
        self._image_cfg_spin.setRange(1.0, 30.0)
        self._image_cfg_spin.setSingleStep(0.5)

        self._image_timeout_spin = doc(QSpinBox(), "settings.image_timeout")
        self._image_timeout_spin.setRange(10, 900)
        self._image_timeout_spin.setSingleStep(10)
        self._image_timeout_spin.setSuffix(" s")

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

        self._tabs.addTab(self._image_widget, tr("tab_image"))
        doc_tab(self._tabs, self._tabs.indexOf(self._image_widget), "settings.tab_image")

    def _setup_memory_tab(self) -> None:
        """Setup Memory tab contributed by axiom.living_memory."""
        from ui.help_system import doc, doc_tab
        self._memory_widget = QWidget()
        memory_form = QFormLayout(self._memory_widget)

        self._memory_mode_combo = doc(QComboBox(), "settings.memory_mode")
        self._memory_mode_combo.addItem(tr("memory_mode_lite"), "lite")
        self._memory_mode_combo.addItem(tr("memory_mode_living"), "living")

        self._memory_interval_spin = doc(QSpinBox(), "settings.memory_interval")
        self._memory_interval_spin.setRange(0, 100)
        self._memory_interval_spin.setSpecialValueText(tr("memory_interval_off"))

        self._memory_model_edit = doc(QLineEdit(), "settings.memory_model")
        self._memory_model_edit.setPlaceholderText(tr("memory_fact_model_placeholder"))

        self._memory_reranker_cb = doc(QCheckBox(tr("memory_reranker_label")), "settings.memory_reranker")
        self._memory_beliefs_cb = doc(QCheckBox(tr("memory_beliefs_label")), "settings.memory_beliefs")
        self._memory_mental_models_cb = doc(QCheckBox(tr("memory_mental_models_label")), "settings.memory_mental_models")
        self._memory_prompt_cache_cb = doc(QCheckBox(tr("memory_prompt_cache_label")), "settings.memory_prompt_cache")

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

        self._tabs.addTab(self._memory_widget, tr("tab_memory"))
        doc_tab(self._tabs, self._tabs.indexOf(self._memory_widget), "settings.tab_memory")

        self._memory_mode_combo.currentIndexChanged.connect(self._on_memory_mode_changed)
        self._memory_beliefs_cb.toggled.connect(self._refresh_memory_controls)
        self._memory_extract_btn.clicked.connect(self._on_extract_now)
        self._memory_browse_btn.clicked.connect(self._on_view_memory)

    # ------------------------------------------------------------------
    # Cloud provider helpers
    # ------------------------------------------------------------------

    def _stash_cloud_fields(self) -> None:
        """Save the displayed key/model into the current provider's slot."""
        if not hasattr(self, "_cloud_current_provider"):
            return
        provider = self._cloud_current_provider
        if provider and hasattr(self, "_cloud_key") and hasattr(self, "_cloud_model"):
            self._cloud_values[provider] = {
                "key": self._cloud_key.text().strip(),
                "model": self._cloud_model.text().strip(),
            }

    def _sync_cloud_fields(self) -> None:
        """Load the selected provider's values + adjust per-provider widgets."""
        if not hasattr(self, "_cloud_provider_combo"):
            return
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
        if hasattr(self, "_cloud_status"):
            self._cloud_status.setText("")
        self._sync_cloud_fields()

    # ------------------------------------------------------------------
    # Test connection
    # ------------------------------------------------------------------

    def _test_backend(self, cfg: AppConfig, status_label: QLabel, test_btn: QPushButton) -> None:
        if self._test_worker and self._test_worker.isRunning():
            return

        status_label.setText(f"<span style='color:gray;'>{tr('testing')}</span>")
        test_btn.setEnabled(False)

        backend = build_llm_from_config(cfg)
        is_cloud = cfg.llm_backend in CLOUD_BACKENDS
        self._test_worker = ConnectionTestWorker(
            backend, parent=self, probe_model=is_cloud
        )
        self._test_worker.test_finished.connect(
            lambda ok, err, lbl=status_label, btn=test_btn: self._on_test_finished(ok, err, lbl, btn)
        )
        self._test_worker.start()

    @Slot()
    def _test_universal(self) -> None:
        cfg = AppConfig(
            llm_backend="universal",
            universal_base_url=self._univ_url.text().strip(),
            universal_api_key=self._univ_key.text().strip(),
            universal_model=self._univ_model.text().strip() or "llama3.2",
        )
        self._test_backend(cfg, self._univ_status, self._univ_test_btn)

    @Slot()
    def _test_cloud(self) -> None:
        self._stash_cloud_fields()
        provider = self._cloud_provider_combo.currentData()
        values = self._cloud_values.get(provider, {"key": "", "model": ""})
        key = values["key"]
        model = values["model"]
        if not key and uses_builtin_keys(provider):
            key = get_builtin_keys(provider)

        kwargs = {
            "llm_backend": provider,
            f"{provider}_api_key": key,
            f"{provider}_model": model,
        }
        if provider == "gemini":
            kwargs["gemini_fallback_model"] = self._gemini_fallback.text().strip()
            kwargs["llm_requests_per_minute"] = self._llm_rpm_spin.value()
        cfg = AppConfig(**kwargs)
        self._test_backend(cfg, self._cloud_status, self._cloud_test_btn)

    @Slot()
    def _browse_models(self) -> None:
        self._stash_cloud_fields()
        provider = self._cloud_provider_combo.currentData()
        values = self._cloud_values.get(provider, {"key": "", "model": ""})
        key = values["key"]
        builtin = False
        if not key and uses_builtin_keys(provider):
            key = get_builtin_keys(provider)
            builtin = True

        cfg = AppConfig(
            llm_backend=provider,
            **{f"{provider}_api_key": key},
        )
        backend = build_llm_from_config(cfg)
        self._cloud_status.setText(f"<span style='color:gray;'>{tr('loading_models')}</span>")
        self._browse_models_btn.setEnabled(False)

        worker = ModelListWorker(backend, parent=self)
        worker.finished.connect(
            lambda models, err, b=builtin: self._on_models_loaded(models, err, b)
        )
        worker.start()

    def _on_models_loaded(self, models: list[str], err: str | None, builtin: bool) -> None:
        self._browse_models_btn.setEnabled(True)
        self._cloud_status.setText("")
        if err:
            QMessageBox.warning(self, tr("model_list_error"), err)
            return

        provider = self._cloud_provider_combo.currentData()
        entries: list[tuple[str, str]]
        if provider == "fireworks":
            entries = _fireworks_model_entries(models, builtin)
        else:
            entries = [(m, m) for m in sorted(models)]

        if not entries:
            QMessageBox.information(self, tr("browse_models"), tr("no_models_found"))
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(tr("select_model"))
        dlg.resize(480, 420)
        d_layout = QVBoxLayout(dlg)
        search = QLineEdit()
        search.setPlaceholderText(tr("filter_models_placeholder"))
        d_layout.addWidget(search)
        lw = QListWidget()
        current = self._cloud_model.text().strip()
        for mid, label in entries:
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, mid)
            lw.addItem(item)
            if mid == current:
                lw.setCurrentItem(item)
        d_layout.addWidget(lw)

        def _filter(text: str) -> None:
            t = text.lower()
            for i in range(lw.count()):
                it = lw.item(i)
                it.setHidden(t not in it.text().lower())

        search.textChanged.connect(_filter)

        bbox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bbox.accepted.connect(dlg.accept)
        bbox.rejected.connect(dlg.reject)
        d_layout.addWidget(bbox)
        lw.itemDoubleClicked.connect(lambda _: dlg.accept())

        if dlg.exec() == QDialog.Accepted and lw.currentItem():
            chosen = lw.currentItem().data(Qt.UserRole)
            self._cloud_model.setText(chosen)
            self._stash_cloud_fields()

    def _on_test_finished(
        self, ok: bool, error: str | None, status_label: QLabel, test_btn: QPushButton
    ) -> None:
        test_btn.setEnabled(True)
        if ok:
            status_label.setText(f"<span style='color:green;'>{tr('connection_ok')}</span>")
        else:
            err_msg = error or tr("unknown_error")
            status_label.setText(
                f"<span style='color:red;'>{tr('connection_failed')}: {err_msg}</span>"
            )

    # ------------------------------------------------------------------
    # Memory controls
    # ------------------------------------------------------------------

    @Slot()
    def _on_memory_mode_changed(self) -> None:
        self._refresh_memory_controls()

    def _refresh_memory_controls(self) -> None:
        if not hasattr(self, "_memory_mode_combo"):
            return
        is_living = self._memory_mode_combo.currentData() == "living"
        self._memory_interval_spin.setEnabled(is_living)
        self._memory_model_edit.setEnabled(is_living)
        self._memory_reranker_cb.setEnabled(is_living)
        self._memory_beliefs_cb.setEnabled(is_living)
        self._memory_mental_models_cb.setEnabled(is_living and self._memory_beliefs_cb.isChecked())
        self._memory_prompt_cache_cb.setEnabled(is_living)
        self._memory_extract_btn.setEnabled(is_living and self._db_path is not None)
        self._memory_browse_btn.setEnabled(self._can_browse_memory)

    @Slot()
    def _on_extract_now(self) -> None:
        self.extract_now_requested.emit()

    @Slot()
    def _on_view_memory(self) -> None:
        self.view_memory_requested.emit()

    @Slot()
    def _on_browse_wallpaper(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            tr("select_wallpaper_title"),
            self._wallpaper_edit.text().strip(),
            "Images (*.png *.jpg *.jpeg *.bmp)"
        )
        if file_path:
            self._wallpaper_edit.setText(file_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_mod_tabs(self, config: AppConfig | None = None) -> None:
        """Dynamically add or remove mod-dependent tabs based on active mods."""
        if config is not None:
            self._config = config

        # Providers tabs
        if is_mod_enabled("axiom.providers", self._config):
            if not hasattr(self, "_univ_widget") or self._univ_widget is None:
                self._setup_providers_tabs()
        else:
            if hasattr(self, "_univ_widget") and self._univ_widget is not None:
                idx = self._tabs.indexOf(self._univ_widget)
                if idx != -1:
                    self._tabs.removeTab(idx)
                self._univ_widget = None
            if hasattr(self, "_cloud_widget") and self._cloud_widget is not None:
                idx = self._tabs.indexOf(self._cloud_widget)
                if idx != -1:
                    self._tabs.removeTab(idx)
                self._cloud_widget = None

        # Illustrations tab
        img_idx = self._tabs.indexOf(self._image_widget) if hasattr(self, "_image_widget") and self._image_widget else -1
        if is_mod_enabled("axiom.illustrations", self._config):
            if img_idx == -1:
                self._setup_image_tab()
        else:
            if img_idx != -1:
                self._tabs.removeTab(img_idx)
                self._image_widget = None

        # Memory tab
        mem_idx = self._tabs.indexOf(self._memory_widget) if hasattr(self, "_memory_widget") and self._memory_widget else -1
        if is_mod_enabled("axiom.living_memory", self._config):
            if mem_idx == -1:
                self._setup_memory_tab()
        else:
            if mem_idx != -1:
                self._tabs.removeTab(mem_idx)
                self._memory_widget = None

    def retranslate_ui(self) -> None:
        """Refresh all UI text for the current language."""
        self.setWindowTitle(tr("settings_title"))
        
        # Providers tabs
        if hasattr(self, "_univ_widget") and self._univ_widget is not None:
            idx = self._tabs.indexOf(self._univ_widget)
            if idx >= 0:
                self._tabs.setTabText(idx, tr("tab_llm"))
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

        if hasattr(self, "_cloud_widget") and self._cloud_widget is not None:
            idx = self._tabs.indexOf(self._cloud_widget)
            if idx >= 0:
                self._tabs.setTabText(idx, tr("tab_cloud"))
            self._cloud_provider_label.setText(tr("cloud_provider"))
            self._cloud_key_label.setText(tr("api_key"))
            self._cloud_model_label.setText(tr("model_name"))
            self._cloud_test_btn.setText(tr("test_connection"))
            self._browse_models_btn.setText(tr("browse_models"))
            self._stash_cloud_fields()
            self._sync_cloud_fields()

        # Core: Universe Params
        idx = self._tabs.indexOf(self._univ_params_widget)
        if idx >= 0:
            self._tabs.setTabText(idx, tr("univ_params"))
        self._llm_temp_label.setText(tr("llm_temp"))
        self._llm_top_p_label.setText(tr("llm_top_p"))
        self._univ_params_info.setText(tr("univ_params_info") if self._db_path else tr("no_universe_loaded"))

        # Core: Personas
        idx = self._tabs.indexOf(self._persona_editor)
        if idx >= 0:
            self._tabs.setTabText(idx, tr("persona_template").replace(":", ""))

        # Core: Audio & Sound
        if hasattr(self, "_audio_widget"):
            idx = self._tabs.indexOf(self._audio_widget)
            if idx >= 0:
                self._tabs.setTabText(idx, tr("enable_audio"))
            self._audio_cb.setText(tr("enable_audio"))

        # Core: Display & UI
        if hasattr(self, "_ui_widget"):
            idx = self._tabs.indexOf(self._ui_widget)
            if idx >= 0:
                self._tabs.setTabText(idx, tr("tab_general"))
            self._general_group.setTitle(tr("tab_general"))
            self._lang_label.setText(tr("language"))
            self._chronicler_label.setText(tr("chronicler_minutes_label"))
            self._font_size_label.setText(tr("ui_font_size"))
            self._rag_chunks_label.setText(tr("rag_chunks"))
            self._timekeeper_cb.setText(tr("timekeeper_enabled"))
            self._doc_tooltips_cb.setText(tr("show_doc_tooltips"))
            self._trim_sentences_cb.setText(tr("trim_sentences"))
            self._wallpaper_label.setText(tr("custom_wallpaper"))
            self._wallpaper_edit.setPlaceholderText(tr("wallpaper_placeholder"))
            self._wallpaper_btn.setText(tr("browse"))
            self._basic_prompt_label.setText(tr("basic_prompt_label"))
            self._basic_prompt.setPlaceholderText(tr("basic_prompt_placeholder"))
            self._negative_prompt_label.setText(tr("negative_prompt_label"))
            self._negative_prompt.setPlaceholderText(tr("negative_prompt_placeholder"))

        # Image Generation tab
        if hasattr(self, "_image_widget") and self._image_widget is not None:
            img_tab_idx = self._tabs.indexOf(self._image_widget)
            if img_tab_idx >= 0:
                self._tabs.setTabText(img_tab_idx, tr("tab_image"))
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

        # Memory tab
        if hasattr(self, "_memory_widget") and self._memory_widget is not None:
            mem_tab_idx = self._tabs.indexOf(self._memory_widget)
            if mem_tab_idx >= 0:
                self._tabs.setTabText(mem_tab_idx, tr("tab_memory"))
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

        # Sub-widgets
        if hasattr(self._persona_editor, "retranslate_ui"):
            self._persona_editor.retranslate_ui()

        # Buttons
        self._buttons.button(QDialogButtonBox.Save).setText(tr("save"))
        self._buttons.button(QDialogButtonBox.Cancel).setText(tr("cancel"))

    def load_from_config(self, config: AppConfig) -> None:
        """Populate all form fields from an AppConfig."""
        self._config = config

        # Providers fields
        if is_mod_enabled("axiom.providers", config) and hasattr(self, "_univ_url") and hasattr(self, "_cloud_provider_combo"):
            self._univ_url.setText(config.universal_base_url)
            self._univ_key.setText(config.universal_api_key)
            self._univ_model.setText(config.universal_model)
            from axiom.config import get_default_verbosity
            v_idx = self._default_verbosity_combo.findData(get_default_verbosity(config))
            if v_idx >= 0:
                self._default_verbosity_combo.setCurrentIndex(v_idx)
            self._extraction_model.setText(config.extraction_model)
            self._time_model.setText(config.time_model)
            self._cloud_values = {
                "gemini": {"key": config.gemini_api_key, "model": config.gemini_model},
                "claude": {"key": config.anthropic_api_key, "model": config.anthropic_model},
                "venice": {"key": config.venice_api_key, "model": config.venice_model},
                "fireworks": {"key": config.fireworks_api_key, "model": config.fireworks_model},
                "openai": {"key": config.openai_api_key, "model": config.openai_model},
                "openrouter": {"key": config.openrouter_api_key, "model": config.openrouter_model},
            }
            provider = config.llm_backend if config.llm_backend in CLOUD_BACKENDS else "gemini"
            self._cloud_current_provider = None
            idx = self._cloud_provider_combo.findData(provider)
            if idx >= 0:
                self._cloud_provider_combo.setCurrentIndex(idx)
            self._sync_cloud_fields()
            self._gemini_fallback.setText(config.gemini_fallback_model)
            self._llm_rpm_spin.setValue(config.llm_requests_per_minute)

            if config.llm_backend in CLOUD_BACKENDS:
                cloud_idx = self._tabs.indexOf(self._cloud_widget)
                if cloud_idx >= 0:
                    self._tabs.setCurrentIndex(cloud_idx)
            else:
                univ_idx = self._tabs.indexOf(self._univ_widget)
                if univ_idx >= 0:
                    self._tabs.setCurrentIndex(univ_idx)

        # Core fields
        self._chronicler_spin.setValue(config.chronicler_minutes_interval)
        self._font_size_spin.setValue(config.ui_font_size)
        self._rag_chunk_spin.setValue(config.rag_chunk_count)
        self._audio_cb.setChecked(config.enable_audio)
        self._timekeeper_cb.setChecked(config.timekeeper_enabled)
        self._doc_tooltips_cb.setChecked(config.doc_tooltips_enabled)
        self._trim_sentences_cb.setChecked(config.trim_sentences)
        self._wallpaper_edit.setText(config.custom_wallpaper)
        self._basic_prompt.setPlainText(config.basic_prompt)
        self._negative_prompt.setPlainText(getattr(config, "negative_prompt", ""))

        idx = self._lang_combo.findData(config.language)
        if idx >= 0:
            self._lang_combo.setCurrentIndex(idx)

        # Image settings
        if is_mod_enabled("axiom.illustrations", config) and hasattr(self, "_image_widget") and self._image_widget is not None and hasattr(self, "_image_enabled_cb"):
            self._image_enabled_cb.setChecked(config.image_generation_enabled)
            idx = self._image_backend_combo.findData(config.image_backend)
            if idx >= 0:
                self._image_backend_combo.setCurrentIndex(idx)
            self._image_url.setText(config.image_api_url)
            self._image_gemini_model.setText(config.image_gemini_model)
            self._image_width_spin.setValue(config.image_width)
            self._image_height_spin.setValue(config.image_height)
            self._image_steps_spin.setValue(config.image_steps)
            self._image_cfg_spin.setValue(config.image_cfg_scale)
            self._image_timeout_spin.setValue(config.image_timeout)
            self._image_workflow.setText(config.image_comfyui_workflow)

        # Memory settings
        if is_mod_enabled("axiom.living_memory", config) and hasattr(self, "_memory_widget") and self._memory_widget is not None and hasattr(self, "_memory_mode_combo"):
            mem_idx = self._memory_mode_combo.findData(
                "living" if memory_mode_is_living(config) else "lite"
            )
            if mem_idx >= 0:
                self._memory_mode_combo.setCurrentIndex(mem_idx)
            self._memory_interval_spin.setValue(config.memory_fact_interval)
            self._memory_model_edit.setText(config.memory_fact_model)
            self._memory_reranker_cb.setChecked(config.memory_reranker_enabled)
            self._memory_beliefs_cb.setChecked(config.memory_beliefs_enabled)
            self._memory_mental_models_cb.setChecked(config.memory_mental_models_enabled)
            self._memory_prompt_cache_cb.setChecked(config.memory_prompt_cache_enabled)
            self._refresh_memory_controls()

    def collect_config(self) -> AppConfig:
        """Read all form fields and return an updated AppConfig.
        Preserves settings from disabled/unmounted tabs from self._config.
        """
        # Core fields
        data = {
            "enable_audio": self._audio_cb.isChecked() if hasattr(self, "_audio_cb") else self._config.enable_audio,
            "language": self._lang_combo.currentData() if hasattr(self, "_lang_combo") and self._lang_combo.currentData() else self._config.language,
            "chronicler_minutes_interval": self._chronicler_spin.value() if hasattr(self, "_chronicler_spin") else self._config.chronicler_minutes_interval,
            "ui_font_size": self._font_size_spin.value() if hasattr(self, "_font_size_spin") else self._config.ui_font_size,
            "rag_chunk_count": self._rag_chunk_spin.value() if hasattr(self, "_rag_chunk_spin") else self._config.rag_chunk_count,
            "timekeeper_enabled": self._timekeeper_cb.isChecked() if hasattr(self, "_timekeeper_cb") else self._config.timekeeper_enabled,
            "doc_tooltips_enabled": self._doc_tooltips_cb.isChecked() if hasattr(self, "_doc_tooltips_cb") else self._config.doc_tooltips_enabled,
            "trim_sentences": self._trim_sentences_cb.isChecked() if hasattr(self, "_trim_sentences_cb") else self._config.trim_sentences,
            "custom_wallpaper": self._wallpaper_edit.text().strip() if hasattr(self, "_wallpaper_edit") else self._config.custom_wallpaper,
            "basic_prompt": self._basic_prompt.toPlainText().strip() if hasattr(self, "_basic_prompt") else self._config.basic_prompt,
            "negative_prompt": self._negative_prompt.toPlainText().strip() if hasattr(self, "_negative_prompt") else getattr(self._config, "negative_prompt", ""),
        }

        # Providers settings (axiom.providers)
        if (
            is_mod_enabled("axiom.providers", self._config)
            and hasattr(self, "_cloud_provider_combo")
            and hasattr(self, "_univ_url")
        ):
            backend = "universal"
            if hasattr(self, "_cloud_widget") and self._cloud_widget is not None and self._tabs.currentWidget() == self._cloud_widget:
                backend = self._cloud_provider_combo.currentData()
            elif hasattr(self, "_cloud_widget") and self._tabs.indexOf(self._cloud_widget) != -1 and self._tabs.currentIndex() == self._tabs.indexOf(self._cloud_widget):
                backend = self._cloud_provider_combo.currentData()

            self._stash_cloud_fields()
            cloud = self._cloud_values

            data.update({
                "llm_backend": backend,
                "universal_base_url": self._univ_url.text().strip() or "http://localhost:11434/v1",
                "universal_api_key": self._univ_key.text().strip(),
                "universal_model": self._univ_model.text().strip() or "llama3.2",
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
                "extraction_model": self._extraction_model.text().strip() or "llama3.1:8b",
                "time_model": self._time_model.text().strip() or "llama3.2:1b",
                "default_verbosity": self._default_verbosity_combo.currentData() or "balanced",
            })
        else:
            data.update({
                "llm_backend": self._config.llm_backend,
                "universal_base_url": self._config.universal_base_url,
                "universal_api_key": self._config.universal_api_key,
                "universal_model": self._config.universal_model,
                "gemini_api_key": self._config.gemini_api_key,
                "gemini_model": self._config.gemini_model,
                "anthropic_api_key": self._config.anthropic_api_key,
                "anthropic_model": self._config.anthropic_model,
                "venice_api_key": self._config.venice_api_key,
                "venice_model": self._config.venice_model,
                "fireworks_api_key": self._config.fireworks_api_key,
                "fireworks_model": self._config.fireworks_model,
                "openai_api_key": self._config.openai_api_key,
                "openai_model": self._config.openai_model,
                "openrouter_api_key": self._config.openrouter_api_key,
                "openrouter_model": self._config.openrouter_model,
                "gemini_fallback_model": self._config.gemini_fallback_model,
                "llm_requests_per_minute": self._config.llm_requests_per_minute,
                "extraction_model": self._config.extraction_model,
                "time_model": self._config.time_model,
                "default_verbosity": self._config.default_verbosity,
            })

        # Image settings (axiom.illustrations)
        if (
            is_mod_enabled("axiom.illustrations", self._config)
            and hasattr(self, "_image_widget")
            and self._image_widget is not None
            and hasattr(self, "_image_enabled_cb")
        ):
            data.update({
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
            })
        else:
            data.update({
                "image_generation_enabled": self._config.image_generation_enabled,
                "image_backend": self._config.image_backend,
                "image_api_url": self._config.image_api_url,
                "image_width": self._config.image_width,
                "image_height": self._config.image_height,
                "image_steps": self._config.image_steps,
                "image_cfg_scale": self._config.image_cfg_scale,
                "image_timeout": self._config.image_timeout,
                "image_comfyui_workflow": self._config.image_comfyui_workflow,
                "image_gemini_model": self._config.image_gemini_model,
            })

        # Memory settings (axiom.living_memory)
        if (
            is_mod_enabled("axiom.living_memory", self._config)
            and hasattr(self, "_memory_widget")
            and self._memory_widget is not None
            and hasattr(self, "_memory_mode_combo")
        ):
            data.update({
                "memory_mode": self._memory_mode_combo.currentData() or "lite",
                "memory_fact_interval": self._memory_interval_spin.value(),
                "memory_fact_model": self._memory_model_edit.text().strip(),
                "memory_reranker_enabled": self._memory_reranker_cb.isChecked(),
                "memory_beliefs_enabled": self._memory_beliefs_cb.isChecked(),
                "memory_mental_models_enabled": self._memory_mental_models_cb.isChecked(),
                "memory_prompt_cache_enabled": self._memory_prompt_cache_cb.isChecked(),
            })
        else:
            data.update({
                "memory_mode": self._config.memory_mode,
                "memory_fact_interval": self._config.memory_fact_interval,
                "memory_fact_model": self._config.memory_fact_model,
                "memory_reranker_enabled": self._config.memory_reranker_enabled,
                "memory_beliefs_enabled": self._config.memory_beliefs_enabled,
                "memory_mental_models_enabled": self._config.memory_mental_models_enabled,
                "memory_prompt_cache_enabled": self._config.memory_prompt_cache_enabled,
            })

        cfg = AppConfig(**data)
        if hasattr(self._config, "mod_settings"):
            cfg.mod_settings = dict(self._config.mod_settings)
        return cfg

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_universe_meta_async(self) -> None:
        self._univ_db_worker = DbWorker(self._db_path)
        self._univ_db_worker.universe_meta_loaded.connect(self._on_meta_loaded)
        self._univ_db_worker.load_universe_meta()

    @Slot(dict)
    def _on_meta_loaded(self, meta: dict) -> None:
        self._universe_meta = meta
        try:
            temp = float(meta.get("llm_temperature", "0.7"))
        except ValueError:
            temp = 0.7
        self._temp_spin.setValue(max(0.0, min(1.0, temp)))
        
        try:
            top_p = float(meta.get("llm_top_p", "1.0"))
        except ValueError:
            top_p = 1.0
        self._top_p_spin.setValue(max(0.0, min(1.0, top_p)))

    def _load_personas_async(self) -> None:
        self._db_worker = DbWorker(str(GLOBAL_DB_FILE))
        self._db_worker.personas_loaded.connect(self._persona_editor.populate)
        self._db_worker.load_global_personas()

    def _save_personas_async(self) -> None:
        personas = self._persona_editor.collect_data()
        self._save_worker = DbWorker(str(GLOBAL_DB_FILE))
        self._save_worker.save_global_personas(personas)
        
        if self._db_path:
            self._save_worker.save_complete.connect(self._save_universe_meta_async)
        else:
            self._save_worker.save_complete.connect(self.accept)
            
        self._save_worker.error_occurred.connect(
            lambda msg: QMessageBox.critical(self, tr("error"), msg)
        )

    def _save_universe_meta_async(self) -> None:
        meta = {
            "llm_temperature": str(self._temp_spin.value()),
            "llm_top_p": str(self._top_p_spin.value()),
        }
        self._univ_save_worker = DbWorker(self._db_path)
        self._univ_save_worker.save_universe_meta(meta)
        self._univ_save_worker.save_complete.connect(self.accept)
        self._univ_save_worker.error_occurred.connect(
            lambda msg: QMessageBox.critical(self, tr("error"), msg)
        )

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @Slot()
    def _show_help(self) -> None:
        """TICKET-057 : open the 'explain this page' dialog for the active tab.

        Tab-aware (like the Creator Studio): the explanation matches the tab you
        are looking at, then appends the always-visible General section.
        """
        from ui.help_dialogs import ExplainPageDialog, settings_tab_help_html
        title, html = settings_tab_help_html(self._tabs.currentIndex())
        ExplainPageDialog("settings", self, html=html, title=title).exec()

    @Slot()
    def _on_save(self) -> None:
        config = self.collect_config()
        try:
            save_config(config)
            self._config = config
        except Exception as err:
            QMessageBox.critical(self, tr("error"), f"{tr('error')}: {err}")
            return

        self._save_personas_async()
