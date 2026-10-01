"""
tests/test_mods_dialog_ui.py

Unit and integration tests for the graphical Mods Manager UI (ModsDialog)
and its integration into the main application menu bar.
"""

from __future__ import annotations

from pathlib import Path
import pytest
from PySide6.QtCore import Qt

from axiom.config import load_config, save_config
from axiom.kernel.manifest import ModContributes, ModManifest, ModOrdering
from mods.axiom.ui.qt.ui.mods_dialog import ModsDialog, categorize_mod


def test_categorize_mod_rules():
    """Verify that different mod profiles are categorized accurately."""
    # World model
    m_world = ModManifest(
        id="axiom.world",
        name="World Model",
        version="1.0.0",
        axiom_api=1,
        ordering=ModOrdering(provides=["world_model"]),
    )
    cat_world, icon_world = categorize_mod(m_world)
    assert icon_world == "🌍"
    assert "Monde" in cat_world or "World" in cat_world

    # Turn pipeline
    m_turn = ModManifest(
        id="axiom.turn",
        name="Turn Pipeline",
        version="1.0.0",
        axiom_api=1,
        ordering=ModOrdering(provides=["turn_pipeline"]),
    )
    cat_turn, icon_turn = categorize_mod(m_turn)
    assert icon_turn == "🔄"

    # Timekeeper
    m_time = ModManifest(
        id="axiom.time",
        name="Timekeeper",
        version="1.0.0",
        axiom_api=1,
        ordering=ModOrdering(provides=["time"]),
    )
    cat_time, icon_time = categorize_mod(m_time)
    assert icon_time == "⏳"

    # Inventory
    m_inv = ModManifest(
        id="axiom.inventory",
        name="Inventory",
        version="1.0.0",
        axiom_api=1,
        ordering=ModOrdering(provides=["inventory"]),
    )
    cat_inv, icon_inv = categorize_mod(m_inv)
    assert icon_inv == "🎒"

    # Memory / RAG
    m_rag = ModManifest(
        id="axiom.rag",
        name="Semantic Memory",
        version="1.0.0",
        axiom_api=1,
    )
    cat_rag, icon_rag = categorize_mod(m_rag)
    assert icon_rag == "🧠"

    # Providers
    m_prov = ModManifest(
        id="axiom.providers",
        name="AI Providers",
        version="1.0.0",
        axiom_api=1,
    )
    cat_prov, icon_prov = categorize_mod(m_prov)
    assert icon_prov == "🤖"

    # Illustrations
    m_ill = ModManifest(
        id="axiom.illustrations",
        name="Illustrations",
        version="1.0.0",
        axiom_api=1,
    )
    cat_ill, icon_ill = categorize_mod(m_ill)
    assert icon_ill == "🎨"

    # Patches
    m_patch = ModManifest(
        id="community.custom_patch",
        name="Custom Patch",
        version="0.1.0",
        axiom_api=1,
        contributes=ModContributes(patches=["axiom.world:calc"]),
    )
    cat_patch, icon_patch = categorize_mod(m_patch)
    assert icon_patch == "⚡"


def test_mods_dialog_loads_and_displays_installed_mods(qtbot, isolated_axiom_data_dir):
    """Verify that ModsDialog populates installed mods and displays metadata."""
    dialog = ModsDialog()
    qtbot.addWidget(dialog)

    # Ensure list widget contains installed mods (from mods/ and dist/mods/)
    assert dialog._mod_list.count() > 0

    # First item should be selected by default
    current_item = dialog._mod_list.currentItem()
    assert current_item is not None

    manifest, path = current_item.data(Qt.UserRole)
    assert manifest.id
    assert manifest.name

    # Check detail pane widgets
    assert dialog._title_lbl.text()
    assert dialog._desc_lbl.text()
    assert dialog._changes_lbl.text()
    assert dialog._badge_id.text().startswith("ID:")


def test_mods_dialog_toggle_activation(qtbot, isolated_axiom_data_dir):
    """Verify that clicking the toggle button enables and disables the mod in configuration."""
    dialog = ModsDialog()
    qtbot.addWidget(dialog)

    # Select a known mod, e.g. community.lockpicking or core.stat_dynamics or first item
    first_item = dialog._mod_list.item(0)
    assert first_item is not None
    dialog._mod_list.setCurrentItem(first_item)

    manifest, _ = first_item.data(Qt.UserRole)
    mod_id = manifest.id

    # Read current state
    cfg = load_config()
    orig_state = cfg.mod_settings.get(mod_id, {}).get("enabled", True)

    # Toggle state
    dialog._toggle_btn.click()

    # Verify config was updated and saved
    updated_cfg = load_config()
    new_state = updated_cfg.mod_settings.get(mod_id, {}).get("enabled", True)
    assert new_state == (not orig_state)

    # Toggle back to original state
    dialog._toggle_btn.click()
    restored_cfg = load_config()
    assert restored_cfg.mod_settings.get(mod_id, {}).get("enabled", True) == orig_state


def test_mods_dialog_search_filter(qtbot, isolated_axiom_data_dir):
    """Verify that typing in search input filters the list."""
    dialog = ModsDialog()
    qtbot.addWidget(dialog)

    initial_count = dialog._mod_list.count()
    assert initial_count >= 5

    # Filter for 'turn'
    dialog._search_input.setText("turn")
    filtered_count = dialog._mod_list.count()
    assert 0 < filtered_count <= initial_count

    for idx in range(filtered_count):
        item = dialog._mod_list.item(idx)
        manifest, _ = item.data(Qt.UserRole)
        cat_label, _ = categorize_mod(manifest)
        text_corpus = f"{manifest.id} {manifest.name} {manifest.description} {cat_label}".lower()
        assert "turn" in text_corpus


def test_main_window_menu_has_mods_menu(qtbot, isolated_axiom_data_dir, monkeypatch):
    """Verify that MainWindow menuBar contains a 'Mods' menu with management action."""
    from mods.axiom.ui.qt.ui.main_window import MainWindow

    # Mock heavy dependencies in MainWindow
    monkeypatch.setattr("mods.axiom.ui.qt.ui.main_window.MainWindow._check_first_launch", lambda self: None)
    monkeypatch.setattr("axiom.config.load_config", lambda: load_config())

    win = MainWindow()
    qtbot.addWidget(win)

    menu_bar = win.menuBar()
    actions = menu_bar.actions()
    action_texts = [a.text().replace("&", "") for a in actions]

    assert "Mods" in action_texts

    # Find the Mods menu
    mods_action = next(a for a in actions if a.text().replace("&", "") == "Mods")
    mods_menu = mods_action.menu()
    assert mods_menu is not None

    menu_item_texts = [a.text().replace("&", "").rstrip("…") for a in mods_menu.actions()]
    assert any("Gérer les mods" in t or "Manage Mods" in t for t in menu_item_texts)
