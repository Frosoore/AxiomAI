"""tests/test_mod_store_and_packaging.py

Comprehensive test suite for Phase 5:
- Decentralized store client & catalog search (axiom/kernel/store.py)
- SHA-256 cryptographic integrity verification (Rule §6.12 & ModIntegrityError)
- Python dependency verification (axiom/kernel/dependencies.py & Decision D-7)
- PyPI export sanitation & headless purity (export_engine.py & Decision D-8)
- Store CLI subcommands and Web API endpoints
"""

from __future__ import annotations

import io
import json
from pathlib import Path
import shutil
import tempfile
import pytest

from axiom.cli.main import main as cli_main
from axiom.cli.mods_cmd import pack_mod
from axiom.config import AppConfig, load_config
from axiom.kernel.dependencies import (
    check_mod_python_dependencies,
    check_python_requirement,
)
from axiom.kernel.loader import load_mod_from_dir
from axiom.kernel.manifest import parse_manifest_file, parse_manifest_string
from axiom.kernel.registry import KernelRegistry
from axiom.kernel.scaffold import scaffold_mod
from axiom.kernel.store import (
    ModIntegrityError,
    StoreError,
    StoreModEntry,
    calculate_sha256,
    fetch_store_index,
    install_mod_from_store,
    publish_mod_to_store_spec,
    search_store,
)
from export_engine import ENGINE_DIR, check_headless, export, read_version


# ---------------------------------------------------------------------------
# 1. Store Index & Catalog Search Tests
# ---------------------------------------------------------------------------


def test_store_index_fetching_and_search(tmp_path: Path) -> None:
    """Verify fetching store index from a JSON file and performing multi-attribute search."""
    index_file = tmp_path / "test_store_index.json"
    mock_data = {
        "version": 1,
        "repository_name": "Axiom Test Store",
        "mods": [
            {
                "id": "community.alchemy",
                "version": "1.2.0",
                "axiom_api": 1,
                "name": "Grand Alchemy",
                "description": "Potion crafting and reagent gathering.",
                "author": "AlchemistDave",
                "download_url": "https://example.com/alchemy.axmod",
                "sha256": "abcdef1234567890",
                "provides": ["alchemy_system"],
            },
            {
                "id": "community.stealth",
                "version": "0.5.0",
                "axiom_api": 1,
                "name": "Shadow Arts",
                "description": "Sneaking mechanics and vision cones.",
                "author": "NinjaBob",
                "download_url": "https://example.com/stealth.axmod",
                "sha256": "123456abcdef7890",
                "provides": ["stealth_system"],
            },
        ],
    }
    index_file.write_text(json.dumps(mock_data), encoding="utf-8")

    entries = fetch_store_index(repo_url=index_file, cache_path=tmp_path / "cache.json", refresh=True)
    assert len(entries) == 2
    assert entries[0].id == "community.alchemy"
    assert entries[1].author == "NinjaBob"

    # Search by name keyword
    results_alchemy = search_store("potion", entries=entries)
    assert len(results_alchemy) == 1
    assert results_alchemy[0].id == "community.alchemy"

    # Search by author
    results_author = search_store("ninjabob", entries=entries)
    assert len(results_author) == 1
    assert results_author[0].id == "community.stealth"

    # Search by provides tag
    results_tag = search_store("alchemy_system", entries=entries)
    assert len(results_tag) == 1
    assert results_tag[0].id == "community.alchemy"

    # Search with empty query returns all
    assert len(search_store("", entries=entries)) == 2


# ---------------------------------------------------------------------------
# 2. Cryptographic Integrity & Installation Tests (Rule §6.12)
# ---------------------------------------------------------------------------


def test_mod_install_with_valid_sha256(tmp_path: Path) -> None:
    """Verify downloading, SHA-256 verifying, and installing an authentic .axmod package."""
    # 1. Scaffold and pack a mod
    src_mod = tmp_path / "src_mod"
    scaffold_mod("community.herbalism", mod_type="hook", target_dir=src_mod)
    archive_path = pack_mod(src_mod, output_path=tmp_path / "herbalism.axmod")
    assert archive_path.is_file()

    # 2. Create store index with exact SHA-256
    index_file = tmp_path / "store.json"
    spec = publish_mod_to_store_spec(archive_path, download_url=f"file://{archive_path}", output_json=index_file)
    assert spec["id"] == "community.herbalism"
    assert spec["sha256"] == calculate_sha256(archive_path)

    # 3. Install from store into a target mods directory
    target_mods = tmp_path / "installed_mods"
    installed_dir = install_mod_from_store(
        mod_id="community.herbalism",
        dest_dir=target_mods,
        repo_url=index_file,
        enable=True,
    )

    assert installed_dir == target_mods / "community.herbalism"
    assert (installed_dir / "mod.toml").is_file()
    assert (installed_dir / "main.py").is_file()

    manifest = parse_manifest_file(installed_dir / "mod.toml")
    assert manifest.id == "community.herbalism"


def test_mod_install_fails_on_corrupted_sha256(tmp_path: Path) -> None:
    """Rule §6.12: Divergence in SHA-256 digest must raise ModIntegrityError and abort."""
    src_mod = tmp_path / "src_mod_corrupt"
    scaffold_mod("community.traps", mod_type="hook", target_dir=src_mod)
    archive_path = pack_mod(src_mod, output_path=tmp_path / "traps.axmod")

    # Tamper with archive content
    archive_bytes = bytearray(archive_path.read_bytes())
    archive_bytes[10] ^= 0xFF
    corrupted_path = tmp_path / "corrupted_traps.axmod"
    corrupted_path.write_bytes(archive_bytes)

    # Point index to corrupted file while keeping original SHA-256
    real_sha = calculate_sha256(archive_path)
    index_file = tmp_path / "store_bad.json"
    bad_data = {
        "version": 1,
        "repository_name": "Bad Store",
        "mods": [
            {
                "id": "community.traps",
                "version": "0.1.0",
                "axiom_api": 1,
                "name": "Traps Mod",
                "download_url": f"file://{corrupted_path}",
                "sha256": real_sha,  # Digest of intact archive, mismatched with corrupted_path
            }
        ],
    }
    index_file.write_text(json.dumps(bad_data), encoding="utf-8")

    target_mods = tmp_path / "installed_mods"
    with pytest.raises(ModIntegrityError, match="Cryptographic integrity verification failed"):
        install_mod_from_store("community.traps", dest_dir=target_mods, repo_url=index_file)

    # Destination folder must not have been created
    assert not (target_mods / "community.traps").exists()


# ---------------------------------------------------------------------------
# 3. Python Package Dependency Verification Tests (Decision D-7)
# ---------------------------------------------------------------------------


def test_python_requirement_checking() -> None:
    """Verify detection of installed and missing Python packages."""
    # Packages known to be installed in .venv
    ok_req, msg_req = check_python_requirement("requests>=2.0.0")
    assert ok_req, f"requests should be satisfied: {msg_req}"

    ok_toml, msg_toml = check_python_requirement("tomlkit")
    assert ok_toml, f"tomlkit should be satisfied: {msg_toml}"

    # Non-existent package
    ok_fake, msg_fake = check_python_requirement("axiom_phantom_pkg_9999>=1.0.0")
    assert not ok_fake
    assert "not installed" in str(msg_fake).lower()


def test_mod_loader_skips_mod_with_missing_python_deps(tmp_path: Path) -> None:
    """Verify loader logs warning and skips mod with missing python deps without crashing."""
    dest = tmp_path / "community.heavy_math"
    dest.mkdir(parents=True)

    toml_content = """[mod]
id = "community.heavy_math"
version = "0.1.0"
axiom_api = 1
name = "Heavy Math"

[python]
requires = ["axiom_completely_fictional_package_xyz>=2.0.0"]
"""
    (dest / "mod.toml").write_text(toml_content, encoding="utf-8")
    (dest / "main.py").write_text("def init(ctx): pass\n", encoding="utf-8")

    manifest = parse_manifest_file(dest / "mod.toml")
    missing = check_mod_python_dependencies(manifest)
    assert len(missing) == 1
    assert "axiom_completely_fictional_package_xyz" in missing[0]

    # Test through runtime loader
    registry = KernelRegistry()
    cfg = AppConfig()
    m, ctx, mod = load_mod_from_dir(dest, registry, cfg)
    assert m.id == "community.heavy_math"
    assert ctx is None  # Skipped!
    assert mod is None


# ---------------------------------------------------------------------------
# 4. PyPI Packaging & Headless Purity Tests (Decision D-8)
# ---------------------------------------------------------------------------


def test_engine_headless_purity() -> None:
    """Decision D-8: axiom/ must have zero forbidden imports to app/UI modules."""
    violations = check_headless(ENGINE_DIR)
    assert violations == [], f"Found forbidden imports in engine: {violations}"


def test_export_engine_script(tmp_path: Path) -> None:
    """Verify export_engine copies only axiom/ and excludes mods/, ui/, web/, universes/."""
    export_dest = tmp_path / "axiomai_engine_export"
    version_tuple = read_version()
    version_str = ".".join(str(p) for p in version_tuple)
    assert version_str == "1.0.0"

    export(export_dest, version_str, force=True)

    assert export_dest.is_dir()
    assert (export_dest / "axiom").is_dir()
    assert (export_dest / "axiom" / "kernel").is_dir()
    assert (export_dest / "axiom" / "testing").is_dir()
    assert (export_dest / "pyproject.toml").is_file()
    assert (export_dest / "NOTICE").is_file()
    assert (export_dest / "LICENSE").is_file()
    assert (export_dest / "README.md").is_file()

    # Strict exclusions
    assert not (export_dest / "mods").exists()
    assert not (export_dest / "ui").exists()
    assert not (export_dest / "web").exists()
    assert not (export_dest / "workers").exists()
    assert not (export_dest / "universes").exists()


# ---------------------------------------------------------------------------
# 5. CLI & Web API Store Integration Tests
# ---------------------------------------------------------------------------


def test_cli_mods_search_and_install(tmp_path: Path, capsys) -> None:
    """Test `axiom mods search` and `axiom mods install` CLI commands."""
    # Scaffold and publish a test mod
    mod_src = tmp_path / "cli_store_src"
    scaffold_mod("community.lockpicking", target_dir=mod_src)
    archive = pack_mod(mod_src, output_path=tmp_path / "lockpicking.axmod")

    index_file = tmp_path / "cli_store.json"
    publish_mod_to_store_spec(archive, download_url=f"file://{archive}", output_json=index_file)

    # 1. Search command
    code = cli_main(["mods", "search", "lockpicking", "--repo", str(index_file)])
    assert code == 0
    captured = capsys.readouterr()
    assert "community.lockpicking" in captured.out

    # 2. Install command
    installed_target = tmp_path / "cli_installed_mods"
    install_code = cli_main(
        [
            "mods",
            "install",
            "community.lockpicking",
            "--dest",
            str(installed_target),
            "--repo",
            str(index_file),
        ]
    )
    assert install_code == 0
    captured_inst = capsys.readouterr()
    assert "SUCCESS: Mod 'community.lockpicking' verified and installed" in captured_inst.out
    assert (installed_target / "community.lockpicking" / "mod.toml").is_file()


def test_web_api_store_endpoints(tmp_path: Path) -> None:
    """Test Web API endpoints GET /api/store/search and POST /api/store/install."""
    from main_web import AxiomWebHandler

    mod_src = tmp_path / "web_store_src"
    scaffold_mod("community.testpack", target_dir=mod_src)
    archive = pack_mod(mod_src, output_path=tmp_path / "testpack.axmod")

    index_file = tmp_path / "web_store.json"
    publish_mod_to_store_spec(archive, download_url=f"file://{archive}", output_json=index_file)

    handler = AxiomWebHandler.__new__(AxiomWebHandler)
    handler.rfile = io.BytesIO()
    handler.wfile = io.BytesIO()
    handler.headers = {"Host": "127.0.0.1"}

    sent_data = []
    handler.send_json = lambda data, code=200: sent_data.append((code, data))
    handler.send_error_json = lambda code, msg: sent_data.append((code, msg))

    # 1. GET /api/store/search
    handler.handle_api_get("/api/store/search", f"q=testpack&repo={index_file}")
    assert len(sent_data) == 1
    code, items = sent_data[0]
    assert code == 200
    assert len(items) == 1
    assert items[0]["id"] == "community.testpack"

    # 2. POST /api/store/install
    sent_data.clear()
    installed_target = tmp_path / "web_installed_mods"
    handler.handle_api_post(
        "/api/store/install",
        {
            "mod_id": "community.testpack",
            "repo": str(index_file),
            "dest": str(installed_target),
        },
    )
    assert len(sent_data) == 1
    code2, resp2 = sent_data[0]
    assert code2 == 200
    assert resp2["status"] == "success"
