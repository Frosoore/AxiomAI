"""axiom/kernel/dev.py

Mod Development Hot-Reload Mode (`axiom mod dev`).
Watches a mod directory for changes, cleans up registered hooks/slots/patches
via ModContext.cleanup() (Rule D11), revalidates mod.toml, and hot-reloads the Python module.
"""

from __future__ import annotations

from collections.abc import Callable
import importlib
import importlib.util
import os
from pathlib import Path
import sys
import time
from typing import Any

from axiom.config import AppConfig, load_config
from axiom.kernel.context import ModContext
from axiom.kernel.manifest import ManifestError, ModManifest, parse_manifest_file
from axiom.kernel.registry import KernelRegistry, SlotRule
from axiom.logger import logger


_EXCLUDED_PARTS = {"__pycache__", ".pytest_cache", ".git", ".DS_Store"}


def get_mod_tree_mtime(mod_dir: Path) -> float:
    """Return the maximum modification timestamp among relevant files in mod_dir."""
    max_mtime = 0.0
    for p in mod_dir.rglob("*"):
        if not p.is_file():
            continue
        if any(part in _EXCLUDED_PARTS for part in p.parts):
            continue
        try:
            m = p.stat().st_mtime
            if m > max_mtime:
                max_mtime = m
        except OSError:
            pass
    return max_mtime


def reload_mod_instance(
    mod_dir: Path,
    registry: KernelRegistry,
    current_ctx: ModContext | None = None,
    config: AppConfig | None = None,
) -> tuple[ModManifest, ModContext, Any]:
    """Clean up existing mod context and reload the mod afresh."""
    # 1. Clean up existing context if provided (Rule D11)
    if current_ctx is not None:
        try:
            current_ctx.cleanup()
        except Exception as err:
            logger.warning("[ModDev] Error during context cleanup: %s", err)

    # 2. Invalidate import caches & revalidate manifest
    importlib.invalidate_caches()
    manifest_file = mod_dir / "mod.toml"
    if not manifest_file.is_file():
        raise ManifestError(f"Missing mod.toml in {mod_dir}")

    manifest = parse_manifest_file(manifest_file)

    new_ctx = ModContext(manifest, registry, config)

    # Re-declare any slots provided by this mod (through the context: undone on cleanup)
    for slot_name, rule_str in getattr(manifest, "provides_slots", {}).items():
        try:
            rule = SlotRule(rule_str.lower())
        except ValueError:
            rule = SlotRule.COLLECT
        new_ctx.declare_slot(slot_name, rule)

    # 3. Reload module
    main_py = mod_dir / "main.py"
    module = None
    if main_py.is_file():
        module_name = f"axiom_mod_{manifest.id.replace('.', '_')}"
        spec = importlib.util.spec_from_file_location(
            module_name, main_py, submodule_search_locations=[str(mod_dir)]
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Failed to create spec for {main_py}")
        # Drop stale submodules so edited helper files are reloaded too.
        for name in [n for n in sys.modules if n == module_name or n.startswith(module_name + ".")]:
            sys.modules.pop(name, None)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
            if hasattr(module, "init") and callable(module.init):
                module.init(new_ctx)
        except BaseException:
            new_ctx.cleanup()  # a broken edit must not leave half a mod registered
            raise

    logger.info("[ModDev] Reloaded mod %s successfully.", manifest.id)
    return manifest, new_ctx, module


def poll_mod_once(
    mod_dir: Path | str,
    last_mtime: float,
    current_ctx: ModContext | None,
    registry: KernelRegistry,
    config: AppConfig | None = None,
) -> tuple[float, bool, ModContext | None]:
    """Check if mod files changed, and reload if so.

    Returns:
        (new_mtime, reloaded_bool, updated_context)
    """
    path = Path(mod_dir).resolve()
    current_mtime = get_mod_tree_mtime(path)

    if current_mtime <= last_mtime and last_mtime > 0:
        return last_mtime, False, current_ctx

    try:
        _, new_ctx, _ = reload_mod_instance(path, registry, current_ctx, config)
        return current_mtime, True, new_ctx
    except Exception as exc:
        logger.error("[ModDev] Failed to reload mod: %s", exc)
        raise


def watch_mod(
    mod_dir: Path | str,
    interval: float = 1.0,
    on_event: Callable[[str], None] = print,
    should_stop: Callable[[], bool] | None = None,
    registry: KernelRegistry | None = None,
) -> None:
    """Watch mod directory and hot-reload upon file save.

    Args:
        mod_dir: Directory containing mod.toml and main.py.
        interval: Polling frequency in seconds.
        on_event: Notification callback.
        should_stop: Optional predicate to terminate loop (useful for tests).
        registry: Optional custom KernelRegistry (creates fresh one if None).
    """
    path = Path(mod_dir).resolve()
    if not path.is_dir():
        raise FileNotFoundError(f"Mod directory does not exist: {path}")

    if registry is None:
        registry = KernelRegistry()

    config = load_config()
    current_ctx: ModContext | None = None
    last_mtime: float = 0.0
    first = True

    on_event(f"[ModDev] Watching mod directory: {path}")

    while True:
        if should_stop is not None and should_stop():
            if current_ctx is not None:
                current_ctx.cleanup()
            return

        try:
            new_mtime, reloaded, updated_ctx = poll_mod_once(
                path,
                last_mtime,
                current_ctx,
                registry,
                config,
            )
            if reloaded:
                current_ctx = updated_ctx
                last_mtime = new_mtime
                mod_id = current_ctx.mod_id if current_ctx else "unknown"
                if first:
                    on_event(f"[ModDev] Initialized mod '{mod_id}' successfully.")
                else:
                    on_event(f"[ModDev] Reloaded mod {mod_id} successfully.")
        except Exception as err:
            on_event(f"[ModDev] Error (awaiting fix): {err}")

        first = False
        time.sleep(interval)
