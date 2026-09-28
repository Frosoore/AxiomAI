"""axiom/kernel

Core Mod Loader, Topological Order Resolver, Manifest Parser, and Registry.
"""

from axiom.kernel.context import ModContext
from axiom.kernel.manifest import (
    ManifestError,
    ModContributes,
    ModDependency,
    ModManifest,
    ModOrdering,
    load_manifest,
    load_manifest_from_archive,
    parse_manifest_file,
    parse_manifest_string,
)
from axiom.kernel.loader import (
    ModLoadError,
    bootstrap_all_mods,
    is_mod_enabled,
    is_official_mod,
    is_safe_mode,
    load_mod,
    load_mod_from_archive,
    load_mod_from_dir,
    set_safe_mode,
)
from axiom.kernel.registry import (
    KernelRegistry,
    RegistryError,
    SlotRule,
    get_active_registry,
    set_active_registry,
)
from axiom.kernel.resolver import (
    ConflictError,
    CyclicDependencyError,
    ResolutionError,
    ResolutionReport,
    resolve_load_order,
)
from axiom.kernel.step_context import (
    KernelStepContext,
    NoTurnPipelineInstalledError,
)
from axiom.kernel.patcher import (
    PatchRecord,
    PatchType,
    PatchingDuringStepError,
    ShortCircuit,
    get_active_patches,
    patchable,
    register_patch,
    remove_patch,
    remove_patches_by_mod,
    step_patch_freeze,
)
from axiom.kernel.scaffold import scaffold_mod
from axiom.kernel.tester import ModTestResult, test_mod
from axiom.kernel.dev import poll_mod_once, reload_mod_instance, watch_mod
from axiom.kernel.llm_creator import (
    ModGenerationResult,
    apply_generated_mod,
    generate_mod,
    get_default_staged_mods_dir,
)
from axiom.kernel.dependencies import (
    check_mod_python_dependencies,
    check_python_requirement,
)
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

try:
    import importlib
    _m = importlib.import_module("mods")
    if hasattr(_m, "install_dotted_mod_finder"):
        _m.install_dotted_mod_finder()
except Exception:
    pass

__all__ = [
    "ConflictError",
    "CyclicDependencyError",
    "KernelRegistry",
    "KernelStepContext",
    "ManifestError",
    "ModContext",
    "ModContributes",
    "ModDependency",
    "ModGenerationResult",
    "ModIntegrityError",
    "ModLoadError",
    "ModManifest",
    "ModOrdering",
    "ModTestResult",
    "NoTurnPipelineInstalledError",
    "PatchRecord",
    "PatchType",
    "PatchingDuringStepError",
    "RegistryError",
    "ResolutionError",
    "ResolutionReport",
    "ShortCircuit",
    "SlotRule",
    "StoreError",
    "StoreModEntry",
    "apply_generated_mod",
    "bootstrap_all_mods",
    "calculate_sha256",
    "check_mod_python_dependencies",
    "check_python_requirement",
    "fetch_store_index",
    "generate_mod",
    "get_active_patches",
    "get_active_registry",
    "get_default_staged_mods_dir",
    "install_mod_from_store",
    "is_mod_enabled",
    "is_official_mod",
    "is_safe_mode",
    "load_manifest",
    "load_manifest_from_archive",
    "load_mod",
    "load_mod_from_archive",
    "load_mod_from_dir",
    "parse_manifest_file",
    "parse_manifest_string",
    "patchable",
    "poll_mod_once",
    "publish_mod_to_store_spec",
    "register_patch",
    "reload_mod_instance",
    "remove_patch",
    "remove_patches_by_mod",
    "resolve_load_order",
    "scaffold_mod",
    "search_store",
    "set_active_registry",
    "set_safe_mode",
    "step_patch_freeze",
    "test_mod",
    "watch_mod",
]


