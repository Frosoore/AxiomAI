"""axiom/kernel/loader.py

Runtime loader for Axiom AI mods (.axmod archives or unpacked directories).
Instantiates ModContext and calls the mod entry point `init(ctx)`.

Main entry points:
- `discover_mods()`: installed mods, from the official mods folder (next to the
  installation) and the user mods folder (`axiom.paths.get_mods_dir()`), never from
  the current directory;
- `plan_modpack()`: what would load and why the rest would not, computed from the
  manifests without running any mod code (D13) — used by `axiom mods list`;
- `bootstrap_all_mods()`: loads a modpack into a registry and records the real status
  of every mod (`registry.load_state`);
- `get_kernel_registry()`: the process-wide registry, bootstrapped once (D-4);
- `disable_mod_hot()`: disables one loaded mod (at once, or "at next launch", D-5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import sys
import threading
from typing import Any
import zipfile

from axiom.config import AppConfig
from axiom.kernel.api import KERNEL_API
from axiom.kernel.context import ModContext
from axiom.kernel.importer import register_mod_root
from axiom.kernel.manifest import (
    ManifestError,
    ModManifest,
    load_manifest_from_archive,
    parse_manifest_file,
)
from axiom.kernel.registry import KernelRegistry, SlotRule
from axiom.logger import logger


class ModLoadError(Exception):
    """Raised when a mod cannot be loaded or initialized."""


_SAFE_MODE: bool = False


def set_safe_mode(enabled: bool) -> None:
    """Toggle kernel safe mode (§4.1, owner decision 2026-10-03): only the mods shipped
    with the installation that declare `[mod] safe_mode = true` are loaded — the
    interfaces and the minimal chat — whatever the user's choices. Nothing else."""
    global _SAFE_MODE
    _SAFE_MODE = bool(enabled)


def is_safe_mode() -> bool:
    """Return whether safe mode is active."""
    return _SAFE_MODE


def is_official_mod(mod_id: str) -> bool:
    """Deprecated: a name prefix does not make a mod official and grants nothing.

    Kept for backward compatibility of imports; no kernel decision uses it any more (D2).
    """
    return mod_id.startswith("axiom.") or mod_id.startswith("core.")


def get_user_mod_order(config: AppConfig | None) -> list[str]:
    """User load order (§8), stored in the mods config: mod_settings["axiom.kernel"]["mod_order"]
    (a top-level mod_settings["mod_order"] list is accepted too)."""
    if config is None or not isinstance(getattr(config, "mod_settings", None), dict):
        return []
    section = config.mod_settings.get("axiom.kernel")
    order = section.get("mod_order") if isinstance(section, dict) else None
    if order is None:
        order = config.mod_settings.get("mod_order")
    if isinstance(order, list):
        return [str(m) for m in order]
    return []


def set_user_mod_order(config: AppConfig, order: list[str]) -> None:
    """Store the user load order in the mods config (caller saves the config)."""
    config.mod_settings.setdefault("axiom.kernel", {})["mod_order"] = list(order)


# Ids of discovered mods whose manifest says `[mod] enabled_by_default = false`
# (example / opt-in mods): off until the user enables them explicitly.
_DEFAULT_DISABLED: set[str] = set()


# Ids of discovered mods allowed in safe mode (shipped with the installation and
# declaring `[mod] safe_mode = true`).
_SAFE_MODE_ELIGIBLE: set[str] = set()

SAFE_MODE_REASON = (
    "Safe mode: only the interfaces, the AI providers and the minimal chat shipped with Axiom are loaded."
)


def is_safe_mode_eligible(manifest: ModManifest, path: Path | None) -> bool:
    """`[mod] safe_mode = true` honoured only for a mod of the official folder: a third-party
    mod cannot put itself in the recovery mode meant to get away from it."""
    mod_section = manifest.raw_data.get("mod", {}) if isinstance(manifest.raw_data, dict) else {}
    if not (isinstance(mod_section, dict) and mod_section.get("safe_mode") is True):
        return False
    if path is None:
        return False
    return Path(path).resolve().parent == get_official_mods_dir()


def is_enabled_by_default(manifest: ModManifest) -> bool:
    """Manifest field `[mod] enabled_by_default` (default true)."""
    mod_section = manifest.raw_data.get("mod", {}) if isinstance(manifest.raw_data, dict) else {}
    return bool(mod_section.get("enabled_by_default", True)) if isinstance(mod_section, dict) else True


def is_mod_enabled(
    mod_id: str,
    config: AppConfig | None = None,
    manifest: ModManifest | None = None,
) -> bool:
    """Check if a mod is enabled by the user (and not in safe mode).

    This is the user's choice only; the real status (dependencies, conflicts,
    API, faults...) is given by `get_mod_status()` / `plan_modpack()`. Without an
    explicit choice, a mod declared `enabled_by_default = false` is off.
    """
    if is_safe_mode():
        return mod_id in _SAFE_MODE_ELIGIBLE
    if config is not None:
        if hasattr(config, "disabled_mods") and getattr(config, "disabled_mods") and mod_id in config.disabled_mods:
            return False
        if hasattr(config, "mod_settings") and isinstance(config.mod_settings, dict):
            settings = config.mod_settings.get(mod_id, {})
            if isinstance(settings, dict) and "enabled" in settings:
                return bool(settings["enabled"])
    if manifest is not None:
        return is_enabled_by_default(manifest)
    return mod_id not in _DEFAULT_DISABLED


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def get_official_mods_dir() -> Path:
    """Folder of the mods shipped with the installation (the repository `mods/`)."""
    env = os.environ.get("AXIOM_OFFICIAL_MODS_DIR")
    if env:
        return Path(env).resolve()
    return (Path(__file__).resolve().parent.parent.parent / "mods").resolve()


def get_user_mods_dir() -> Path:
    """Folder where the user, the store and the mod creator install mods."""
    from axiom.paths import get_mods_dir
    return get_mods_dir().resolve()


def get_mod_search_dirs(extra_dirs: list[Path] | None = None) -> list[Path]:
    """Absolute discovery folders: official, user, then extra ones. Never cwd-relative,
    never `dist/` (build artefacts)."""
    dirs = [get_official_mods_dir(), get_user_mods_dir()]
    for d in extra_dirs or []:
        dirs.append(Path(d).resolve())
    unique: list[Path] = []
    for d in dirs:
        if d not in unique:
            unique.append(d)
    return unique


def discover_mods(extra_dirs: list[Path] | None = None) -> list[tuple[ModManifest, Path]]:
    """Scan the mod folders for installed mods (.axmod archives or unpacked dirs).

    When the same id is found twice, the first folder wins (official before user)
    and an unpacked folder wins over an archive in the same folder.
    """
    found: dict[str, tuple[ModManifest, Path]] = {}
    seen_paths: set[Path] = set()

    for base_dir in get_mod_search_dirs(extra_dirs):
        if not base_dir.is_dir():
            continue
        local: dict[str, tuple[ModManifest, Path]] = {}

        for sub_dir in sorted(base_dir.iterdir()):
            if sub_dir.name.startswith(".") or not sub_dir.is_dir() or not (sub_dir / "mod.toml").is_file():
                continue
            real = sub_dir.resolve()
            if real in seen_paths:  # e.g. a symlink alias of another mod folder
                continue
            seen_paths.add(real)
            try:
                manifest = parse_manifest_file(sub_dir / "mod.toml")
            except Exception as err:
                logger.warning("Ignoring mod folder %s: invalid manifest: %s", sub_dir, err)
                continue
            local.setdefault(manifest.id, (manifest, sub_dir))

        for archive_file in sorted(base_dir.glob("*.axmod")):
            try:
                manifest = load_manifest_from_archive(archive_file)
            except Exception as err:
                logger.warning("Ignoring archive %s: %s", archive_file, err)
                continue
            local.setdefault(manifest.id, (manifest, archive_file))

        for mod_id, entry in local.items():
            if mod_id in found:
                logger.info("Mod '%s' in %s is shadowed by %s", mod_id, entry[1], found[mod_id][1])
                continue
            found[mod_id] = entry
            if is_safe_mode_eligible(entry[0], entry[1]):
                _SAFE_MODE_ELIGIBLE.add(mod_id)
            else:
                _SAFE_MODE_ELIGIBLE.discard(mod_id)
            if is_enabled_by_default(entry[0]):
                _DEFAULT_DISABLED.discard(mod_id)
            else:
                _DEFAULT_DISABLED.add(mod_id)

    return sorted(found.values(), key=lambda t: t[0].id)


# ---------------------------------------------------------------------------
# Status / plan (static, from manifests)
# ---------------------------------------------------------------------------

STATE_ACTIVE = "active"                  # loaded in this process
STATE_ENABLED = "enabled"                # will load (plan computed without running code)
STATE_DISABLED = "disabled"              # disabled by the user
STATE_SAFE_MODE = "safe_mode"            # not loaded in safe mode (only the recovery set is)
STATE_MISSING_PY = "missing_python_deps"
STATE_REJECTED = "rejected"              # set aside by the resolver (API, deps, conflict, cycle)
STATE_FAILED = "failed"                  # error while loading / in init()
STATE_FAULTED = "faulted"                # disabled at runtime after raising
STATE_NEXT_LAUNCH = "disabled_next_launch"  # disabled, takes effect at next launch (D-5)


@dataclass
class ModStatus:
    mod_id: str
    state: str
    reason: str = ""
    path: Path | None = None
    manifest: ModManifest | None = None
    order: int | None = None
    content_hash: str = ""   # computed once per load (get_active_modpack)

    @property
    def is_loaded(self) -> bool:
        return self.state in (STATE_ACTIVE, STATE_NEXT_LAUNCH)


@dataclass
class ModpackPlan:
    statuses: dict[str, ModStatus] = field(default_factory=dict)
    load_order: list[str] = field(default_factory=list)
    report: Any = None
    exclusive_conflicts: list[tuple[str, list[str]]] = field(default_factory=list)


def plan_modpack(
    installed: list[tuple[ModManifest, Path]] | None = None,
    config: AppConfig | None = None,
    user_order: list[str] | None = None,
) -> ModpackPlan:
    """Compute, from the manifests only, which mods would load, in which order, and why
    the others would not (user choice, safe mode, Python packages, API, dependencies with
    cascade, conflicts, cycles)."""
    from axiom.kernel.dependencies import check_mod_python_dependencies
    from axiom.kernel.resolver import compute_exclusive_conflicts, resolve_load_order

    if installed is None:
        installed = discover_mods()
    if user_order is None:
        user_order = get_user_mod_order(config)

    plan = ModpackPlan()
    candidates: dict[str, ModManifest] = {}
    unavailable: dict[str, str] = {}
    for manifest, path in installed:
        st = ModStatus(manifest.id, STATE_ENABLED, path=path, manifest=manifest)
        plan.statuses[manifest.id] = st
        if is_safe_mode() and not is_safe_mode_eligible(manifest, path):
            st.state, st.reason = STATE_SAFE_MODE, SAFE_MODE_REASON
        elif not is_safe_mode() and not is_mod_enabled(manifest.id, config, manifest):
            st.state, st.reason = STATE_DISABLED, (
                "Disabled by the user." if is_enabled_by_default(manifest)
                or "enabled" in (getattr(config, "mod_settings", {}) or {}).get(manifest.id, {})
                else "Disabled by default (enable it to use it)."
            )
        else:
            missing = check_mod_python_dependencies(manifest)
            if missing:
                st.state, st.reason = STATE_MISSING_PY, "; ".join(missing)
            else:
                candidates[manifest.id] = manifest
                continue
        unavailable[manifest.id] = st.reason

    report = resolve_load_order(candidates, user_order=user_order, unavailable=unavailable)
    for mod_id, reason in report.disabled_mods.items():
        st = plan.statuses[mod_id]
        st.state, st.reason = STATE_REJECTED, reason
    for i, mod_id in enumerate(report.load_order):
        plan.statuses[mod_id].order = i
    plan.load_order = list(report.load_order)
    plan.report = report
    plan.exclusive_conflicts = compute_exclusive_conflicts(candidates, report.load_order)
    return plan


# ---------------------------------------------------------------------------
# Loading one mod
# ---------------------------------------------------------------------------

def _module_name(manifest: ModManifest) -> str:
    return f"axiom_mod_{manifest.id.replace('.', '_').replace('-', '_')}"


def _purge_modules(prefix: str) -> None:
    for name in [n for n in sys.modules if n == prefix or n.startswith(prefix + ".")]:
        sys.modules.pop(name, None)


def _load_mod_root(
    root: Path,
    manifest: ModManifest,
    registry: KernelRegistry,
    config: AppConfig | None,
    origin: str,
) -> tuple[ModManifest, ModContext, Any]:
    """Common loading path: declared slots, locales, main.py executed as a package
    (`from . import helpers` works), `init(ctx)`. Any failure undoes everything."""
    register_mod_root(manifest.id, root)
    mod_ctx = ModContext(manifest, registry, config)
    module_name = _module_name(manifest)
    module = None
    try:
        for slot_name, rule_str in getattr(manifest, "provides_slots", {}).items():
            try:
                rule = SlotRule(rule_str.lower())
            except ValueError:
                rule = SlotRule.COLLECT
            mod_ctx.declare_slot(slot_name, rule)

        # Register mod locales automatically via ModContext into axiom.kernel:locales slot
        if getattr(manifest, "locales", None):
            for lang_code, strings in manifest.locales.items():
                if isinstance(strings, dict):
                    mod_ctx.contribute_slot("axiom.kernel:locales", (lang_code, strings))

        # Declarative storage policies of the manifest (DOC §10.2, K9); already done
        # at bootstrap for every installed mod, done here for a mod loaded alone.
        declare_mod_storage(manifest, root)

        main_py = root / "main.py"
        if main_py.is_file():
            spec = importlib.util.spec_from_file_location(
                module_name, main_py, submodule_search_locations=[str(root)]
            )
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

        _check_custom_storage_registered(manifest)
    except BaseException:
        # I4: nothing of a failed mod stays registered.
        try:
            mod_ctx.cleanup()
        finally:
            _purge_modules(module_name)
        raise

    logger.info("Loaded mod '%s' (v%s) from %s", manifest.id, manifest.version, origin)
    return manifest, mod_ctx, module


# Storage declared by each installed mod's manifest: {mod_id: [registered specs]}.
# Kept while the mod is disabled — the kernel still rewinds/forks its data with
# its storage code only (owner decision 2026-10-03).
_DECLARED_STORAGE: dict[str, list[Any]] = {}


def _resolve_storage_handler(manifest: ModManifest, root: Path, ref: str) -> Any:
    """``"module:function"`` of the mod. Only that module is imported (as
    ``mods.<mod_id>.<module>``): no hook, prompt or UI of the mod runs."""
    module_name, func_name = ref.split(":", 1)
    register_mod_root(manifest.id, root)
    try:
        module = importlib.import_module(f"mods.{manifest.id}.{module_name}")
    except Exception as err:
        raise ModLoadError(f"[storage] cannot import '{module_name}' of mod '{manifest.id}': {err}") from err
    func = getattr(module, func_name, None)
    if not callable(func):
        raise ModLoadError(f"[storage] '{ref}' of mod '{manifest.id}' is not a function.")
    return func


def declare_mod_storage(manifest: ModManifest, root: Path) -> list[Any]:
    """Register the save data declared by a mod's `[storage]` (idempotent).

    Called for every installed mod, enabled or not: ``step_keyed_table`` data is
    rewound/forked generically, ``custom`` data by the handlers the manifest names
    (``rewind`` / ``fork`` / ``snapshot``). ``events`` / ``versioned_kv`` live in
    kernel tables. A table already registered differently or by another owner is a
    conflict (ModLoadError, nothing registered for that mod).
    """
    from axiom.storage_registry import (
        StoragePolicy,
        TableStorageSpec,
        find_storage_spec,
        register_table_storage,
        unregister_storage,
    )

    if manifest.id in _DECLARED_STORAGE:
        return _DECLARED_STORAGE[manifest.id]
    registered: list[Any] = []
    try:
        for name, decl in (manifest.storage or {}).items():
            policy = decl["policy"]
            if policy in ("events", "versioned_kv"):
                continue
            if policy == "custom" and not any(
                h in decl for h in ("rewind", "fork", "snapshot", "state", "load", "diff")
            ):
                continue  # registered by init() (checked once it has run)
            table = decl.get("table") or name
            existing = find_storage_spec(table)
            if policy == "step_keyed_table":
                if existing is not None and existing.owner is None and existing.policy is StoragePolicy.STEP_KEYED \
                        and (existing.step_column or "").lower() == decl["step_column"].lower():
                    continue  # handled by the kernel itself
                spec = TableStorageSpec(
                    table_name=table,
                    policy=StoragePolicy.STEP_KEYED,
                    step_column=decl["step_column"],
                    columns=tuple(decl["columns"]),
                    id_column=decl["id_column"],
                    id_autoincrement=decl["id_autoincrement"],
                    fork_with=decl.get("fork_with"),
                    owner=manifest.id,
                )
            else:
                handlers = {h: _resolve_storage_handler(manifest, root, decl[h])
                            for h in ("rewind", "fork", "snapshot", "state", "load", "diff") if h in decl}
                external = "table" not in decl
                spec = TableStorageSpec(
                    table_name=table,
                    policy=StoragePolicy.CUSTOM,
                    step_column=None,
                    is_runtime=True,
                    custom_rewind=handlers.get("rewind"),
                    custom_fork=handlers.get("fork"),
                    custom_snapshot=handlers.get("snapshot"),
                    section=decl.get("section"),
                    custom_state=handlers.get("state"),
                    custom_load=handlers.get("load"),
                    custom_diff=handlers.get("diff"),
                    save_scoped=not external,
                    external=external,
                    owner=manifest.id,
                )
            if existing is not None:
                raise ModLoadError(
                    f"[storage] '{name}': table '{table}' is already registered "
                    f"({existing.policy.value}, by {'mod ' + existing.owner if existing.owner else 'the kernel'})."
                )
            register_table_storage(spec)
            registered.append(spec)
    except BaseException:
        for spec in registered:
            unregister_storage(spec)
        raise
    _DECLARED_STORAGE[manifest.id] = registered
    return registered


def ensure_installed_storage_declared() -> None:
    """Declare the `[storage]` of every installed mod (no mod code runs but their
    storage handlers). Called by the storage registry before its first rewind,
    fork or purge when no modpack was bootstrapped in this process."""
    try:
        installed = discover_mods()
    except Exception:
        logger.exception("Mod discovery failed: mods' save data not declared")
        return
    for manifest, path in installed:
        try:
            root = path if path.is_dir() else _extract_archive(path, manifest)
            declare_mod_storage(manifest, root)
        except Exception as err:
            logger.error("Storage of mod '%s' could not be declared: %s", manifest.id, err)


def forget_declared_storage() -> None:
    """Unregister every manifest-declared storage (a new modpack is being loaded)."""
    from axiom.storage_registry import unregister_storage

    for specs in _DECLARED_STORAGE.values():
        for spec in specs:
            unregister_storage(spec)
    _DECLARED_STORAGE.clear()


def _check_custom_storage_registered(manifest: ModManifest) -> None:
    """A declared ``custom`` storage must exist once ``init`` has run (D13: no
    declaration without behaviour)."""
    from axiom.storage_registry import find_storage_spec

    for name, decl in (manifest.storage or {}).items():
        if decl["policy"] != "custom":
            continue
        target = decl.get("table", name)
        spec = find_storage_spec(target)
        if spec is None or (spec.owner not in (None, manifest.id)):
            raise ModLoadError(
                f"[storage] '{name}': declared `custom` but '{target}' was not registered "
                f"(storage handlers in the manifest, or ctx.register_storage / "
                f"ctx.register_table_storage in init())."
            )


def load_mod_from_dir(
    dir_path: Path | str,
    registry: KernelRegistry,
    config: AppConfig | None = None,
) -> tuple[ModManifest, ModContext | None, Any]:
    """Load and initialize a mod from an unpacked directory.

    Returns (manifest, None, None) when the mod is disabled (user, safe mode) or a
    Python package it requires is missing. Raises ModLoadError on any other failure
    (nothing stays registered).
    """
    path = Path(dir_path).resolve()
    if not path.is_dir():
        raise ModLoadError(f"Mod directory not found: {path}")

    manifest_file = path / "mod.toml"
    if not manifest_file.is_file():
        raise ModLoadError(f"Missing mod.toml in {path}")

    manifest = parse_manifest_file(manifest_file)
    if not _precheck(manifest, config):
        return manifest, None, None
    return _load_mod_root(path, manifest, registry, config, f"directory {path}")


def _precheck(manifest: ModManifest, config: AppConfig | None) -> bool:
    if not is_mod_enabled(manifest.id, config, manifest):
        logger.info("Mod '%s' is disabled (safe_mode=%s), skipping.", manifest.id, is_safe_mode())
        return False
    if manifest.axiom_api != KERNEL_API:
        raise ModLoadError(
            f"Mod '{manifest.id}' requires axiom_api={manifest.axiom_api}, kernel provides {KERNEL_API}."
        )
    from axiom.kernel.dependencies import check_mod_python_dependencies
    missing_deps = check_mod_python_dependencies(manifest)
    if missing_deps:
        for msg in missing_deps:
            logger.warning("[PythonDeps] %s", msg)
        return False
    return True


def get_archive_cache_dir() -> Path:
    """Where .axmod archives are extracted to be imported as packages."""
    return get_user_mods_dir() / ".axmod-cache"


def _extract_archive(path: Path, manifest: ModManifest) -> Path:
    """Extract an archive once into the cache (keyed by its SHA-256) and return the root."""
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    dest = get_archive_cache_dir() / f"{manifest.id}-{manifest.version}-{digest}"
    if (dest / "mod.toml").is_file():
        return dest
    tmp = dest.with_name(dest.name + f".tmp{os.getpid()}-{threading.get_ident()}")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    with zipfile.ZipFile(path, "r") as zf:
        names = zf.namelist()
        toml_entries = [n for n in names if n.replace("\\", "/").lower().endswith("mod.toml")]
        top = ""
        if "mod.toml" not in names and toml_entries:
            # archive packed with a top folder: <folder>/mod.toml
            top = min(toml_entries, key=len)[: -len("mod.toml")]
        for name in names:
            norm = name.replace("\\", "/")
            if top and not norm.startswith(top):
                continue
            rel = norm[len(top):]
            if not rel or rel.endswith("/"):
                continue
            target = (tmp / rel).resolve()
            if tmp.resolve() not in target.parents:
                shutil.rmtree(tmp, ignore_errors=True)
                raise ModLoadError(f"Unsafe path '{name}' in archive {path}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(name))
    try:
        tmp.rename(dest)
    except OSError:
        shutil.rmtree(tmp, ignore_errors=True)  # another process extracted it first
    return dest


def load_mod_from_archive(
    archive_path: Path | str,
    registry: KernelRegistry,
    config: AppConfig | None = None,
) -> tuple[ModManifest, ModContext | None, Any]:
    """Load and initialize a mod from a .axmod (ZIP) archive.

    The archive is extracted once into a cache folder and imported as a package, so
    multi-file mods (relative imports or `mods.<id>.<module>` imports) work without
    their sources anywhere else on disk.
    """
    path = Path(archive_path).resolve()
    if not path.is_file():
        raise ModLoadError(f"Mod archive not found: {path}")

    manifest = load_manifest_from_archive(path)
    if not _precheck(manifest, config):
        return manifest, None, None
    try:
        root = _extract_archive(path, manifest)
    except (OSError, zipfile.BadZipFile) as err:
        raise ModLoadError(f"Failed to extract archive {path}: {err}") from err
    return _load_mod_root(root, manifest, registry, config, f"archive {path}")


def load_mod(
    path: Path | str,
    registry: KernelRegistry,
    config: AppConfig | None = None,
) -> tuple[ModManifest, ModContext | None, Any]:
    """Load and initialize a mod from either a directory or a .axmod archive."""
    p = Path(path).resolve()
    if p.is_dir():
        return load_mod_from_dir(p, registry, config)
    elif p.is_file() and p.suffix in (".axmod", ".zip"):
        return load_mod_from_archive(p, registry, config)
    raise ModLoadError(f"Invalid mod path (must be directory or .axmod archive): {path}")


# ---------------------------------------------------------------------------
# Modpack loading and runtime state
# ---------------------------------------------------------------------------

class ModLoadState:
    """Real status of every installed mod for one registry (D13)."""

    def __init__(self, registry: KernelRegistry, plan: ModpackPlan) -> None:
        self.registry = registry
        self.plan = plan
        self.statuses: dict[str, ModStatus] = plan.statuses
        self.contexts: dict[str, ModContext] = {}
        self.modules: dict[str, Any] = {}
        self.load_order: list[str] = []

    # -- queries -------------------------------------------------------
    def get_status(self, mod_id: str) -> ModStatus | None:
        return self.statuses.get(mod_id)

    def is_active(self, mod_id: str) -> bool:
        st = self.statuses.get(mod_id)
        return bool(st and st.state == STATE_ACTIVE)

    def dependents_of(self, mod_id: str) -> list[str]:
        """Loaded mods that need `mod_id` (directly, or through a virtual id it alone provides)."""
        manifests = {m: self.statuses[m].manifest for m in self.contexts if self.statuses[m].manifest}
        provided = {mod_id}
        if mod_id in self.statuses and self.statuses[mod_id].manifest:
            provided |= set(self.statuses[mod_id].manifest.ordering.provides)
        result = []
        for other, m in manifests.items():
            if other == mod_id or not self.statuses[other].is_loaded:
                continue
            for dep_name, dep in m.dependencies.items():
                if dep.optional or dep_name not in provided:
                    continue
                alt = [
                    p for p, pm in manifests.items()
                    if p not in (mod_id, other) and self.statuses[p].is_loaded
                    and (p == dep_name or dep_name in pm.ordering.provides)
                ]
                if not alt:
                    result.append(other)
                    break
        return sorted(result)

    # -- changes -------------------------------------------------------
    def _on_fault(self, mod_id: str, reason: str) -> None:
        st = self.statuses.get(mod_id)
        if st is not None:
            st.state, st.reason = STATE_FAULTED, reason
        for dep in self.dependents_of(mod_id):
            self.disable(dep, f"Required dependency '{mod_id}' was disabled: {reason}", cascade=True)

    def disable(self, mod_id: str, reason: str = "Disabled by the user.", cascade: bool = True) -> str:
        """Disable one loaded mod. Returns "now", "next_launch" or "not_loaded" (D-5)."""
        ctx = self.contexts.get(mod_id)
        st = self.statuses.get(mod_id)
        if ctx is None or st is None or st.state != STATE_ACTIVE:
            return "not_loaded"
        if not ctx.can_disable_hot:
            st.state = STATE_NEXT_LAUNCH
            st.reason = f"{reason} Takes effect at next launch (the mod uses patches or raw code)."
            outcome = "next_launch"
        else:
            ctx.cleanup()
            self.registry.purge_mod(mod_id)
            st.state, st.reason = STATE_DISABLED, reason
            outcome = "now"
        if cascade:
            for dep in self.dependents_of(mod_id):
                self.disable(dep, f"Required dependency '{mod_id}' was disabled.", cascade=True)
        return outcome


_PATCH_FAULT_LISTENER: Any = None


def bootstrap_all_mods(
    registry: KernelRegistry | None = None,
    config: AppConfig | None = None,
    extra_dirs: list[Path] | None = None,
    user_order: list[str] | None = None,
) -> KernelRegistry:
    """Bootstrap all enabled mods into a KernelRegistry according to the load order.

    Never fails as a whole: a mod that is rejected (API, dependency, conflict, cycle),
    fails in init() or depends on a failed mod is set aside with its reason, and the
    others load. The result is in `registry.load_state` (see `get_mod_status`).
    Prefer `get_kernel_registry()` to share one modpack per process (D-4).
    """
    from axiom.config import load_config
    from axiom.kernel.patcher import (
        add_patch_fault_listener,
        remove_patch_fault_listener,
        set_patch_mod_order,
    )
    from axiom.kernel.registry import set_active_registry

    if config is None:
        config = load_config()
    if registry is None:
        registry = KernelRegistry()
    set_active_registry(registry)

    try:
        installed = discover_mods(extra_dirs)
    except Exception as err:
        logger.warning("Error discovering installed mods during bootstrap: %s", err)
        installed = []

    plan = plan_modpack(installed, config, user_order)

    # Save data of EVERY installed mod, loaded or not: a disabled mod's data keeps
    # following rewinds and forks (only its storage code runs).
    from axiom.storage_registry import mark_mod_storage_ready
    forget_declared_storage()
    mark_mod_storage_ready()
    for manifest, path in installed:
        st = plan.statuses.get(manifest.id)
        try:
            root = path if path.is_dir() else _extract_archive(path, manifest)
            declare_mod_storage(manifest, root)
        except Exception as err:
            logger.error("Storage of mod '%s' could not be declared: %s", manifest.id, err)
            if st is not None and st.state == STATE_ENABLED:
                st.state, st.reason = STATE_FAILED, f"Storage declaration failed: {err}"
                if manifest.id in plan.load_order:
                    plan.load_order.remove(manifest.id)

    state = ModLoadState(registry, plan)
    registry.load_state = state
    registry.set_mod_order(plan.load_order)
    set_patch_mod_order(plan.load_order)
    registry.add_fault_listener(state._on_fault)

    def _patch_fault(mod_id: str, reason: str) -> None:
        if mod_id in state.contexts and state.statuses[mod_id].state == STATE_ACTIVE:
            registry.disable_mod(mod_id, reason)
    # Patches are process-wide: only the latest modpack listens to their faults
    # (one listener, not one more per bootstrap).
    global _PATCH_FAULT_LISTENER
    if _PATCH_FAULT_LISTENER is not None:
        remove_patch_fault_listener(_PATCH_FAULT_LISTENER)
    _PATCH_FAULT_LISTENER = _patch_fault
    add_patch_fault_listener(_patch_fault)

    for mod_id, st in plan.statuses.items():
        if st.state not in (STATE_ENABLED,):
            logger.warning("Mod '%s' not loaded (%s): %s", mod_id, st.state, st.reason)

    for mod_id in plan.load_order:
        st = plan.statuses[mod_id]
        manifest = st.manifest
        # Dependencies that failed earlier in this bootstrap take their dependents down.
        failed_dep = next(
            (
                d for d, dep in manifest.dependencies.items()
                if not dep.optional and not _dependency_loaded(state, d)
            ),
            None,
        )
        if failed_dep is not None:
            cause = state.statuses.get(failed_dep)
            st.state = STATE_FAILED
            st.reason = f"Required dependency '{failed_dep}' failed to load" + (
                f": {cause.reason}" if cause and cause.reason else "."
            )
            logger.error("Mod '%s' not loaded: %s", mod_id, st.reason)
            continue
        try:
            _m, ctx, module = load_mod(st.path, registry, config)
        except Exception as err:
            st.state, st.reason = STATE_FAILED, str(err)
            logger.error("Failed to load mod '%s': %s", mod_id, err, exc_info=True)
            continue
        if ctx is None:
            st.state, st.reason = STATE_FAILED, "Not loaded (disabled or missing Python package)."
            continue
        st.state, st.reason = STATE_ACTIVE, ""
        state.contexts[mod_id] = ctx
        state.modules[mod_id] = module
        state.load_order.append(mod_id)

    return registry


def _dependency_loaded(state: ModLoadState, dep_name: str) -> bool:
    for mod_id in state.load_order:
        st = state.statuses[mod_id]
        if st.state != STATE_ACTIVE:
            continue
        if mod_id == dep_name or dep_name in st.manifest.ordering.provides:
            return True
    return False


_PROCESS_REGISTRY: KernelRegistry | None = None
_PROCESS_LOCK = threading.Lock()


def get_kernel_registry(config: AppConfig | None = None) -> KernelRegistry:
    """Process-wide registry: bootstrapped on first call only (D-4, one modpack per
    process). Sessions and UIs should use this instead of calling bootstrap_all_mods."""
    global _PROCESS_REGISTRY
    with _PROCESS_LOCK:
        if _PROCESS_REGISTRY is None:
            _PROCESS_REGISTRY = bootstrap_all_mods(config=config)
        else:
            from axiom.kernel.registry import set_active_registry
            set_active_registry(_PROCESS_REGISTRY)
        return _PROCESS_REGISTRY


def has_kernel_registry() -> bool:
    return _PROCESS_REGISTRY is not None


def reset_kernel_registry() -> None:
    """Forget the process-wide registry (tests only; loaded mods are not unloaded)."""
    global _PROCESS_REGISTRY
    with _PROCESS_LOCK:
        _PROCESS_REGISTRY = None


def get_load_state(registry: KernelRegistry | None = None) -> ModLoadState | None:
    """Load state of a registry (default: the process-wide one, else the active one)."""
    if registry is None:
        from axiom.kernel.registry import get_active_registry
        registry = _PROCESS_REGISTRY or get_active_registry()
    return getattr(registry, "load_state", None) if registry is not None else None


def get_mod_status(mod_id: str, registry: KernelRegistry | None = None) -> ModStatus | None:
    state = get_load_state(registry)
    return state.get_status(mod_id) if state else None


def is_mod_active(mod_id: str, registry: KernelRegistry | None = None) -> bool:
    """True if the mod is really loaded and running in this process."""
    state = get_load_state(registry)
    return bool(state and state.is_active(mod_id))


def disable_mod_hot(
    mod_id: str,
    registry: KernelRegistry | None = None,
    reason: str = "Disabled by the user.",
) -> str:
    """Disable one loaded mod without reloading the others (D-5).

    Returns "now" (hooks/slots/services/jobs removed via its ModContext),
    "next_launch" (the mod has patches or declared raw code) or "not_loaded".
    Dependents are disabled with it. The caller persists the choice in the config.
    """
    state = get_load_state(registry)
    if state is None:
        return "not_loaded"
    return state.disable(mod_id, reason)


def mod_content_hash(path: Path | str) -> str:
    """SHA-256 of a mod's content: the archive bytes, or every file of the folder
    (relative path + bytes, sorted; caches excluded). Same content = same hash."""
    p = Path(path)
    h = hashlib.sha256()
    if p.is_file():
        h.update(p.read_bytes())
        return h.hexdigest()
    files = sorted(
        f for f in p.rglob("*")
        if f.is_file() and "__pycache__" not in f.parts and f.suffix != ".pyc"
    )
    for f in files:
        h.update(f.relative_to(p).as_posix().encode("utf-8"))
        h.update(b"\0")
        h.update(f.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def _status_hash(st: ModStatus) -> str:
    if not st.content_hash and st.path is not None:
        st.content_hash = mod_content_hash(st.path)
    return st.content_hash


def get_active_modpack(registry: KernelRegistry | None = None) -> list[dict[str, str]]:
    """The loaded modpack, in load order: [{id, version, name, hash}] (DOC §10.3:
    ids + versions + hash). Empty when no modpack is loaded in this process."""
    state = get_load_state(registry)
    if state is None:
        return []
    out = []
    for mod_id in state.load_order:
        st = state.statuses.get(mod_id)
        if st is None or st.state != STATE_ACTIVE or st.manifest is None:
            continue
        out.append({
            "id": mod_id,
            "version": st.manifest.version,
            "name": st.manifest.name,
            "hash": _status_hash(st),
        })
    return out


def interface_unavailable_message(mod_id: str, registry: KernelRegistry | None = None) -> str | None:
    """Why the interface mod ``mod_id`` cannot run, with how to fix it (None = it is active).

    Launchers check the real status (dependencies, conflicts, failures...), not only
    the user's checkbox: an interface whose turn pipeline is gone must not start.
    """
    st = get_mod_status(mod_id, registry)
    if st is not None and st.state == STATE_ACTIVE:
        return None
    if st is None:
        reason = "it is not installed."
    elif st.state == STATE_DISABLED:
        reason = "it is disabled in your configuration."
    else:
        reason = f"it could not be loaded: {st.reason}"
    lines = [f"The interface mod '{mod_id}' is not available: {reason}"]
    if st is not None and st.state == STATE_DISABLED:
        lines.append(f"To re-enable it, run:\n    axiom mods enable {mod_id}")
    if not is_safe_mode():
        lines.append(
            "To repair your mods, start in safe mode (interface + minimal chat only):\n"
            "    python main.py --safe-mode    (or python main_web.py --safe-mode)\n"
            "then check them with:\n    axiom mods list"
        )
    return "\n\n".join(lines)
