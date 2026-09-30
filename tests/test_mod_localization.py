"""tests/test_mod_localization.py

Comprehensive tests for mod translation and multilingual fallback:
1. Validation of all 10 supported languages for all 12 official mods.
2. Localized name and description resolution in ModManifest.
3. Fallback logic for community mods with partial locales (falling back to English or any available translation).
4. Fallback logic for mods with zero locale files (falling back to mod.toml defaults).
5. Automatic registration of mod locales into the 'axiom.kernel:locales' slot upon mod loading.
6. Preservation and loading of locales from packed .axmod archives.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from axiom.cli.mods_cmd import pack_mod
from axiom.kernel.loader import load_mod_from_archive, load_mod_from_dir
from axiom.kernel.manifest import (
    ModManifest,
    load_manifest,
    load_manifest_from_archive,
    parse_manifest_file,
    parse_manifest_string,
)
from axiom.kernel.registry import KernelRegistry
from core.localization import SUPPORTED_LANGUAGES, reload_translations, set_kernel_registry, set_language, tr

OFFICIAL_MOD_IDS = [
    "axiom.cli",
    "axiom.illustrations",
    "axiom.inventory",
    "axiom.living_memory",
    "axiom.providers",
    "axiom.rag",
    "axiom.time",
    "axiom.turn",
    "axiom.ui.qt",
    "axiom.ui.web",
    "axiom.world",
    "core.stat_dynamics",
]


def test_official_mods_have_all_10_locales():
    """All 12 official mods must contain valid JSON translations for all 10 supported languages."""
    base_mods_dir = Path("mods")
    languages = list(SUPPORTED_LANGUAGES.keys())
    assert len(languages) == 10

    for mod_id in OFFICIAL_MOD_IDS:
        mod_dir = base_mods_dir / mod_id
        locales_dir = mod_dir / "locales"
        assert locales_dir.is_dir(), f"Mod '{mod_id}' missing 'locales/' directory."

        for lang in languages:
            locale_file = locales_dir / f"{lang}.json"
            assert locale_file.is_file(), f"Mod '{mod_id}' missing translation file for '{lang}'."

            data = json.loads(locale_file.read_text(encoding="utf-8"))
            assert isinstance(data, dict), f"Translation '{locale_file}' is not a valid JSON object."
            assert "title" in data and data["title"].strip(), f"'{locale_file}' missing non-empty 'title'."
            assert "description" in data and data["description"].strip(), f"'{locale_file}' missing non-empty 'description'."


def test_manifest_localized_name_and_description():
    """ModManifest loads locales from disk and resolves localized_name and localized_description."""
    manifest = parse_manifest_file("mods/axiom.world/mod.toml")

    assert len(manifest.locales) >= 10
    assert manifest.localized_name("en") == "TTRPG World Model"
    assert manifest.localized_name("fr") == "Modèle de Monde JDR"
    assert manifest.localized_name("ja") == "TRPG ワールドモデル"
    assert manifest.localized_name("zh") == "跑团世界模型"

    assert "deterministic" in manifest.localized_description("en").lower() or "entities" in manifest.localized_description("en").lower()
    assert "règles" in manifest.localized_description("fr").lower() or "entités" in manifest.localized_description("fr").lower()


def test_community_mod_fallback_to_english():
    """A community mod with only an English locale falls back gracefully to English for other app languages."""
    manifest = parse_manifest_file("mods/community.survival/mod.toml")

    # community.survival only has locales/en.json
    assert "en" in manifest.locales
    assert manifest.localized_name("en") == "Survival"

    # Querying other languages should fall back to English
    assert manifest.localized_name("fr") == "Survival"
    assert manifest.localized_name("es") == "Survival"
    assert manifest.localized_name("ja") == "Survival"
    assert manifest.localized_name("de") == "Survival"

    assert "survival extension mod" in manifest.localized_description("fr").lower()
    assert "survival extension mod" in manifest.localized_description("ja").lower()


def test_mod_fallback_to_any_available_locale(tmp_path: Path):
    """If a community mod has neither the requested language nor English, it uses any available locale."""
    mod_dir = tmp_path / "community.spanish_only"
    mod_dir.mkdir()
    (mod_dir / "mod.toml").write_text(
        """[mod]
id = "community.spanish_only"
version = "1.0.0"
axiom_api = 1
name = "Spanish Mod"
description = "Default description"
""",
        encoding="utf-8",
    )
    loc_dir = mod_dir / "locales"
    loc_dir.mkdir()
    (loc_dir / "es.json").write_text(
        json.dumps({"title": "Supervivencia", "description": "Mod de supervivencia en español."}),
        encoding="utf-8",
    )

    manifest = parse_manifest_file(mod_dir / "mod.toml")
    assert "es" in manifest.locales
    assert "en" not in manifest.locales

    # Querying Spanish gives exact match
    assert manifest.localized_name("es") == "Supervivencia"
    assert manifest.localized_description("es") == "Mod de supervivencia en español."

    # Querying French or Japanese falls back to the available Spanish translation
    assert manifest.localized_name("fr") == "Supervivencia"
    assert manifest.localized_name("ja") == "Supervivencia"
    assert manifest.localized_description("de") == "Mod de supervivencia en español."


def test_mod_fallback_to_manifest_defaults():
    """If a mod has no locales directory, localized_name and localized_description fall back to mod.toml."""
    toml_content = """[mod]
id = "thirdparty.nolocales"
version = "1.0.0"
axiom_api = 1
name = "Raw Default Name"
description = "Raw Default Description"
"""
    manifest = parse_manifest_string(toml_content)
    assert not manifest.locales

    assert manifest.localized_name("en") == "Raw Default Name"
    assert manifest.localized_name("fr") == "Raw Default Name"
    assert manifest.localized_name("zh") == "Raw Default Name"
    assert manifest.localized_description("ja") == "Raw Default Description"


def test_loader_registers_mod_locales_in_kernel_slot():
    """Loading a mod automatically contributes its locales into 'axiom.kernel:locales'."""
    reg = KernelRegistry()
    manifest, ctx, mod = load_mod_from_dir("mods/axiom.time", reg)

    contributions = reg.get_slot_contributions("axiom.kernel:locales")
    assert len(contributions) > 0

    # Ensure contributions include language mappings
    langs_contributed = {c[0] for c in contributions if isinstance(c, tuple) and len(c) == 2}
    for l in SUPPORTED_LANGUAGES:
        assert l in langs_contributed, f"Language '{l}' was not contributed to 'axiom.kernel:locales'."

    # Test integration with core.localization
    set_kernel_registry(reg)
    reload_translations()
    try:
        set_language("fr")
        assert tr("title") == "Système Temporel & Chroniqueur"

        set_language("en")
        assert tr("title") == "Time System & Chronicler"
    finally:
        set_kernel_registry(None)
        reload_translations()


def test_archived_axmod_preserves_and_loads_locales(tmp_path: Path):
    """Packaging a mod into .axmod preserves locales/ and load_manifest_from_archive loads them."""
    archive_path = pack_mod("mods/axiom.inventory", output_path=tmp_path / "axiom.inventory-test.axmod")
    assert archive_path.is_file()

    manifest = load_manifest_from_archive(archive_path)
    assert manifest.id == "axiom.inventory"
    assert len(manifest.locales) == 10

    assert manifest.localized_name("en") == "Emergent Nested Inventory"
    assert manifest.localized_name("fr") == "Inventaire Imbriqué Émergent"
    assert manifest.localized_name("ru") == "Вложенный Инвентарь"
    assert manifest.localized_name("zh") == "涌现式嵌套物品栏"
    assert manifest.localized_name("ja") == "階層型ネストインベントリ"
    assert manifest.localized_name("ko") == "창발적 중첩 인벤토리"


def test_official_mods_author_is_vanilla():
    """All official mods must declare author = 'Vanilla'."""
    for mod_id in OFFICIAL_MOD_IDS:
        manifest = parse_manifest_file(f"mods/{mod_id}/mod.toml")
        assert manifest.author == "Vanilla", f"Mod '{mod_id}' has author '{manifest.author}', expected 'Vanilla'."


def test_mod_manager_detail_labels_translated_in_all_10_languages():
    """Verify that all mod detail labels are translated in every supported language."""
    labels = [
        "mods_meta_category",
        "mods_meta_provides",
        "mods_meta_hooks_subscribed",
        "mods_meta_hooks",
        "mods_meta_none",
        "mods_meta_slots_contributed",
        "mods_meta_slots",
        "mods_meta_slots_provided",
        "mods_meta_patches",
        "mods_meta_dependencies",
        "mods_meta_python_deps",
        "mods_meta_type",
        "mods_type_archive",
        "mods_type_directory",
        "mods_meta_location",
        "mods_meta_author",
        "mods_author_unknown",
        "mods_meta_api_compat",
        "mods_api_compatible",
        "mods_no_description",
    ]

    for lang in SUPPORTED_LANGUAGES:
        set_language(lang)
        reload_translations()
        for label_key in labels:
            translated = tr(label_key)
            assert translated != label_key, f"Key '{label_key}' missing translation in language '{lang}'."
            assert len(translated.strip()) > 0
