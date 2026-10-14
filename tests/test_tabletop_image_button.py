"""tests/test_tabletop_image_button.py

Tests for TabletopView illustration generation button and ImageWorker:
- Verify _active_save_id property alias works.
- Verify _on_generate_image_clicked does not crash when _save_id is empty.
- Verify _on_generate_image_clicked does not crash when no narrative is present.
- Verify full flow with narrative: placeholder shown, ImageWorker executed, image appended.
- Verify error handling cleans up placeholder and re-enables button.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from axiom.config import AppConfig
from mods.axiom.ui.qt.ui.tabletop_view import TabletopView
from workers.image_worker import ImageWorker


def test_tabletop_active_save_id_property(qtbot) -> None:
    """Verify that _active_save_id property returns _save_id correctly."""
    tabletop = TabletopView()
    qtbot.addWidget(tabletop)

    assert tabletop._active_save_id == ""
    tabletop._save_id = "save_test_123"
    assert tabletop._active_save_id == "save_test_123"


def test_on_generate_image_clicked_no_save_no_crash(qtbot, monkeypatch) -> None:
    """Clicking illustration button when no save is loaded does nothing and does not crash."""
    cfg = AppConfig()
    cfg.image_generation_enabled = True
    monkeypatch.setattr("axiom.config.load_config", lambda: cfg)

    tabletop = TabletopView()
    qtbot.addWidget(tabletop)

    # _save_id is empty
    assert tabletop._save_id == ""
    # Should not raise any exception
    tabletop._on_generate_image_clicked()
    assert getattr(tabletop, "_image_worker", None) is None


def test_on_generate_image_clicked_no_narrative_status(qtbot, monkeypatch) -> None:
    """Clicking illustration button with an active save but no narrative warns in status."""
    cfg = AppConfig()
    monkeypatch.setattr("axiom.config.load_config", lambda: cfg)

    mock_registry = MagicMock()
    mock_registry.get_service.return_value = MagicMock()
    monkeypatch.setattr("axiom.kernel.registry.get_active_registry", lambda: mock_registry)

    mock_main = MagicMock()
    tabletop = TabletopView(main_window=mock_main)
    qtbot.addWidget(tabletop)
    tabletop._save_id = "save_test_123"
    tabletop._history = []

    tabletop._on_generate_image_clicked()
    assert getattr(tabletop, "_image_worker", None) is None
    mock_main.on_status_update.assert_called()


def test_on_generate_image_clicked_full_flow(qtbot, tmp_path, monkeypatch) -> None:
    """Full flow: active save and narrative triggers ImageWorker, adds image and clears placeholder."""
    cfg = AppConfig()
    cfg.image_backend = "mock"
    monkeypatch.setattr("axiom.config.load_config", lambda: cfg)

    mock_main = MagicMock()
    tabletop = TabletopView(main_window=mock_main)
    qtbot.addWidget(tabletop)
    tabletop._save_id = "save_test_123"
    tabletop._turn_id = 2
    tabletop._history = [
        {
            "turn_id": 1,
            "event_type": "narrative_text",
            "payload": {"variants": ["First scene."], "active": 0},
        },
        {
            "turn_id": 2,
            "event_type": "narrative_text",
            "payload": {"variants": ["You enter a glowing crystal cavern."], "active": 0},
        },
    ]

    mock_img_path = tmp_path / "turn_2.png"
    mock_img_path.write_bytes(b"\x89PNG\r\n\x1a\nfake_image")

    mock_illus_svc = MagicMock()
    mock_illus_svc.generate_turn_image.return_value = mock_img_path

    mock_registry = MagicMock()
    mock_registry.get_service.return_value = mock_illus_svc
    monkeypatch.setattr("axiom.kernel.registry.get_active_registry", lambda: mock_registry)

    # Spy on chat
    spy_show = MagicMock(side_effect=tabletop._chat.show_image_placeholder)
    spy_append = MagicMock(side_effect=tabletop._chat.append_image)
    tabletop._chat.show_image_placeholder = spy_show
    tabletop._chat.append_image = spy_append

    tabletop._on_generate_image_clicked()

    worker = tabletop._image_worker
    assert worker is not None
    # Wait for the thread to complete
    qtbot.waitUntil(lambda: not worker.isRunning(), timeout=3000)

    mock_illus_svc.generate_turn_image.assert_called_once()
    _, kwargs = mock_illus_svc.generate_turn_image.call_args
    assert kwargs["save_id"] == "save_test_123"
    assert kwargs["turn_id"] == 2
    assert kwargs["narrative_text"] == "You enter a glowing crystal cavern."
    assert kwargs["force"] is True

    spy_show.assert_called_once()
    spy_append.assert_called_once_with(mock_img_path)
    assert tabletop._image_btn.isEnabled()


def test_on_generate_image_error_flow(qtbot, monkeypatch) -> None:
    """When ImageWorker fails, placeholder is removed and button re-enabled."""
    cfg = AppConfig()
    monkeypatch.setattr("axiom.config.load_config", lambda: cfg)

    mock_main = MagicMock()
    tabletop = TabletopView(main_window=mock_main)
    qtbot.addWidget(tabletop)
    tabletop._save_id = "save_test_123"
    tabletop._turn_id = 1
    tabletop._history = [
        {
            "turn_id": 1,
            "event_type": "narrative_text",
            "payload": {"variants": ["Dark forest."], "active": 0},
        }
    ]

    mock_illus_svc = MagicMock()
    mock_illus_svc.generate_turn_image.side_effect = RuntimeError("Backend offline")

    mock_registry = MagicMock()
    mock_registry.get_service.return_value = mock_illus_svc
    monkeypatch.setattr("axiom.kernel.registry.get_active_registry", lambda: mock_registry)

    spy_clear = MagicMock(side_effect=tabletop._chat.clear_image_placeholder)
    tabletop._chat.clear_image_placeholder = spy_clear

    tabletop._on_generate_image_clicked()

    worker = tabletop._image_worker
    assert worker is not None
    qtbot.waitUntil(lambda: not worker.isRunning(), timeout=3000)

    spy_clear.assert_called()
    assert tabletop._image_btn.isEnabled()
    mock_main.on_status_update.assert_called()
    last_status = mock_main.on_status_update.call_args[0][0]
    assert "Backend offline" in last_status
