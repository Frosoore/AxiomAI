"""axiom/kernel/loader.py

Runtime loader for Axiom AI mods (.axmod archives or unpacked directories).
Instantiates ModContext and calls the mod entry point `init(ctx)`.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
from typing import Any
import zipfile

from axiom.config import AppConfig
from axiom.kernel.context import ModContext
from axiom.kernel.manifest import (
    ManifestError,
    ModManifest,
    load_manifest,
    load_manifest_from_archive,
    parse_manifest_file,
)
from axiom.kernel.registry import KernelRegistry
from axiom.logger import logger

try:
    importlib.import_module("mods")
except Exception:
    pass


class ModLoadError(Exception):
    """Raised when a mod cannot be loaded or initialized."""


_SAFE_MODE: bool = False


def set_safe_mode(enabled: bool) -> None:
    """Toggle kernel safe mode. In safe mode, third-party mods are disabled."""
    global _SAFE_MODE
    _SAFE_MODE = bool(enabled)


def is_safe_mode() -> bool:
    """Return whether safe mode is active."""
    return _SAFE_MODE


def is_official_mod(mod_id: str) -> bool:
    """Check if a mod ID belongs to official platform namespaces (axiom.*, core.*)."""
    return mod_id.startswith("axiom.") or mod_id.startswith("core.")


def is_mod_enabled(mod_id: str, config: AppConfig | None = None) -> bool:
    """Check if a mod is enabled considering safe-mode and mod_settings."""
    if is_safe_mode() and not is_official_mod(mod_id):
        return False
    if config is not None and hasattr(config, "mod_settings"):
        settings = config.mod_settings.get(mod_id, {})
        if isinstance(settings, dict) and not settings.get("enabled", True):
            return False
    return True


def load_mod_from_dir(
    dir_path: Path | str,
    registry: KernelRegistry,
    config: AppConfig | None = None,
) -> tuple[ModManifest, ModContext | None, Any]:
    """Load and initialize a mod from an unpacked directory."""
    path = Path(dir_path).resolve()
    if not path.is_dir():
        raise ModLoadError(f"Mod directory not found: {path}")

    manifest_file = path / "mod.toml"
    if not manifest_file.is_file():
        raise ModLoadError(f"Missing mod.toml in {path}")

    manifest = parse_manifest_file(manifest_file)
    if not is_mod_enabled(manifest.id, config):
        logger.info("Mod '%s' is disabled (safe_mode=%s), skipping.", manifest.id, is_safe_mode())
        return manifest, None, None

    from axiom.kernel.dependencies import check_mod_python_dependencies
    missing_deps = check_mod_python_dependencies(manifest)
    if missing_deps:
        for msg in missing_deps:
            logger.warning("[PythonDeps] %s", msg)
        return manifest, None, None

    from axiom.kernel.registry import SlotRule

    for slot_name, rule_str in getattr(manifest, "provides_slots", {}).items():
        try:
            rule = SlotRule(rule_str.lower())
        except ValueError:
            rule = SlotRule.COLLECT
        registry.declare_slot(slot_name, rule)

    mod_ctx = ModContext(manifest, registry, config)

    main_py = path / "main.py"
    module = None
    if main_py.is_file():
        module_name = f"axiom_mod_{manifest.id.replace('.', '_')}"
        spec = importlib.util.spec_from_file_location(module_name, main_py)
        if spec is None or spec.loader is None:
            raise ModLoadError(f"Failed to create module spec for {main_py}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as err:
            raise ModLoadError(f"Failed to execute mod '{manifest.id}' code: {err}") from err

        if hasattr(module, "init") and callable(module.init):
            try:
                module.init(mod_ctx)
            except Exception as err:
                raise ModLoadError(f"Error during init() of mod '{manifest.id}': {err}") from err

    logger.info("Loaded mod '%s' (v%s) from directory %s", manifest.id, manifest.version, path)
    return manifest, mod_ctx, module


def load_mod_from_archive(
    archive_path: Path | str,
    registry: KernelRegistry,
    config: AppConfig | None = None,
) -> tuple[ModManifest, ModContext, Any]:
    """Load and initialize a mod from a .axmod (ZIP) archive without on-disk extraction."""
    path = Path(archive_path).resolve()
    if not path.is_file():
        raise ModLoadError(f"Mod archive not found: {path}")

    manifest = load_manifest_from_archive(path)
    if not is_mod_enabled(manifest.id, config):
        logger.info("Mod '%s' is disabled (safe_mode=%s), skipping.", manifest.id, is_safe_mode())
        return manifest, None, None

    from axiom.kernel.dependencies import check_mod_python_dependencies
    missing_deps = check_mod_python_dependencies(manifest)
    if missing_deps:
        for msg in missing_deps:
            logger.warning("[PythonDeps] %s", msg)
        return manifest, None, None

    from axiom.kernel.registry import SlotRule

    for slot_name, rule_str in getattr(manifest, "provides_slots", {}).items():
        try:
            rule = SlotRule(rule_str.lower())
        except ValueError:
            rule = SlotRule.COLLECT
        registry.declare_slot(slot_name, rule)

    mod_ctx = ModContext(manifest, registry, config)

    module = None
    with zipfile.ZipFile(path, "r") as zf:
        if "main.py" in zf.namelist():
            try:
                code_bytes = zf.read("main.py")
                code_str = code_bytes.decode("utf-8")
            except Exception as err:
                raise ModLoadError(f"Failed to read main.py from archive {path}: {err}") from err

            module_name = f"axiom_mod_{manifest.id.replace('.', '_')}"
            module = types.ModuleType(module_name)
            module.__file__ = f"{path}:main.py"
            module.__loader__ = None  # type: ignore
            sys.modules[module_name] = module

            try:
                code_obj = compile(code_str, f"{path}:main.py", "exec")
                exec(code_obj, module.__dict__)
            except Exception as err:
                raise ModLoadError(f"Failed to execute mod '{manifest.id}' code from archive: {err}") from err

            if hasattr(module, "init") and callable(module.init):
                try:
                    module.init(mod_ctx)
                except Exception as err:
                    raise ModLoadError(f"Error during init() of mod '{manifest.id}': {err}") from err

    logger.info("Loaded mod '%s' (v%s) from archive %s", manifest.id, manifest.version, path)
    return manifest, mod_ctx, module


def load_mod(
    path: Path | str,
    registry: KernelRegistry,
    config: AppConfig | None = None,
) -> tuple[ModManifest, ModContext, Any]:
    """Load and initialize a mod from either a directory or a .axmod archive."""
    p = Path(path).resolve()
    if p.is_dir():
        return load_mod_from_dir(p, registry, config)
    elif p.is_file() and p.suffix in (".axmod", ".zip"):
        return load_mod_from_archive(p, registry, config)
    raise ModLoadError(f"Invalid mod path (must be directory or .axmod archive): {path}")


def bootstrap_all_mods(
    registry: KernelRegistry | None = None,
    config: AppConfig | None = None,
) -> KernelRegistry:
    """Bootstrap all enabled mods into the active KernelRegistry according to topological load order.

    Discovers installed mods from standard directories, filters out disabled mods,
    resolves dependency graph and load order, and initializes each mod with ModContext.
    """
    from axiom.cli.mods_cmd import discover_installed_mods
    from axiom.config import load_config
    from axiom.kernel.registry import KernelRegistry, set_active_registry
    from axiom.kernel.resolver import resolve_load_order

    if config is None:
        config = load_config()

    if registry is None:
        registry = KernelRegistry()
    set_active_registry(registry)

    try:
        installed = discover_installed_mods()
    except Exception as err:
        logger.warning("Error discovering installed mods during bootstrap: %s", err)
        installed = []

    manifest_map = {m.id: m for m, path in installed if is_mod_enabled(m.id, config)}
    path_map = {m.id: path for m, path in installed}

    try:
        report = resolve_load_order(manifest_map)
    except Exception as err:
        logger.error("Dependency resolution failed during bootstrap: %s", err)
        return registry

    for mod_id in report.load_order:
        path = path_map.get(mod_id)
        if path:
            try:
                load_mod(path, registry, config)
            except Exception as err:
                logger.error("Failed to load mod '%s': %s", mod_id, err, exc_info=True)

    return registry

