"""
tests/test_settings_dialog.py

Unit tests for the settings dialog UI.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt

from axiom.config import AppConfig
from ui.settings_dialog import SettingsDialog


def test_settings_dialog_image_fields(qtbot) -> None:
    cfg = AppConfig(
        image_generation_enabled=True,
        image_backend="comfyui",
        image_api_url="http://local-generator:8188",
        image_width=1024,
        image_height=1024,
        image_steps=30,
        image_cfg_scale=8.5,
        image_comfyui_workflow="my_workflow.json",
        image_gemini_model="gemini-2.5-flash-image",
        image_timeout=240,
    )

    dialog = SettingsDialog(cfg)
    qtbot.addWidget(dialog)

    # Verify fields loaded successfully
    assert dialog._image_enabled_cb.isChecked() is True
    assert dialog._image_backend_combo.currentData() == "comfyui"
    assert dialog._image_url.text() == "http://local-generator:8188"
    assert dialog._image_width_spin.value() == 1024
    assert dialog._image_height_spin.value() == 1024
    assert dialog._image_steps_spin.value() == 30
    assert dialog._image_cfg_spin.value() == 8.5
    assert dialog._image_workflow.text() == "my_workflow.json"
    assert dialog._image_gemini_model.text() == "gemini-2.5-flash-image"
    assert dialog._image_timeout_spin.value() == 240

    # Modify widget values
    dialog._image_enabled_cb.setChecked(False)
    dialog._image_backend_combo.setCurrentIndex(
        dialog._image_backend_combo.findData("stable_diffusion")
    )
    dialog._image_gemini_model.setText("gemini-3-pro-image-preview")
    dialog._image_timeout_spin.setValue(90)
    dialog._image_url.setText("http://another-generator:7860")
    dialog._image_width_spin.setValue(256)
    dialog._image_height_spin.setValue(256)
    dialog._image_steps_spin.setValue(10)
    dialog._image_cfg_spin.setValue(6.0)
    dialog._image_workflow.setText("another.json")

    # Collect updated config and assert values
    updated_cfg = dialog.collect_config()
    assert updated_cfg.image_generation_enabled is False
    assert updated_cfg.image_backend == "stable_diffusion"
    assert updated_cfg.image_api_url == "http://another-generator:7860"
    assert updated_cfg.image_width == 256
    assert updated_cfg.image_height == 256
    assert updated_cfg.image_steps == 10
    assert updated_cfg.image_cfg_scale == 6.0
    assert updated_cfg.image_comfyui_workflow == "another.json"
    assert updated_cfg.image_gemini_model == "gemini-3-pro-image-preview"
    assert updated_cfg.image_timeout == 90


def test_settings_dialog_gemini_image_backend_selectable(qtbot) -> None:
    cfg = AppConfig(image_backend="gemini")

    dialog = SettingsDialog(cfg)
    qtbot.addWidget(dialog)

    assert dialog._image_backend_combo.currentData() == "gemini"
    # Empty model field falls back to the default model on save
    dialog._image_gemini_model.setText("")
    updated_cfg = dialog.collect_config()
    assert updated_cfg.image_backend == "gemini"
    assert updated_cfg.image_gemini_model == "gemini-2.5-flash-image"


def test_settings_dialog_cloud_provider_dropdown(qtbot) -> None:
    """The Cloud tab exposes the 5 text providers in the dropdown."""
    dialog = SettingsDialog(AppConfig())
    qtbot.addWidget(dialog)

    providers = [
        dialog._cloud_provider_combo.itemData(i)
        for i in range(dialog._cloud_provider_combo.count())
    ]
    assert providers == ["gemini", "claude", "venice", "fireworks", "openai", "openrouter"]
    # Default config (universal backend) shows the Gemini provider with its
    # gemini-only rows visible.
    assert dialog._cloud_provider_combo.currentData() == "gemini"
    assert dialog._cloud_form.isRowVisible(dialog._gemini_fallback)


def test_settings_dialog_cloud_provider_loads_and_collects(qtbot) -> None:
    """A venice backend selects the provider, fills its fields, and switching
    providers keeps every key (round-trip through collect_config)."""
    cfg = AppConfig(
        llm_backend="venice",
        venice_api_key="venice-key",
        venice_model="zai-org-glm-4.7",
        gemini_api_key="gemini-key",
        anthropic_api_key="claude-key",
    )
    dialog = SettingsDialog(cfg)
    qtbot.addWidget(dialog)

    # Loaded on the Cloud tab with venice selected and its values displayed
    assert dialog._tabs.currentIndex() == 1
    assert dialog._cloud_provider_combo.currentData() == "venice"
    assert dialog._cloud_key.text() == "venice-key"
    assert dialog._cloud_model.text() == "zai-org-glm-4.7"
    # Gemini-only rows are hidden for the other providers
    assert not dialog._cloud_form.isRowVisible(dialog._gemini_fallback)
    assert not dialog._cloud_form.isRowVisible(dialog._llm_rpm_spin)

    # Switch to claude: its stored key appears, venice's is stashed
    idx = dialog._cloud_provider_combo.findData("claude")
    dialog._cloud_provider_combo.setCurrentIndex(idx)
    assert dialog._cloud_key.text() == "claude-key"
    dialog._cloud_model.setText("claude-opus-4-8")

    updated = dialog.collect_config()
    assert updated.llm_backend == "claude"
    assert updated.anthropic_api_key == "claude-key"
    assert updated.anthropic_model == "claude-opus-4-8"
    # Nothing lost on the other providers
    assert updated.venice_api_key == "venice-key"
    assert updated.venice_model == "zai-org-glm-4.7"
    assert updated.gemini_api_key == "gemini-key"


def test_settings_dialog_memory_tab_roundtrip(qtbot) -> None:
    """The Memory tab loads the Phase 2 fields and collect_config preserves them
    (regression: a fresh AppConfig in collect_config used to reset them)."""
    cfg = AppConfig(
        memory_mode="living",
        memory_fact_interval=7,
        memory_fact_model="gpt-oss-20b",
        memory_reranker_enabled=True,
    )
    dialog = SettingsDialog(cfg)
    qtbot.addWidget(dialog)

    assert dialog._memory_mode_combo.currentData() == "living"
    assert dialog._memory_interval_spin.value() == 7
    assert dialog._memory_model_edit.text() == "gpt-oss-20b"
    assert dialog._memory_reranker_cb.isChecked() is True
    # Living mode → interval/model/extract enabled
    assert dialog._memory_interval_spin.isEnabled()

    # Round-trip: nothing is silently reset on save.
    updated = dialog.collect_config()
    assert updated.memory_mode == "living"
    assert updated.memory_fact_interval == 7
    assert updated.memory_fact_model == "gpt-oss-20b"
    assert updated.memory_reranker_enabled is True


def test_settings_dialog_memory_lite_disables_controls(qtbot) -> None:
    """Lite mode (default) greys out the living-only controls; the extract-now
    button stays disabled without an active session."""
    dialog = SettingsDialog(AppConfig())  # default = lite, db_path None
    qtbot.addWidget(dialog)

    assert dialog._memory_mode_combo.currentData() == "lite"
    assert not dialog._memory_interval_spin.isEnabled()
    assert not dialog._memory_model_edit.isEnabled()
    assert not dialog._memory_extract_btn.isEnabled()

    # Switching to living enables interval/model, but extract still needs a save.
    idx = dialog._memory_mode_combo.findData("living")
    dialog._memory_mode_combo.setCurrentIndex(idx)
    assert dialog._memory_interval_spin.isEnabled()
    assert not dialog._memory_extract_btn.isEnabled()  # db_path is None


def test_settings_dialog_extract_now_emits(qtbot, tmp_path) -> None:
    """With a live session + living mode, the button emits extract_now_requested."""
    from axiom.schema import create_universe_db
    db_path = str(tmp_path / "universe.db")
    create_universe_db(db_path)
    dialog = SettingsDialog(AppConfig(memory_mode="living"), db_path=db_path)
    qtbot.addWidget(dialog)
    assert dialog._memory_extract_btn.isEnabled()

    fired: list[bool] = []
    dialog.extract_now_requested.connect(lambda: fired.append(True))
    dialog._memory_extract_btn.click()
    assert fired == [True]


def test_settings_tab_help_is_tab_aware(qtbot) -> None:
    """The 'Information' help composes the active tab's rich intro + its elements
    + the always-visible General section."""
    from core.localization import set_language
    from ui.help_dialogs import settings_tab_help_html
    from ui.help_system import SETTINGS_TAB_PAGES, SETTINGS_GENERAL_PAGE

    set_language("en")
    # Memory tab (last in SETTINGS_TAB_PAGES) → its intro + a memory element + General.
    mem_idx = len(SETTINGS_TAB_PAGES) - 1
    title, html = settings_tab_help_html(mem_idx)
    assert title == "Settings — Memory"
    assert "Living" in html              # rich tab intro
    assert "cross-encoder" in html       # memory element details block (_d)
    assert "Settings — General" in html  # General section appended

    # Out-of-range index falls back to the General page and does not double it.
    gen_title, gen_html = settings_tab_help_html(999)
    assert gen_title == "Settings — General"
    assert gen_html.count("Settings — General") == 1


class _FakeListingLLM:
    """Backend stub exposing the same surface ConnectionTestWorker probes."""

    def __init__(self, model_name: str, ids: list[str]) -> None:
        self.model_name = model_name
        self._ids = ids

    def is_available(self) -> bool:
        return True

    def list_models(self) -> list[str]:
        return self._ids


def test_connection_test_worker_flags_unknown_model() -> None:
    """Server up + wrong model = the exact trap seen on Fireworks (404 only at
    generation time): the test must fail with an explicit message."""
    from workers.connection_test_worker import ConnectionTestWorker

    worker = ConnectionTestWorker(
        _FakeListingLLM("accounts/fireworks/models/gone", ["accounts/fireworks/models/deepseek-v3p1"])
    )
    msg = worker._check_model()
    assert msg is not None and "gone" in msg


def test_connection_test_worker_accepts_known_and_tagged_models() -> None:
    from workers.connection_test_worker import ConnectionTestWorker

    # Exact id
    ok = ConnectionTestWorker(_FakeListingLLM("m1", ["m1", "m2"]))._check_model()
    assert ok is None
    # Ollama-style "name:tag" listing for a configured bare name
    ok = ConnectionTestWorker(_FakeListingLLM("llama3.2", ["llama3.2:latest"]))._check_model()
    assert ok is None
    # Unlistable endpoint (empty list) stays permissive
    ok = ConnectionTestWorker(_FakeListingLLM("anything", []))._check_model()
    assert ok is None


def test_connection_test_worker_probe_validates_with_real_completion() -> None:
    """Cloud providers: /models is not authoritative (Fireworks lists only the
    account's own models) — the test validates the model with a 1-token call."""
    from workers.connection_test_worker import ConnectionTestWorker

    class _OkLLM:
        def is_available(self) -> bool:
            return True

        def complete(self, messages, **kwargs):
            assert kwargs.get("max_tokens") == 1
            return object()

    assert ConnectionTestWorker(_OkLLM(), probe_model=True)._probe() is None

    class _FailingLLM:
        def is_available(self) -> bool:
            return True

        def complete(self, messages, **kwargs):
            raise RuntimeError("LLM API error 404 from .../chat/completions: model not found")

    msg = ConnectionTestWorker(_FailingLLM(), probe_model=True)._probe()
    assert msg is not None and msg.startswith("✗") and "404" in msg


def test_settings_dialog_cloud_empty_models_fall_back_to_defaults(qtbot) -> None:
    dialog = SettingsDialog(AppConfig())
    qtbot.addWidget(dialog)

    updated = dialog.collect_config()
    assert updated.anthropic_model == "claude-opus-4-8"
    assert updated.venice_model == "zai-org-glm-4.7"
    assert updated.fireworks_model == "accounts/fireworks/models/gpt-oss-120b"
    assert updated.openai_model == "gpt-4.1-mini"
    assert updated.openrouter_model == "openrouter/auto"


def test_settings_dialog_doc_tooltips_toggle(qtbot) -> None:
    """TICKET-057 follow-up: the hover-doc toggle loads and saves."""
    dialog = SettingsDialog(AppConfig(doc_tooltips_enabled=False))
    qtbot.addWidget(dialog)
    assert dialog._doc_tooltips_cb.isChecked() is False

    dialog._doc_tooltips_cb.setChecked(True)
    assert dialog.collect_config().doc_tooltips_enabled is True


def test_settings_dialog_basic_prompt(qtbot) -> None:
    """The basic_prompt UI field loads and collects values correctly."""
    cfg = AppConfig(basic_prompt="Speak only in simple sentences.")
    dialog = SettingsDialog(cfg)
    qtbot.addWidget(dialog)

    assert dialog._basic_prompt.toPlainText() == "Speak only in simple sentences."

    dialog._basic_prompt.setPlainText("Use French words occasionally.")

    updated = dialog.collect_config()
    assert updated.basic_prompt == "Use French words occasionally."

