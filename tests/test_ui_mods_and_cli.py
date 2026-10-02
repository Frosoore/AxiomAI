"""tests/test_ui_mods_and_cli.py

Integration and unit tests for Phase 2 (Fin):
- UI Mods (axiom.ui.web, axiom.ui.qt, axiom.cli)
- Web UI side panel extension via slot
- Cross-cutting i18n ('axiom.kernel:locales') and help system ('axiom.kernel:help_entries')
- CLI mod management (axiom mods list/enable/disable) & safe-mode recovery
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

import pytest

import axiom.paths
from axiom.cli.mods_cmd import (
    discover_installed_mods,
    run_mod_disable,
    run_mod_enable,
    run_mod_list,
)
from axiom.config import AppConfig, load_config, save_config
from axiom.kernel import (
    KernelRegistry,
    ModContext,
    is_mod_enabled,
    is_official_mod,
    is_safe_mode,
    load_mod,
    load_mod_from_archive,
    parse_manifest_file,
    set_safe_mode,
)
from core.localization import reload_translations, set_language, tr
import mods.axiom.help_system.ui.help_system as help_sys


def test_manifests_and_loading_ui_mods(tmp_path):
    """1. Manifest validation and runtime loading of axiom.ui.web, axiom.ui.qt, and axiom.cli."""
    reg = KernelRegistry()
    cfg = AppConfig()

    mods_to_test = ["axiom.ui.web", "axiom.ui.qt", "axiom.cli"]

    for mod_id in mods_to_test:
        mod_dir = Path("mods") / mod_id
        assert mod_dir.is_dir(), f"Mod directory missing: {mod_dir}"

        manifest = parse_manifest_file(mod_dir / "mod.toml")
        assert manifest.id == mod_id
        assert manifest.version == "1.0.0"
        assert manifest.axiom_api == 1
        assert "user_interface" in manifest.ordering.provides

        # Load from directory
        m, ctx, module = load_mod(mod_dir, reg, config=cfg)
        assert m.id == mod_id
        assert ctx is not None
        assert module is not None

        # Also verify the packed .axmod loads (built in tmp_path: dist/ is not versioned)
        from axiom.cli.mods_cmd import pack_mod
        archive_path = pack_mod(mod_dir, tmp_path / f"{mod_id}.axmod")
        assert archive_path.is_file(), f"Archive missing: {archive_path}"
        reg_archive = KernelRegistry()
        m_arc, ctx_arc, _ = load_mod_from_archive(archive_path, reg_archive, config=cfg)
        assert m_arc.id == mod_id
        assert ctx_arc is not None

    # Check services registered in registry
    assert reg.get_service("web_ui") is not None
    assert reg.get_service("qt_ui") is not None
    assert reg.get_service("cli_play") is not None


def test_web_ui_side_panel_extension():
    """2. Test slot 'axiom.ui.web:side_panel' contribution from a third-party mod."""
    reg = KernelRegistry()
    cfg = AppConfig()

    # Load web UI mod
    load_mod(Path("mods/axiom.ui.web"), reg, config=cfg)
    web_svc = reg.get_service("web_ui")
    assert web_svc is not None

    # Initial side panels
    assert web_svc.get_side_panels() == []

    # Contribute a third-party component to slot
    reg.add_to_slot(
        "axiom.ui.web:side_panel",
        "thirdparty.hunger",
        {
            "id": "hunger_gauge",
            "title": "Hunger",
            "component": "HungerGaugeWidget",
            "order": 10,
        },
    )

    panels = web_svc.get_side_panels()
    assert len(panels) == 1
    assert panels[0]["id"] == "hunger_gauge"
    assert panels[0]["component"] == "HungerGaugeWidget"

    # Enrich snapshot
    snapshot = {"turn_id": 1, "entities": []}
    enriched = web_svc.enrich_session_snapshot(snapshot)
    assert "side_panels" in enriched
    assert len(enriched["side_panels"]) == 1
    assert enriched["side_panels"][0]["id"] == "hunger_gauge"


def test_locales_slot_injection():
    """3. Test injection of new i18n translation keys via 'axiom.kernel:locales'."""
    reg = KernelRegistry()

    # Contribute multilingual dictionary via slot
    reg.add_to_slot(
        "axiom.kernel:locales",
        "thirdparty.magic",
        {
            "en": {"spell_fireball_name": "Fireball", "spell_fireball_desc": "Launches a fiery sphere."},
            "fr": {"spell_fireball_name": "Boule de feu", "spell_fireball_desc": "Lance une sphère enflammée."},
        },
    )

    # Force translation reload to incorporate active registry
    reload_translations()

    try:
        set_language("en")
        assert tr("spell_fireball_name") == "Fireball"
        assert tr("spell_fireball_desc") == "Launches a fiery sphere."

        set_language("fr")
        assert tr("spell_fireball_name") == "Boule de feu"
        assert tr("spell_fireball_desc") == "Lance une sphère enflammée."
    finally:
        set_language("en")
        reload_translations()


def test_help_entries_slot_injection():
    """4. Test dynamic help entries contributed via 'axiom.kernel:help_entries'."""
    reg = KernelRegistry()

    entry = {
        "ref": "magic.spellbook",
        "page": "magic",
        "element": "spellbook",
        "title": "Arcane Spellbook",
        "body": "Displays memorized spells and mana consumption.",
    }

    reg.add_to_slot("axiom.kernel:help_entries", "thirdparty.magic", entry)

    assert help_sys._is_known("magic.spellbook")
    html = help_sys.tooltip_html("magic.spellbook")
    assert "Arcane Spellbook" in html
    assert "Displays memorized spells" in html


def test_cli_mods_management_and_safe_mode(tmp_path: Path, monkeypatch):
    """5. Test CLI mod commands (list, enable, disable) and safe-mode."""
    cfg_file = tmp_path / "settings.json"
    axiom.paths.configure(config_dir=tmp_path)

    try:
        # 1. Discover installed mods
        discovered = discover_installed_mods()
        discovered_ids = {m[0].id for m in discovered}
        assert "axiom.world" in discovered_ids
        assert "axiom.ui.web" in discovered_ids

        # 2. Test list command
        buf = io.StringIO()
        monkeypatch.setattr(sys, "stdout", buf)
        ret = run_mod_list(argparse.Namespace())
        assert ret == 0
        output = buf.getvalue()
        assert "axiom.ui.web" in output
        assert "MOD ID" in output

        # 3. Test disable mod
        ret_dis = run_mod_disable(argparse.Namespace(mod_id="axiom.illustrations"))
        assert ret_dis == 0
        cfg = load_config()
        assert cfg.mod_settings.get("axiom.illustrations", {}).get("enabled") is False
        assert not is_mod_enabled("axiom.illustrations", cfg)

        # 4. Test enable mod
        ret_en = run_mod_enable(argparse.Namespace(mod_id="axiom.illustrations"))
        assert ret_en == 0
        cfg = load_config()
        assert cfg.mod_settings.get("axiom.illustrations", {}).get("enabled") is True
        assert is_mod_enabled("axiom.illustrations", cfg)

        # 5. Test safe mode
        set_safe_mode(False)
        assert not is_safe_mode()
        assert is_official_mod("axiom.world")
        assert is_official_mod("core.stat_dynamics")
        assert not is_official_mod("thirdparty.custom")

        # In normal mode, thirdparty mod is enabled by default
        assert is_mod_enabled("thirdparty.custom", cfg)

        # Enable safe mode
        set_safe_mode(True)
        assert is_safe_mode()
        # Official mods stay enabled
        assert is_mod_enabled("axiom.world", cfg)
        assert is_mod_enabled("core.stat_dynamics", cfg)
        # Thirdparty mod is disabled
        assert not is_mod_enabled("thirdparty.custom", cfg)

        # Loading a fake thirdparty mod directory is skipped in safe mode
        fake_mod_dir = tmp_path / "thirdparty.test"
        fake_mod_dir.mkdir()
        (fake_mod_dir / "mod.toml").write_text(
            """[mod]
id = "thirdparty.test"
version = "1.0.0"
axiom_api = 1
name = "Third Party Test"
""",
            encoding="utf-8",
        )
        (fake_mod_dir / "main.py").write_text("def init(ctx): pass\n", encoding="utf-8")

        reg = KernelRegistry()
        m, ctx, mod = load_mod(fake_mod_dir, reg, config=cfg)
        assert m.id == "thirdparty.test"
        assert ctx is None
        assert mod is None

    finally:
        set_safe_mode(False)
        axiom.paths.reset()


def test_entrypoints_disabled_mods(tmp_path: Path, monkeypatch):
    """Entrypoints main.py, main_web.py, and axiom play must refuse to start if their UI mod is disabled."""
    axiom.paths.configure(config_dir=tmp_path)
    try:
        cfg = AppConfig()

        # 1. Test main.py with axiom.ui.qt disabled
        cfg.mod_settings["axiom.ui.qt"] = {"enabled": False}
        save_config(cfg)
        monkeypatch.setattr(sys, "argv", ["main.py"])
        import PySide6.QtWidgets
        monkeypatch.setattr(PySide6.QtWidgets.QMessageBox, "critical", lambda *args, **kwargs: None)

        import main
        ret = main.main()
        assert ret == 1

        # 2. Test main_web.py with axiom.ui.web disabled
        cfg.mod_settings["axiom.ui.web"] = {"enabled": False}
        save_config(cfg)
        import main_web
        ret_web = main_web.run_server(port=9999)
        assert ret_web == 1

        # 3. Test axiom play with axiom.cli disabled
        cfg.mod_settings["axiom.cli"] = {"enabled": False}
        save_config(cfg)
        from axiom.cli.play import run_play
        ret_cli = run_play(argparse.Namespace(universe="test.axiom"))
        assert ret_cli == 1
    finally:
        axiom.paths.reset()


def test_mods_dialog_deactivate_active_ui(qtbot, monkeypatch, tmp_path: Path):
    """Disabling axiom.ui.qt from within ModsDialog prompts for confirmation and exits cleanly."""
    axiom.paths.configure(config_dir=tmp_path)
    try:
        cfg = AppConfig()
        cfg.mod_settings["axiom.ui.qt"] = {"enabled": True}
        save_config(cfg)

        from mods.axiom.ui.qt.ui.mods_dialog import ModsDialog
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QMessageBox

        dialog = ModsDialog(parent=None)
        qtbot.addWidget(dialog)

        # Find axiom.ui.qt in the list
        qt_item = None
        for i in range(dialog._mod_list.count()):
            item = dialog._mod_list.item(i)
            data = item.data(Qt.UserRole)
            if data and isinstance(data, tuple) and data[0].id == "axiom.ui.qt":
                qt_item = item
                break

        assert qt_item is not None
        dialog._mod_list.setCurrentItem(qt_item)
        assert dialog._current_manifest.id == "axiom.ui.qt"

        # Case 1: User says NO to confirmation dialog
        monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.No)
        dialog._toggle_current_mod()
        cfg_reloaded = load_config()
        assert is_mod_enabled("axiom.ui.qt", cfg_reloaded)

        # Case 2: User says YES to confirmation dialog
        quit_called = []
        monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        monkeypatch.setattr(app, "quit", lambda: quit_called.append(True))

        dialog._toggle_current_mod()
        assert len(quit_called) == 1
        cfg_reloaded = load_config()
        assert not is_mod_enabled("axiom.ui.qt", cfg_reloaded)
    finally:
        axiom.paths.reset()


def test_qt_slots_instantiate_widget_classes(qtbot):
    """axiom.ui.qt:sidebar_widget and axiom.ui.qt:settings_tab instantiate contributed widget classes."""
    from PySide6.QtWidgets import QWidget, QLabel
    from axiom.kernel.registry import KernelRegistry, set_active_registry
    from mods.axiom.ui.qt.ui.constants_sidebar import ConstantsSidebar
    from mods.axiom.ui.qt.ui.settings_dialog import SettingsDialog

    reg = KernelRegistry()
    set_active_registry(reg)

    class CustomSidebarWidget(QWidget):
        widget_id = "custom_sidebar"
        title_key = "custom_sidebar_title"

        def __init__(self, parent=None):
            super().__init__(parent)
            label = QLabel("Custom Sidebar Content", self)

    class CustomSettingsTab(QWidget):
        tab_id = "custom_tab"
        title_key = "custom_tab_title"

        def __init__(self, parent=None):
            super().__init__(parent)
            label = QLabel("Custom Tab Content", self)

    reg.add_to_slot("axiom.ui.qt:sidebar_widget", "test.mod", CustomSidebarWidget)
    reg.add_to_slot("axiom.ui.qt:settings_tab", "test.mod", CustomSettingsTab)

    sidebar = ConstantsSidebar()
    qtbot.addWidget(sidebar)
    tab_titles = [sidebar._tabs.tabText(i) for i in range(sidebar._tabs.count())]
    assert "custom_sidebar_title" in tab_titles

    settings = SettingsDialog(config=AppConfig())
    qtbot.addWidget(settings)
    settings_tab_titles = [settings._tabs.tabText(i) for i in range(settings._tabs.count())]
    assert "custom_tab_title" in settings_tab_titles

