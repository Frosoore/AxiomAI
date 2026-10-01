"""tests/test_help_system_mod.py

Test suite verifying the official Help System & Tooltips mod (axiom.help_system):
- Test 1: Mod manifest, discovery and capabilities.
- Test 2: Full 10-language localization round-trip.
- Test 3: Mod loading, HelpSystemService registration and public API.
- Test 4: Complete code detachment when mod is disabled (zero-overhead no-ops for doc, doc_tab, tooltip_html, etc.).
- Test 5: Dynamic UI visibility on HubView, SetupView, TabletopView, and CreatorStudioView.
- Test 6: MainWindow Help menu actions and F1 shortcut detachment when mod is disabled.
- Test 7: Store index entry integrity and SHA-256 validation.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication, QPushButton, QTabWidget, QWidget

from axiom.cli.mods_cmd import discover_installed_mods
from axiom.config import AppConfig
from axiom.kernel.context import ModContext
from axiom.kernel.loader import is_mod_enabled, load_mod_from_dir
from axiom.kernel.manifest import parse_manifest_file
from axiom.kernel.registry import KernelRegistry
from mods.axiom.help_system.ui import help_system
from mods.axiom.help_system.ui import help_dialogs


def test_1_manifest_and_discovery():
    """Verify axiom.help_system manifest structure and discovery."""
    manifest_path = Path("mods/axiom.help_system/mod.toml")
    assert manifest_path.is_file(), "Missing mods/axiom.help_system/mod.toml"

    manifest = parse_manifest_file(manifest_path)
    assert manifest.id == "axiom.help_system"
    assert manifest.version == "1.0.0"
    assert manifest.axiom_api == 1
    assert manifest.author == "Vanilla"
    assert "help_system" in manifest.ordering.provides
    assert "tooltips" in manifest.ordering.provides
    assert "inapp_documentation" in manifest.ordering.provides

    installed = {m.id: m for m, _ in discover_installed_mods()}
    assert "axiom.help_system" in installed


def test_2_full_10_language_localization():
    """Verify that axiom.help_system has valid translations across all 10 supported languages."""
    manifest = parse_manifest_file("mods/axiom.help_system/mod.toml")
    expected_langs = ["en", "fr", "de", "es", "it", "ja", "ko", "pt", "ru", "zh"]

    locales_dir = Path("mods/axiom.help_system/locales")
    assert locales_dir.is_dir()

    for lang in expected_langs:
        lang_file = locales_dir / f"{lang}.json"
        assert lang_file.is_file(), f"Missing translation file: {lang_file}"
        name = manifest.localized_name(lang)
        desc = manifest.localized_description(lang)
        assert name and len(name) > 2
        assert desc and len(desc) > 5


def test_3_mod_loading_and_service_registration():
    """Verify that load_mod_from_dir registers HelpSystemService and provides its API."""
    reg = KernelRegistry()
    cfg = AppConfig()
    manifest, ctx, module = load_mod_from_dir("mods/axiom.help_system", reg, cfg)

    assert ctx is not None
    service = reg.get_service("help_system")
    assert service is not None
    assert service.__class__.__name__ == "HelpSystemService"
    assert service.is_available() is True

    pages = service.get_pages()
    assert isinstance(pages, dict)
    assert "hub" in pages
    assert "setup" in pages
    assert "tabletop" in pages
    assert "creator" in pages


def test_4_complete_detachment_when_disabled(qtbot, monkeypatch):
    """Verify total detachment of help system code when mod is disabled."""
    cfg = AppConfig()
    cfg.mod_settings["axiom.help_system"] = {"enabled": False}

    monkeypatch.setattr("axiom.config.load_config", lambda: cfg)

    # 1. doc() returns widget with NO tooltip attached
    btn = QPushButton("Action")
    qtbot.addWidget(btn)
    res_btn = help_system.doc(btn, "hub.import")
    assert res_btn is btn
    assert btn.toolTip() == ""

    # 2. doc_tab() does nothing
    tabs = QTabWidget()
    qtbot.addWidget(tabs)
    tabs.addTab(QWidget(), "Tab 1")
    help_system.doc_tab(tabs, 0, "setup.tab_saves")
    assert tabs.tabToolTip(0) == ""

    # 3. Tooltip functions return inactive states
    assert help_system.tooltips_enabled() is False
    assert help_system.tooltip_html("hub.import") == ""
    assert help_system.audit_undocumented(btn) == []

    # 4. make_help_button returns an invisible widget
    help_btn = help_dialogs.make_help_button("hub")
    qtbot.addWidget(help_btn)
    assert not help_btn.isVisible()


def test_5_ui_views_visibility_toggling(qtbot, monkeypatch):
    """Verify that HubView, SetupView, TabletopView and CreatorStudioView toggle Information button."""
    from mods.axiom.ui.qt.ui.hub_view import HubView
    from mods.axiom.ui.qt.ui.setup_view import SetupView
    from mods.axiom.ui.qt.ui.tabletop_view import TabletopView
    from mods.axiom.ui.qt.ui.creator_studio_view import CreatorStudioView

    # Enabled configuration
    cfg_enabled = AppConfig()
    cfg_enabled.mod_settings["axiom.help_system"] = {"enabled": True}
    monkeypatch.setattr("axiom.config.load_config", lambda: cfg_enabled)

    hub = HubView()
    qtbot.addWidget(hub)
    hub.show()
    assert hasattr(hub, "_help_btn")
    assert hub._help_btn.isVisible()

    setup = SetupView()
    qtbot.addWidget(setup)
    setup.show()
    assert hasattr(setup, "_help_btn")
    assert setup._help_btn.isVisible()

    studio = CreatorStudioView()
    qtbot.addWidget(studio)
    studio.show()
    assert hasattr(studio, "_help_btn")
    assert studio._help_btn.isVisible()

    tabletop = TabletopView()
    qtbot.addWidget(tabletop)
    tabletop.show()
    assert hasattr(tabletop, "_help_btn")
    assert tabletop._help_btn.isVisible()

    # Disabled configuration
    cfg_disabled = AppConfig()
    cfg_disabled.mod_settings["axiom.help_system"] = {"enabled": False}

    hub.update_mod_visibility(cfg_disabled)
    assert not hub._help_btn.isVisible()

    setup.update_mod_visibility(cfg_disabled)
    assert not setup._help_btn.isVisible()

    studio.update_mod_visibility(cfg_disabled)
    assert not studio._help_btn.isVisible()

    tabletop.update_mod_visibility(cfg_disabled)
    assert not tabletop._help_btn.isVisible()

    # Re-enable
    hub.update_mod_visibility(cfg_enabled)
    assert hub._help_btn.isVisible()
    setup.update_mod_visibility(cfg_enabled)
    assert setup._help_btn.isVisible()
    studio.update_mod_visibility(cfg_enabled)
    assert studio._help_btn.isVisible()
    tabletop.update_mod_visibility(cfg_enabled)
    assert tabletop._help_btn.isVisible()


def test_6_main_window_actions_decoupling(qtbot, monkeypatch):
    """Verify that MainWindow Help actions are detached when axiom.help_system is disabled."""
    from mods.axiom.ui.qt.ui.main_window import MainWindow

    cfg_enabled = AppConfig()
    cfg_enabled.mod_settings["axiom.help_system"] = {"enabled": True}
    monkeypatch.setattr("axiom.config.load_config", lambda: cfg_enabled)

    win = MainWindow()
    qtbot.addWidget(win)

    assert hasattr(win, "_explain_action")
    assert hasattr(win, "_directory_action")
    assert hasattr(win, "_tour_action")

    assert win._explain_action.isVisible()
    assert win._directory_action.isVisible()
    assert win._tour_action.isVisible()

    # Disable mod
    cfg_disabled = AppConfig()
    cfg_disabled.mod_settings["axiom.help_system"] = {"enabled": False}
    win.update_mod_visibility(cfg_disabled)

    assert not win._explain_action.isVisible() or not win._explain_action.isEnabled()
    assert not win._directory_action.isVisible() or not win._directory_action.isEnabled()
    assert not win._tour_action.isVisible() or not win._tour_action.isEnabled()

    # Re-enable mod
    win.update_mod_visibility(cfg_enabled)
    assert win._explain_action.isVisible() and win._explain_action.isEnabled()
    assert win._directory_action.isVisible() and win._directory_action.isEnabled()
    assert win._tour_action.isVisible() and win._tour_action.isEnabled()


def test_7_store_index_integrity_and_sha256():
    """Verify that store_index.json contains axiom.help_system with valid metadata and matching SHA-256."""
    store_file = Path("dist/mods/store_index.json")
    assert store_file.is_file()

    with store_file.open("r", encoding="utf-8") as f:
        data = json.load(f)

    mods = {m["id"]: m for m in data.get("mods", [])}
    assert "axiom.help_system" in mods

    entry = mods["axiom.help_system"]
    assert entry["version"] == "1.0.0"
    assert entry["author"] == "Vanilla"
    assert "help_system" in entry["provides"]

    archive_path = Path("dist/mods/axiom.help_system-1.0.0.axmod")
    assert archive_path.is_file(), f"Missing archive file: {archive_path}"

    hasher = hashlib.sha256()
    with archive_path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    actual_hash = hasher.hexdigest()

    assert actual_hash == entry["sha256"], f"SHA256 mismatch: {actual_hash} != {entry['sha256']}"
