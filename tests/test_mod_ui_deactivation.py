"""tests/test_mod_ui_deactivation.py

Test suite verifying dynamic UI deactivation when mods are disabled:
- Test 1: With default config (all mods enabled), SettingsDialog contains the 'Génération d'images' tab and 'Mémoire' tab.
- Test 2: When axiom.illustrations is disabled, SettingsDialog does NOT contain the 'Génération d'images' tab (tab_image title or _image_widget), and image generation buttons in Tabletop are disabled/hidden.
- Test 3: When axiom.living_memory is disabled, SettingsDialog does NOT contain the 'Mémoire' tab (tab_memory title or _memory_widget), and _memory_btn in Tabletop is hidden.
- Test 4: When axiom.time is disabled, _time_label in Tabletop is hidden.
- Test 5: When axiom.inventory is disabled, ConstantsSidebar omits the inventory tab.
- Test 6: Re-enabling axiom.illustrations restores the 'Génération d'images' tab in SettingsDialog.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt

from axiom.config import AppConfig
from mods.axiom.ui.qt.ui.constants_sidebar import ConstantsSidebar
from mods.axiom.ui.qt.ui.settings_dialog import SettingsDialog
from mods.axiom.ui.qt.ui.tabletop_view import TabletopView


def test_1_default_config_has_image_and_memory_tabs(qtbot) -> None:
    """Test 1: With default config (all mods enabled), SettingsDialog contains
    the 'Génération d'images' tab and 'Mémoire' tab.
    """
    cfg = AppConfig()
    dialog = SettingsDialog(cfg)
    qtbot.addWidget(dialog)

    # 1. Check widget references in tabs
    assert dialog._tabs.indexOf(dialog._image_widget) != -1
    assert dialog._tabs.indexOf(dialog._memory_widget) != -1

    # 2. Check tab titles
    tab_titles = [dialog._tabs.tabText(i).lower() for i in range(dialog._tabs.count())]
    assert any("illustration" in t or "image" in t for t in tab_titles)
    assert any("mémoire" in t or "memory" in t for t in tab_titles)


def test_2_illustrations_disabled_removes_tab_and_hides_tabletop_button(qtbot, monkeypatch) -> None:
    """Test 2: When axiom.illustrations is disabled in config.mod_settings['axiom.illustrations'] = {'enabled': False},
    SettingsDialog does NOT contain the 'Génération d'images' tab (tab_image title or _image_widget),
    and image generation buttons in Tabletop are disabled/hidden.
    """
    cfg = AppConfig()
    cfg.mod_settings["axiom.illustrations"] = {"enabled": False}

    # Verify SettingsDialog
    dialog = SettingsDialog(cfg)
    qtbot.addWidget(dialog)

    assert dialog._tabs.indexOf(dialog._image_widget) == -1
    for i in range(dialog._tabs.count()):
        assert dialog._tabs.widget(i) != dialog._image_widget
        t = dialog._tabs.tabText(i).lower()
        assert not ("illustration" in t or "image" in t)

    # Verify TabletopView
    monkeypatch.setattr("axiom.config.load_config", lambda: cfg)
    tabletop = TabletopView()
    qtbot.addWidget(tabletop)

    assert hasattr(tabletop, "_image_btn")
    assert not tabletop._image_btn.isVisible() or not tabletop._image_btn.isEnabled()


def test_3_living_memory_disabled_removes_tab_and_hides_memory_button(qtbot, monkeypatch) -> None:
    """Test 3: When axiom.living_memory is disabled, SettingsDialog does NOT contain
    the 'Mémoire' tab (tab_memory title or _memory_widget), and _memory_btn in Tabletop is hidden.
    """
    cfg = AppConfig()
    cfg.mod_settings["axiom.living_memory"] = {"enabled": False}

    # Verify SettingsDialog
    dialog = SettingsDialog(cfg)
    qtbot.addWidget(dialog)

    assert dialog._tabs.indexOf(dialog._memory_widget) == -1
    for i in range(dialog._tabs.count()):
        assert dialog._tabs.widget(i) != dialog._memory_widget
        t = dialog._tabs.tabText(i).lower()
        assert not ("mémoire" in t or "memory" in t)

    # Verify TabletopView
    monkeypatch.setattr("axiom.config.load_config", lambda: cfg)
    tabletop = TabletopView()
    qtbot.addWidget(tabletop)

    assert hasattr(tabletop, "_memory_btn")
    assert not tabletop._memory_btn.isVisible()


def test_4_time_disabled_hides_time_label(qtbot, monkeypatch) -> None:
    """Test 4: When axiom.time is disabled, _time_label in Tabletop is hidden."""
    cfg = AppConfig()
    cfg.mod_settings["axiom.time"] = {"enabled": False}

    monkeypatch.setattr("axiom.config.load_config", lambda: cfg)
    tabletop = TabletopView()
    qtbot.addWidget(tabletop)

    assert hasattr(tabletop, "_time_label")
    assert not tabletop._time_label.isVisible()


def test_5_inventory_disabled_omits_inventory_tab_in_sidebar(qtbot, monkeypatch) -> None:
    """Test 5: When axiom.inventory is disabled, ConstantsSidebar omits the inventory tab."""
    cfg = AppConfig()
    cfg.mod_settings["axiom.inventory"] = {"enabled": False}

    monkeypatch.setattr("axiom.config.load_config", lambda: cfg)
    sidebar = ConstantsSidebar(config=cfg)
    qtbot.addWidget(sidebar)

    assert sidebar._tabs.indexOf(sidebar._inv_scroll) == -1
    for i in range(sidebar._tabs.count()):
        assert sidebar._tabs.widget(i) != sidebar._inv_scroll
        t = sidebar._tabs.tabText(i).lower()
        assert not ("inventaire" in t or "inventory" in t)


def test_6_reenabling_illustrations_restores_tab(qtbot) -> None:
    """Test 6: Re-enabling axiom.illustrations restores the 'Génération d'images' tab in SettingsDialog."""
    cfg = AppConfig()
    cfg.mod_settings["axiom.illustrations"] = {"enabled": False}

    dialog = SettingsDialog(cfg)
    qtbot.addWidget(dialog)
    assert dialog._tabs.indexOf(dialog._image_widget) == -1

    # Re-enable via update_mod_tabs
    cfg.mod_settings["axiom.illustrations"] = {"enabled": True}
    dialog.update_mod_tabs(cfg)
    assert dialog._tabs.indexOf(dialog._image_widget) != -1

    tab_titles = [dialog._tabs.tabText(i).lower() for i in range(dialog._tabs.count())]
    assert any("illustration" in t or "image" in t for t in tab_titles)

    # Also verify re-enabling in a fresh dialog instance
    dialog_fresh = SettingsDialog(cfg)
    qtbot.addWidget(dialog_fresh)
    assert dialog_fresh._tabs.indexOf(dialog_fresh._image_widget) != -1
