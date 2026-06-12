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

def test_settings_dialog_doc_tooltips_toggle(qtbot) -> None:
    """TICKET-057 follow-up: the hover-doc toggle loads and saves."""
    dialog = SettingsDialog(AppConfig(doc_tooltips_enabled=False))
    qtbot.addWidget(dialog)
    assert dialog._doc_tooltips_cb.isChecked() is False

    dialog._doc_tooltips_cb.setChecked(True)
    assert dialog.collect_config().doc_tooltips_enabled is True
