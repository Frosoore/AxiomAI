"""tests/test_kernel_loader.py

Unit test suite for Phase 1: Mod Loader, Manifest Parser, Topological Resolver,
Kernel Registry exception isolation, and ModContext lifecycle.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
import pytest

from axiom.config import AppConfig
from axiom.kernel import (
    ConflictError,
    CyclicDependencyError,
    KernelRegistry,
    ManifestError,
    ModContext,
    RegistryError,
    SlotRule,
    load_manifest,
    load_manifest_from_archive,
    parse_manifest_string,
    resolve_load_order,
)


def _create_fake_axmod(path: Path, manifest_content: str, extra_files: dict[str, str] | None = None) -> Path:
    """Helper to create a temporary .axmod zip archive."""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mod.toml", manifest_content)
        if extra_files:
            for fname, fcontent in extra_files.items():
                zf.writestr(fname, fcontent)
    return path


class TestManifestParser:
    """Tests for mod.toml declarative parsing and validation."""

    def test_parse_valid_manifest(self) -> None:
        toml = """
        [mod]
        id = "comm.hunger"
        version = "1.2.0"
        axiom_api = 1
        name = "Hunger System"
        description = "Adds hunger and metabolism."
        author = "AxiomDev"

        [dependencies]
        "axiom.turn" = ">=1.0"
        "axiom.ui" = { version = ">=2.0", optional = true }

        [ordering]
        after = ["axiom.world"]
        before = ["comm.cooking"]
        conflicts = ["other.hunger"]
        provides = ["virtual.metabolism"]

        [contributes]
        hooks = ["axiom.turn:after_tick"]
        slots = ["axiom.turn:stats_view"]
        patches = []
        """
        manifest = parse_manifest_string(toml)
        assert manifest.id == "comm.hunger"
        assert manifest.version == "1.2.0"
        assert manifest.axiom_api == 1
        assert manifest.name == "Hunger System"
        assert len(manifest.dependencies) == 2
        assert manifest.dependencies["axiom.turn"].optional is False
        assert manifest.dependencies["axiom.ui"].optional is True
        assert manifest.ordering.after == ["axiom.world"]
        assert manifest.ordering.before == ["comm.cooking"]
        assert manifest.ordering.conflicts == ["other.hunger"]
        assert manifest.ordering.provides == ["virtual.metabolism"]
        assert manifest.contributes.hooks == ["axiom.turn:after_tick"]

    def test_parse_invalid_mod_id(self) -> None:
        # Must be namespaced with a dot
        toml = """
        [mod]
        id = "simpleid"
        version = "1.0.0"
        axiom_api = 1
        """
        with pytest.raises(ManifestError, match="namespaced"):
            parse_manifest_string(toml)

    def test_parse_invalid_semver(self) -> None:
        toml = """
        [mod]
        id = "comm.test"
        version = "v1-beta"
        axiom_api = 1
        """
        with pytest.raises(ManifestError, match="SemVer"):
            parse_manifest_string(toml)

    def test_parse_missing_required_table(self) -> None:
        with pytest.raises(ManifestError, match=r"\[mod\]"):
            parse_manifest_string("title = 'orphan'")

    def test_load_manifest_from_axmod_archive(self, tmp_path: Path) -> None:
        archive_path = tmp_path / "test.axmod"
        toml = """
        [mod]
        id = "core.world"
        version = "2.0.0"
        axiom_api = 1
        name = "World Core"
        """
        _create_fake_axmod(archive_path, toml, {"main.py": "print('malicious code never executed')"})

        manifest = load_manifest_from_archive(archive_path)
        assert manifest.id == "core.world"
        assert manifest.version == "2.0.0"

        # Also polymorphic load_manifest
        polymorphic = load_manifest(archive_path)
        assert polymorphic.id == "core.world"

    def test_load_manifest_missing_mod_toml_in_archive(self, tmp_path: Path) -> None:
        archive_path = tmp_path / "empty.axmod"
        with zipfile.ZipFile(archive_path, "w") as zf:
            zf.writestr("dummy.txt", "hello")

        with pytest.raises(ManifestError, match="does not contain 'mod.toml'"):
            load_manifest_from_archive(archive_path)


class TestLoadOrderResolver:
    """Tests for DAG topological sorting, cycle detection, and dependency resolution."""

    def test_stable_topological_sort_with_user_preference(self) -> None:
        m_turn = parse_manifest_string("""
        [mod]
        id = "core.turn"
        version = "1.0.0"
        axiom_api = 1
        """)
        m_world = parse_manifest_string("""
        [mod]
        id = "core.world"
        version = "1.0.0"
        axiom_api = 1
        [ordering]
        before = ["core.turn"]
        """)
        m_magic = parse_manifest_string("""
        [mod]
        id = "comm.magic"
        version = "1.0.0"
        axiom_api = 1
        [dependencies]
        "core.turn" = ">=1.0"
        """)
        m_quests = parse_manifest_string("""
        [mod]
        id = "comm.quests"
        version = "1.0.0"
        axiom_api = 1
        [dependencies]
        "core.turn" = ">=1.0"
        """)

        manifests = {
            "comm.magic": m_magic,
            "core.turn": m_turn,
            "comm.quests": m_quests,
            "core.world": m_world,
        }

        # User prefers quests before magic
        report = resolve_load_order(manifests, user_order=["comm.quests", "comm.magic"])
        assert report.load_order == ["core.world", "core.turn", "comm.quests", "comm.magic"]

        # User prefers magic before quests
        report2 = resolve_load_order(manifests, user_order=["comm.magic", "comm.quests"])
        assert report2.load_order == ["core.world", "core.turn", "comm.magic", "comm.quests"]

    def test_cyclic_dependency_sets_cycle_aside_with_reason(self) -> None:
        """1-NOYAU B1: a cycle no longer empties the modpack; the cycle is reported."""
        mA = parse_manifest_string("""
        [mod]
        id = "mod.a"
        version = "1.0.0"
        axiom_api = 1
        [dependencies]
        "mod.b" = ">=1.0"
        """)
        mB = parse_manifest_string("""
        [mod]
        id = "mod.b"
        version = "1.0.0"
        axiom_api = 1
        [dependencies]
        "mod.c" = ">=1.0"
        """)
        mC = parse_manifest_string("""
        [mod]
        id = "mod.c"
        version = "1.0.0"
        axiom_api = 1
        [ordering]
        after = ["mod.a"]
        """)

        m_free = parse_manifest_string("""
        [mod]
        id = "mod.free"
        version = "1.0.0"
        axiom_api = 1
        """)

        manifests = {"mod.a": mA, "mod.b": mB, "mod.c": mC, "mod.free": m_free}
        report = resolve_load_order(manifests)

        assert report.load_order == ["mod.free"]
        for mod_id in ("mod.a", "mod.b", "mod.c"):
            err_msg = report.disabled_mods[mod_id]
            assert "Cyclic dependency detected" in err_msg
            assert "mod.a" in err_msg and "mod.b" in err_msg and "mod.c" in err_msg
        assert report.cycles

    def test_missing_mandatory_dependency_prunes_dependent_mod(self) -> None:
        mA = parse_manifest_string("""
        [mod]
        id = "mod.lonely"
        version = "1.0.0"
        axiom_api = 1
        [dependencies]
        "missing.parent" = ">=1.0"
        """)
        mValid = parse_manifest_string("""
        [mod]
        id = "mod.independent"
        version = "1.0.0"
        axiom_api = 1
        """)

        manifests = {"mod.lonely": mA, "mod.independent": mValid}
        report = resolve_load_order(manifests)

        assert "mod.independent" in report.load_order
        assert "mod.lonely" not in report.load_order
        assert "mod.lonely" in report.disabled_mods
        assert "missing.parent" in report.disabled_mods["mod.lonely"]

    def test_direct_conflict_sets_loser_aside(self) -> None:
        """1-NOYAU B1/I6: a conflict disables only the loser (by user order), not everything."""
        mA = parse_manifest_string("""
        [mod]
        id = "comm.hunger_a"
        version = "1.0.0"
        axiom_api = 1
        [ordering]
        conflicts = ["comm.hunger_b"]
        """)
        mB = parse_manifest_string("""
        [mod]
        id = "comm.hunger_b"
        version = "1.0.0"
        axiom_api = 1
        """)

        manifests = {"comm.hunger_a": mA, "comm.hunger_b": mB}
        report = resolve_load_order(manifests)
        # Default order is alphabetical: hunger_a wins
        assert report.load_order == ["comm.hunger_a"]
        assert "Conflicts with 'comm.hunger_a'" in report.disabled_mods["comm.hunger_b"]
        assert report.conflicts == [("comm.hunger_b", "comm.hunger_a", "'comm.hunger_a' declares a conflict with 'comm.hunger_b'")]

        # The user order decides the winner
        report2 = resolve_load_order(manifests, user_order=["comm.hunger_b"])
        assert report2.load_order == ["comm.hunger_b"]
        assert "comm.hunger_a" in report2.disabled_mods


class TestKernelRegistryAndModContext:
    """Tests for exception isolation and ModContext lifecycle unregistration."""

    def test_hook_exception_isolation(self) -> None:
        """A faulty mod callback must not halt execution or crash the kernel."""
        registry = KernelRegistry()
        executed: list[str] = []

        def failing_hook() -> None:
            raise RuntimeError("Fatal mod crash simulated")

        def healthy_hook() -> str:
            executed.append("healthy")
            return "ok"

        registry.add_hook("turn:step", "faulty.mod", failing_hook)
        registry.add_hook("turn:step", "healthy.mod", healthy_hook)

        # Invocation should not raise
        results = registry.invoke_hook("turn:step")
        assert executed == ["healthy"]
        assert results == ["ok"]

    def test_mod_context_cleanup_unregistration(self) -> None:
        """Rule D11: ModContext.cleanup() must remove all hooks and slot contributions."""
        registry = KernelRegistry()
        registry.declare_slot("ui:toolbar", SlotRule.COLLECT)

        app_config = AppConfig(mod_settings={"comm.weather": {"rain": True}})
        ctx = ModContext("comm.weather", registry, app_config)

        # Check config access
        assert ctx.config == {"rain": True}

        # Register hook and slot
        hook_called = False
        def on_weather() -> None:
            nonlocal hook_called
            hook_called = True

        ctx.register_hook("weather:tick", on_weather)
        ctx.contribute_slot("ui:toolbar", "WeatherWidget")

        # Verify active
        registry.invoke_hook("weather:tick")
        assert hook_called is True
        assert registry.get_slot("ui:toolbar") == ["WeatherWidget"]

        # Call cleanup
        ctx.cleanup()

        # Verify hook is gone
        hook_called = False
        registry.invoke_hook("weather:tick")
        assert hook_called is False

        # Verify slot contribution is gone
        assert registry.get_slot("ui:toolbar") == []

    def test_exclusive_slot_rule(self) -> None:
        """1-NOYAU I6: every candidate is kept, the first in mod order wins, conflict visible."""
        registry = KernelRegistry()
        registry.declare_slot("core:primary_audio", SlotRule.EXCLUSIVE)

        registry.add_to_slot("core:primary_audio", "mod.audio1", "AudioEngine1")
        assert registry.get_slot("core:primary_audio") == "AudioEngine1"

        # No RegistryError any more: the second mod is a candidate
        registry.add_to_slot("core:primary_audio", "mod.audio2", "AudioEngine2")
        assert registry.get_slot("core:primary_audio") == "AudioEngine1"
        assert registry.get_slot_conflicts() == {"core:primary_audio": ["mod.audio1", "mod.audio2"]}

        # The user order (load order) designates the winner
        registry.set_mod_order(["mod.audio2", "mod.audio1"])
        assert registry.get_slot("core:primary_audio") == "AudioEngine2"
