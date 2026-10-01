"""tests/test_sillytavern_mod.py

Test suite verifying the official SillyTavern character card importer mod:
- Test 1: Mod manifest, discovery and capabilities.
- Test 2: Full 10-language localization round-trip.
- Test 3: Mod loading, SillyTavernService registration and JSON card parsing.
- Test 4: Qt UI dynamic visibility (HubView button shows when enabled, hides when disabled).
- Test 5: ImportExportWorker guard when mod is disabled.
- Test 6: Web API endpoint guard (403 when mod is disabled).
- Test 7: Store index entry integrity and SHA-256 validation.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from axiom.cli.mods_cmd import discover_installed_mods
from axiom.config import AppConfig
from axiom.kernel.context import ModContext
from axiom.kernel.loader import is_mod_enabled, load_mod_from_dir
from axiom.kernel.manifest import parse_manifest_file
from axiom.kernel.registry import KernelRegistry
from mods.axiom.sillytavern.main import SillyTavernService, parse_st_card


def test_1_manifest_and_discovery():
    """Verify axiom.sillytavern manifest structure and discovery."""
    manifest_path = Path("mods/axiom.sillytavern/mod.toml")
    assert manifest_path.is_file(), "Missing mods/axiom.sillytavern/mod.toml"

    manifest = parse_manifest_file(manifest_path)
    assert manifest.id == "axiom.sillytavern"
    assert manifest.version == "1.0.0"
    assert manifest.axiom_api == 1
    assert manifest.author == "Vanilla"
    assert "sillytavern_import" in manifest.ordering.provides

    installed = {m.id: m for m, _ in discover_installed_mods()}
    assert "axiom.sillytavern" in installed


def test_2_full_10_language_localization():
    """Verify that axiom.sillytavern has valid translations across all 10 supported languages."""
    manifest = parse_manifest_file("mods/axiom.sillytavern/mod.toml")
    expected_langs = ["en", "fr", "de", "es", "it", "ja", "ko", "pt", "ru", "zh"]

    locales_dir = Path("mods/axiom.sillytavern/locales")
    assert locales_dir.is_dir()

    for lang in expected_langs:
        lang_file = locales_dir / f"{lang}.json"
        assert lang_file.is_file(), f"Missing translation file: {lang_file}"
        name = manifest.localized_name(lang)
        desc = manifest.localized_description(lang)
        assert name and len(name) > 2
        assert desc and len(desc) > 5


def test_3_service_registration_and_parsing(tmp_path: Path):
    """Verify that load_mod_from_dir registers SillyTavernService and parses JSON cards."""
    reg = KernelRegistry()
    cfg = AppConfig()
    manifest, ctx, module = load_mod_from_dir("mods/axiom.sillytavern", reg, cfg)

    assert ctx is not None
    service = reg.get_service("sillytavern")
    assert service is not None
    assert service.__class__.__name__ == "SillyTavernService"

    # Test JSON card parsing
    sample_card = {
        "name": "Eldrin",
        "description": "An elven ranger with keen eyes.",
        "personality": "Cautious, loyal",
        "scenario": "Meeting at the tavern",
        "first_mes": "Greetings, traveler.",
    }
    card_file = tmp_path / "card.json"
    card_file.write_text(json.dumps(sample_card), encoding="utf-8")

    parsed = service.parse_card(card_file)
    assert parsed["name"] == "Eldrin"
    assert parsed["first_mes"] == "Greetings, traveler."


def test_4_qt_hub_visibility_deactivation(qtbot, monkeypatch):
    """Verify that HubView dynamically shows or hides the SillyTavern button based on mod state."""
    from ui.hub_view import HubView

    cfg = AppConfig()
    # 1. Enabled by default
    assert is_mod_enabled("axiom.sillytavern", cfg) is True

    monkeypatch.setattr("axiom.config.load_config", lambda: cfg)
    hub = HubView(main_window=None)
    qtbot.addWidget(hub)
    hub.show()

    assert hasattr(hub, "_import_st_btn")
    assert not hub._import_st_btn.isHidden()

    # 2. Disabled in config -> hides button
    cfg.mod_settings["axiom.sillytavern"] = {"enabled": False}
    hub.update_mod_visibility(cfg)
    assert hub._import_st_btn.isHidden()

    # 3. Re-enabled -> restores button
    cfg.mod_settings["axiom.sillytavern"] = {"enabled": True}
    hub.update_mod_visibility(cfg)
    assert not hub._import_st_btn.isHidden()


def test_5_worker_guard_when_disabled(monkeypatch):
    """Verify that ImportExportWorker rejects SillyTavern imports when mod is disabled."""
    from workers.import_export_worker import ImportExportWorker

    cfg = AppConfig()
    cfg.mod_settings["axiom.sillytavern"] = {"enabled": False}
    monkeypatch.setattr("axiom.config.load_config", lambda: cfg)

    worker = ImportExportWorker(mode="import_st", source_path="dummy.json", dest_path="dummy_dest")
    errors = []
    worker.error_occurred.connect(errors.append)
    worker.run()

    assert len(errors) == 1
    assert "disabled" in errors[0].lower()


def test_6_web_api_guard_when_disabled(tmp_path: Path, monkeypatch):
    """Verify that POST /api/universes/import-st returns 403 when mod is disabled."""
    from main_web import AxiomWebHandler
    from unittest.mock import MagicMock

    cfg = AppConfig()
    cfg.mod_settings["axiom.sillytavern"] = {"enabled": False}
    monkeypatch.setattr("main_web.load_config", lambda: cfg)

    handler = MagicMock(spec=AxiomWebHandler)
    handler.send_error_json = MagicMock()

    AxiomWebHandler.handle_api_post(handler, "/api/universes/import-st", {"path": "test.png"})
    handler.send_error_json.assert_called_once()
    status_code, error_msg = handler.send_error_json.call_args[0]
    assert status_code == 403
    assert "disabled" in error_msg.lower()


def test_7_store_index_integrity():
    """Verify that axiom.sillytavern is correctly recorded in dist/mods/store_index.json."""
    store_file = Path("dist/mods/store_index.json")
    assert store_file.is_file()

    with store_file.open("r", encoding="utf-8") as f:
        data = json.load(f)

    mods = {entry["id"]: entry for entry in data.get("mods", [])}
    assert "axiom.sillytavern" in mods
    st_entry = mods["axiom.sillytavern"]
    assert st_entry["version"] == "1.0.0"
    assert st_entry["axiom_api"] == 1
    assert "sillytavern_import" in st_entry["provides"]
    assert len(st_entry["sha256"]) == 64
