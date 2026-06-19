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
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
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
        # Memory is per *save*, not per universe: browsing only makes sense for a
        # live play session (the tabletop). The settings dialog knows db_path (a
        # universe) but not the save, so the owner tells us whether a session is
        # active. Off in the Hub / Creator Studio (no save selected).
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

        # ---- Universal API tab ----
        univ_widget = QWidget()
        univ_form = QFormLayout(univ_widget)
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

        self._univ_test_btn = doc(QPushButton(tr("test_connection")), "settings.test_connection")
        
        self._univ_status = QLabel("")
        
        self._univ_url_label = QLabel(tr("base_url"))
        self._univ_key_label = QLabel(tr("api_key"))
        self._univ_model_label = QLabel(tr("main_model"))
        self._univ_extraction_label = QLabel(tr("extraction_model"))
        self._univ_time_label = QLabel(tr("time_model"))

        univ_form.addRow(self._univ_url_label, self._univ_url)
        univ_form.addRow(self._univ_key_label, self._univ_key)
        univ_form.addRow(self._univ_model_label, self._univ_model)
        univ_form.addRow(self._univ_extraction_label, self._extraction_model)
        univ_form.addRow(self._univ_time_label, self._time_model)
        
        test_row = QHBoxLayout()
        test_row.addWidget(self._univ_test_btn)
        test_row.addWidget(self._univ_status)
        test_row.addStretch()
        univ_form.addRow(test_row)
        self._tabs.addTab(univ_widget, tr("tab_llm"))
        doc_tab(self._tabs, 0, "settings.tab_llm")

        # ---- Cloud tab (Gemini / Claude / Venice / Fireworks / OpenAI / OpenRouter) ----
        cloud_widget = QWidget()
        self._cloud_form = QFormLayout(cloud_widget)

        self._cloud_provider_combo = doc(QComboBox(), "settings.cloud_provider")
        for label, provider in _CLOUD_PROVIDERS:
            self._cloud_provider_combo.addItem(label, provider)
        self._cloud_provider_label = QLabel(tr("cloud_provider"))

        self._cloud_key = doc(QLineEdit(), "settings.cloud_key")
        self._cloud_key.setEchoMode(QLineEdit.Password)
        self._cloud_model = doc(QLineEdit(), "settings.cloud_model")
        # TICKET-062 : pick the model from the provider's real catalogue.
        self._browse_models_btn = doc(
            QPushButton(tr("browse_models")), "settings.browse_models"
        )
        self._cloud_test_btn = doc(QPushButton(tr("test_connection")), "settings.test_connection")
        self._cloud_status = QLabel("")

        self._cloud_key_label = QLabel(tr("api_key"))
        self._cloud_model_label = QLabel(tr("model_name"))

        # TICKET-031 : résilience aux quotas (429) — spécifique Gemini.
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
        self._tabs.addTab(cloud_widget, tr("tab_cloud"))
        doc_tab(self._tabs, 1, "settings.tab_cloud")

        # Per-provider key/model values: the two QLineEdits are shared between
        # providers, this dict keeps each provider's text while another one is
        # displayed (switching never loses a key).
        self._cloud_values: dict[str, dict[str, str]] = {
            provider: {"key": "", "model": ""} for _, provider in _CLOUD_PROVIDERS
        }
        self._cloud_current_provider: str | None = None
        self._sync_cloud_fields()

        # ---- Universe Parameters tab ----
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
        doc_tab(self._tabs, 2, "settings.tab_params")
        if not self._db_path:
            self._tabs.setTabEnabled(self._tabs.indexOf(self._univ_params_widget), False)
            self._univ_params_info.setText(f"<span style='color:#c0392b;'>{tr('no_universe_loaded')}</span>")

        # ---- Personas tab ----
        self._persona_editor = PersonaEditorWidget()
        self._tabs.addTab(self._persona_editor, tr("persona_template").replace(":", ""))
        doc_tab(self._tabs, 3, "settings.tab_personas")

        # ---- Image Generation tab ----
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
        doc_tab(self._tabs, 4, "settings.tab_image")

        # ---- Memory tab (Phase 2: lite/living mode + fact extraction) ----
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
        # Mental models build on beliefs → keep their toggle gated on the beliefs one.
        self._memory_beliefs_cb.toggled.connect(self._refresh_memory_controls)
        self._memory_extract_btn.clicked.connect(self._on_extract_now)
        self._memory_browse_btn.clicked.connect(self._on_view_memory)

        layout.addWidget(self._tabs)

        # ---- General section ----
        self._general_group = QGroupBox(tr("tab_general"))
        general_form = QFormLayout(self._general_group)

        self._lang_combo = doc(QComboBox(), "settings.language")
        for code, name in SUPPORTED_LANGUAGES.items():
            self._lang_combo.addItem(name, code)

        # Chronicler interval is expressed in in-game minutes (the world clock),
        # not player turns (Pilier 5 / TICKET-018).
        self._chronicler_spin = doc(QSpinBox(), "settings.chronicler")
        self._chronicler_spin.setRange(5, 100000)
        self._chronicler_spin.setSuffix(" min")

        self._font_size_spin = doc(QSpinBox(), "settings.font_size")
        self._font_size_spin.setRange(8, 36)

        self._rag_chunk_spin = doc(QSpinBox(), "settings.rag_chunks")
        self._rag_chunk_spin.setRange(1, 20)
        self._audio_cb = doc(QCheckBox(tr("enable_audio")), "settings.audio")

        # Toggle for the extra Timekeeper LLM call (Pilier 5 / TICKET-015).
        self._timekeeper_cb = doc(QCheckBox(tr("timekeeper_enabled")), "settings.timekeeper")

        # TICKET-057 : doc tooltips on hover can be turned off.
        self._doc_tooltips_cb = doc(QCheckBox(tr("show_doc_tooltips")), "settings.doc_tooltips")

        # Trim Sentences toggle
        self._trim_sentences_cb = doc(QCheckBox(tr("trim_sentences")), "settings.trim_sentences")

        self._basic_prompt = doc(QTextEdit(), "settings.basic_prompt")
        self._basic_prompt.setAcceptRichText(False)
        self._basic_prompt.setMaximumHeight(80)
        self._basic_prompt.setPlaceholderText(tr("basic_prompt_placeholder"))

        self._lang_label = QLabel(tr("language"))
        self._chronicler_label = QLabel(tr("chronicler_minutes_label"))
        self._font_size_label = QLabel(tr("ui_font_size"))
        self._rag_chunks_label = QLabel(tr("rag_chunks"))
        self._basic_prompt_label = QLabel(tr("basic_prompt_label"))

        general_form.addRow(self._lang_label, self._lang_combo)
        general_form.addRow(self._chronicler_label, self._chronicler_spin)
        general_form.addRow(self._font_size_label, self._font_size_spin)
        general_form.addRow(self._rag_chunks_label, self._rag_chunk_spin)
        general_form.addRow("", self._audio_cb)
        general_form.addRow("", self._timekeeper_cb)
        general_form.addRow("", self._doc_tooltips_cb)
        general_form.addRow("", self._trim_sentences_cb)
        general_form.addRow(self._basic_prompt_label, self._basic_prompt)
        
        layout.addWidget(self._general_group)


        # ---- Buttons ----
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel | QDialogButtonBox.Help
        )
        self._buttons.button(QDialogButtonBox.Save).setText(tr("save"))
        self._buttons.button(QDialogButtonBox.Cancel).setText(tr("cancel"))
        # TICKET-057 : « expliquer cette page » pour le dialogue de réglages.
        help_btn = self._buttons.button(QDialogButtonBox.Help)
        help_btn.setText("?")
        help_btn.setToolTip(tr("explain_page_btn"))
        self._buttons.helpRequested.connect(self._show_help)

        self._buttons.accepted.connect(self._on_save)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

        # Connections
        self._univ_test_btn.clicked.connect(self._test_universal)
        self._cloud_test_btn.clicked.connect(self._test_cloud)
        self._browse_models_btn.clicked.connect(self._browse_models)
        self._cloud_provider_combo.currentIndexChanged.connect(
            self._on_cloud_provider_changed
        )

    # ------------------------------------------------------------------
    # Cloud provider helpers
    # ------------------------------------------------------------------

    def _stash_cloud_fields(self) -> None:
        """Save the displayed key/model into the current provider's slot."""
        provider = self._cloud_current_provider
        if provider:
            self._cloud_values[provider] = {
                "key": self._cloud_key.text().strip(),
                "model": self._cloud_model.text().strip(),
            }

    def _sync_cloud_fields(self) -> None:
        """Load the selected provider's values + adjust per-provider widgets."""
        provider = self._cloud_provider_combo.currentData()
        self._cloud_current_provider = provider
        values = self._cloud_values.get(provider, {"key": "", "model": ""})
        self._cloud_key.setText(values["key"])
        self._cloud_model.setText(values["model"])
        if provider == "gemini":
            key_placeholder = tr("gemini_key_placeholder")
        elif get_builtin_keys(provider):
            # TICKET-062 : shared beta keys cover this provider.
            key_placeholder = tr("builtin_keys_placeholder")
        else:
            key_placeholder = tr("api_key").rstrip(" :")
        self._cloud_key.setPlaceholderText(key_placeholder)
        self._cloud_model.setPlaceholderText(_CLOUD_MODEL_PLACEHOLDERS.get(provider, ""))
        # Fallback model + RPM limit only exist on the Gemini client.
        is_gemini = provider == "gemini"
        self._cloud_form.setRowVisible(self._gemini_fallback, is_gemini)
        self._cloud_form.setRowVisible(self._llm_rpm_spin, is_gemini)

    @Slot()
    def _on_cloud_provider_changed(self) -> None:
        self._stash_cloud_fields()
        self._cloud_status.setText("")
        self._sync_cloud_fields()

    # ------------------------------------------------------------------
    # Memory tab helpers
    # ------------------------------------------------------------------

    def _refresh_memory_controls(self) -> None:
        """Enable interval/model/extract only when living mode is selected.

        'Extract now' also needs an active session (db_path) to act on.
        """
        living = self._memory_mode_combo.currentData() == "living"
        self._memory_interval_spin.setEnabled(living)
        self._memory_model_edit.setEnabled(living)
        self._memory_beliefs_cb.setEnabled(living)
        # Mental models are distilled from beliefs → only selectable with beliefs on.
        self._memory_mental_models_cb.setEnabled(living and self._memory_beliefs_cb.isChecked())
        self._memory_extract_btn.setEnabled(living and bool(self._db_path))
        # Browsing is read-only (works outside living mode — an old save may hold
        # memory to inspect) but needs an *active play session*: memory belongs to
        # a save, not a universe, so it is off in the Hub / Creator Studio.
        self._memory_browse_btn.setEnabled(self._can_browse_memory)

    @Slot()
    def _on_memory_mode_changed(self) -> None:
        self._refresh_memory_controls()

    @Slot()
    def _on_extract_now(self) -> None:
        """Ask the owner to distil the live session's recent turns into facts."""
        self.extract_now_requested.emit()

    @Slot()
    def _on_view_memory(self) -> None:
        """Ask the owner to open the read-only memory browser on the session."""
        self.view_memory_requested.emit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def retranslate_ui(self) -> None:
        """Refresh all UI text for the current language."""
        self.setWindowTitle(tr("settings_title"))
        
        # Tabs
        self._tabs.setTabText(0, tr("tab_llm"))
        self._tabs.setTabText(1, tr("tab_cloud"))
        self._tabs.setTabText(2, tr("univ_params"))
        self._tabs.setTabText(3, tr("persona_template").replace(":", ""))
        
        # Universal Tab
        self._univ_url_label.setText(tr("base_url"))
        self._univ_key_label.setText(tr("api_key"))
        self._univ_model_label.setText(tr("main_model"))
        self._univ_extraction_label.setText(tr("extraction_model"))
        self._univ_time_label.setText(tr("time_model"))
        self._univ_key.setPlaceholderText(tr("optional_key"))
        self._univ_test_btn.setText(tr("test_connection"))
        
        # Cloud Tab
        self._cloud_provider_label.setText(tr("cloud_provider"))
        self._cloud_key_label.setText(tr("api_key"))
        self._cloud_model_label.setText(tr("model_name"))
        self._cloud_test_btn.setText(tr("test_connection"))
        self._browse_models_btn.setText(tr("browse_models"))
        # Refresh the localized key placeholder without losing unsaved edits.
        self._stash_cloud_fields()
        self._sync_cloud_fields()
        
        # Univ Params
        self._llm_temp_label.setText(tr("llm_temp"))
        self._llm_top_p_label.setText(tr("llm_top_p"))
        self._univ_params_info.setText(tr("univ_params_info") if self._db_path else tr("no_universe_loaded"))
        
        # General section
        self._general_group.setTitle(tr("tab_general"))
        self._lang_label.setText(tr("language"))
        self._chronicler_label.setText(tr("chronicler_minutes_label"))
        self._font_size_label.setText(tr("ui_font_size"))
        self._rag_chunks_label.setText(tr("rag_chunks"))
        self._audio_cb.setText(tr("enable_audio"))
        self._timekeeper_cb.setText(tr("timekeeper_enabled"))
        self._doc_tooltips_cb.setText(tr("show_doc_tooltips"))
        self._trim_sentences_cb.setText(tr("trim_sentences"))
        self._basic_prompt_label.setText(tr("basic_prompt_label"))
        self._basic_prompt.setPlaceholderText(tr("basic_prompt_placeholder"))

        
        # Image Generation tab
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
        if hasattr(self._persona_editor, "retranslate_ui"): self._persona_editor.retranslate_ui()

        # Buttons
        self._buttons.button(QDialogButtonBox.Save).setText(tr("save"))
        self._buttons.button(QDialogButtonBox.Cancel).setText(tr("cancel"))

    def load_from_config(self, config: AppConfig) -> None:
        """Populate all form fields from an AppConfig."""
        self._univ_url.setText(config.universal_base_url)
        self._univ_key.setText(config.universal_api_key)
        self._univ_model.setText(config.universal_model)
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
        self._cloud_current_provider = None  # don't stash stale text on the way
        idx = self._cloud_provider_combo.findData(provider)
        if idx >= 0:
            self._cloud_provider_combo.setCurrentIndex(idx)
        self._sync_cloud_fields()
        self._gemini_fallback.setText(config.gemini_fallback_model)
        self._llm_rpm_spin.setValue(config.llm_requests_per_minute)
        self._chronicler_spin.setValue(config.chronicler_minutes_interval)
        self._font_size_spin.setValue(config.ui_font_size)
        self._rag_chunk_spin.setValue(config.rag_chunk_count)
        self._audio_cb.setChecked(config.enable_audio)
        self._timekeeper_cb.setChecked(config.timekeeper_enabled)
        self._doc_tooltips_cb.setChecked(config.doc_tooltips_enabled)
        self._trim_sentences_cb.setChecked(config.trim_sentences)
        self._basic_prompt.setPlainText(config.basic_prompt)

        # Memory settings (Phase 2)
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

        # Image settings
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
        
        idx = self._lang_combo.findData(config.language)
        if idx >= 0:
            self._lang_combo.setCurrentIndex(idx)

        if config.llm_backend in CLOUD_BACKENDS:
            self._tabs.setCurrentIndex(1)
        else:
            self._tabs.setCurrentIndex(0)

    def collect_config(self) -> AppConfig:
        """Read all form fields and return an updated AppConfig."""
        backend = "universal"
        if self._tabs.currentIndex() == 1:
            backend = self._cloud_provider_combo.currentData()

        self._stash_cloud_fields()
        cloud = self._cloud_values

        return AppConfig(
            llm_backend=backend,
            universal_base_url=self._univ_url.text().strip() or "http://localhost:11434/v1",
            universal_api_key=self._univ_key.text().strip(),
            universal_model=self._univ_model.text().strip() or "llama3.2",
            gemini_api_key=cloud["gemini"]["key"],
            gemini_model=cloud["gemini"]["model"] or "gemini-2.0-flash",
            anthropic_api_key=cloud["claude"]["key"],
            anthropic_model=cloud["claude"]["model"] or "claude-opus-4-8",
            venice_api_key=cloud["venice"]["key"],
            venice_model=cloud["venice"]["model"] or "zai-org-glm-4.7",
            fireworks_api_key=cloud["fireworks"]["key"],
            fireworks_model=cloud["fireworks"]["model"]
            or "accounts/fireworks/models/gpt-oss-120b",
            openai_api_key=cloud["openai"]["key"],
            openai_model=cloud["openai"]["model"] or "gpt-4.1-mini",
            openrouter_api_key=cloud["openrouter"]["key"],
            openrouter_model=cloud["openrouter"]["model"] or "openrouter/auto",
            gemini_fallback_model=self._gemini_fallback.text().strip(),
            llm_requests_per_minute=self._llm_rpm_spin.value(),
            extraction_model=self._extraction_model.text().strip() or "llama3.1:8b",
            time_model=self._time_model.text().strip() or "llama3.2:1b",
            timekeeper_enabled=self._timekeeper_cb.isChecked(),
            chronicler_minutes_interval=self._chronicler_spin.value(),
            ui_font_size=self._font_size_spin.value(),
            enable_audio=self._audio_cb.isChecked(),
            doc_tooltips_enabled=self._doc_tooltips_cb.isChecked(),
            trim_sentences=self._trim_sentences_cb.isChecked(),
            rag_chunk_count=self._rag_chunk_spin.value(),
            language=self._lang_combo.currentData(),
            basic_prompt=self._basic_prompt.toPlainText().strip(),
            # Memory settings (Phase 2) — must be read back here or saving the
            # dialog would silently reset them to their defaults.
            memory_mode=self._memory_mode_combo.currentData() or "lite",
            memory_fact_interval=self._memory_interval_spin.value(),
            memory_fact_model=self._memory_model_edit.text().strip(),
            memory_reranker_enabled=self._memory_reranker_cb.isChecked(),
            memory_beliefs_enabled=self._memory_beliefs_cb.isChecked(),
            memory_mental_models_enabled=self._memory_mental_models_cb.isChecked(),
            memory_prompt_cache_enabled=self._memory_prompt_cache_cb.isChecked(),
            # Image generation settings
            image_generation_enabled=self._image_enabled_cb.isChecked(),
            image_backend=self._image_backend_combo.currentData(),
            image_api_url=self._image_url.text().strip(),
            image_width=self._image_width_spin.value(),
            image_height=self._image_height_spin.value(),
            image_steps=self._image_steps_spin.value(),
            image_cfg_scale=self._image_cfg_spin.value(),
            image_timeout=self._image_timeout_spin.value(),
            image_comfyui_workflow=self._image_workflow.text().strip(),
            image_gemini_model=self._image_gemini_model.text().strip()
            or "gemini-2.5-flash-image",
        )

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
        except OSError as exc:
            QMessageBox.critical(self, tr("error"), f"Could not save settings:\n{exc}")
            return

        self._save_personas_async()

    @Slot()
    def _test_universal(self) -> None:
        self._univ_status.setText(tr("testing"))
        self._univ_test_btn.setEnabled(False)
        cfg = self.collect_config()
        cfg.llm_backend = "universal"
        try:
            llm = build_llm_from_config(cfg)
        except ValueError as exc:
            self._univ_status.setText(f"{tr('failed')} {exc}")
            self._univ_test_btn.setEnabled(True)
            return
        self._test_worker = ConnectionTestWorker(llm)
        self._test_worker.result_ready.connect(
            lambda ok, msg: self._on_test_result(ok, msg, self._univ_status, self._univ_test_btn)
        )
        self._test_worker.start()

    @Slot()
    def _test_cloud(self) -> None:
        self._cloud_status.setText(tr("testing"))
        self._cloud_test_btn.setEnabled(False)
        cfg = self.collect_config()
        cfg.llm_backend = self._cloud_provider_combo.currentData()
        try:
            llm = build_llm_from_config(cfg)
        except ValueError as exc:
            self._cloud_status.setText(f"{tr('failed')} {exc}")
            self._cloud_test_btn.setEnabled(True)
            return
        # OpenAI-compat providers: validate the model with a 1-token call —
        # their /models listing is not authoritative. Gemini keeps the plain
        # reachability check (its client retries 429s with long sleeps).
        probe = cfg.llm_backend in OPENAI_COMPAT_PROVIDERS
        self._test_worker = ConnectionTestWorker(llm, probe_model=probe)
        self._test_worker.result_ready.connect(
            lambda ok, msg: self._on_test_result(ok, msg, self._cloud_status, self._cloud_test_btn)
        )
        self._test_worker.start()

    @Slot(bool, str)
    def _on_test_result(
        self,
        ok: bool,
        msg: str,
        status_label: QLabel,
        test_btn: QPushButton,
    ) -> None:
        color = "#27ae60" if ok else "#c0392b"
        status_label.setText(f'<span style="color:{color};">{msg}</span>')
        test_btn.setEnabled(True)

    # ------------------------------------------------------------------
    # Model picker (TICKET-062)
    # ------------------------------------------------------------------

    def _cloud_config(self) -> AppConfig:
        """Current form state with the selected cloud provider as backend."""
        cfg = self.collect_config()
        cfg.llm_backend = self._cloud_provider_combo.currentData()
        return cfg

    @Slot()
    def _browse_models(self) -> None:
        cfg = self._cloud_config()
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
        cfg = self._cloud_config()
        provider = cfg.llm_backend
        builtin = uses_builtin_keys(cfg)

        if provider == "fireworks":
            entries = _fireworks_model_entries(models, builtin)
        else:
            entries = [(m, m) for m in models]

        if not entries:
            self._cloud_status.setText(
                f'<span style="color:#c0392b;">{tr("no_models_found")}</span>'
            )
            return
        self._show_model_picker(entries, builtin_note=builtin)

    def _show_model_picker(self, entries: list, builtin_note: bool) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("model_picker_title"))
        dialog.setMinimumWidth(520)
        layout = QVBoxLayout(dialog)
        if builtin_note:
            note = QLabel(tr("model_picker_builtin_note"))
            note.setWordWrap(True)
            layout.addWidget(note)
        model_list = QListWidget()
        current = self._cloud_model.text().strip()
        for mid, label in entries:
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, mid)
            model_list.addItem(item)
            if mid == current:
                model_list.setCurrentItem(item)
        layout.addWidget(model_list)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        model_list.itemDoubleClicked.connect(lambda _item: dialog.accept())
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.Accepted and model_list.currentItem() is not None:
            self._cloud_model.setText(model_list.currentItem().data(Qt.UserRole))
