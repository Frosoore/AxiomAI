"""axiom/kernel/manifest.py

Declarative manifest parser and strict validator for Axiom AI mods (.axmod).
Reads mod.toml from disk or ZIP archive without executing any Python code.
"""

from __future__ import annotations

import re
import tomllib
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ManifestError(Exception):
    """Raised when a mod manifest is missing, malformed, or fails validation."""


_MOD_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]+\.[a-zA-Z0-9_.-]+$")
_SEMVER_REGEX = re.compile(r"^\d+\.\d+\.\d+(-[a-zA-Z0-9_.-]+)?(\+[a-zA-Z0-9_.-]+)?$")


@dataclass(frozen=True)
class ModDependency:
    """Represents a dependency declared by a mod."""

    name: str
    version_spec: str = "*"
    optional: bool = False


@dataclass(frozen=True)
class ModOrdering:
    """Sequencing and conflict constraints declared in [ordering]."""

    after: list[str] = field(default_factory=list)
    before: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    provides: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ModContributes:
    """Declared extension point contributions in [contributes]."""

    hooks: list[str] = field(default_factory=list)
    slots: list[str] = field(default_factory=list)
    patches: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ModManifest:
    """Strictly validated in-memory representation of a mod.toml manifest."""

    id: str
    version: str
    axiom_api: int
    name: str = ""
    description: str = ""
    author: str = ""
    dependencies: dict[str, ModDependency] = field(default_factory=dict)
    ordering: ModOrdering = field(default_factory=ModOrdering)
    contributes: ModContributes = field(default_factory=ModContributes)
    provides_slots: dict[str, str] = field(default_factory=dict)
    storage: dict[str, Any] = field(default_factory=dict)
    python_requires: list[str] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict)


def parse_manifest_string(toml_str: str) -> ModManifest:
    """Parse and strictly validate a TOML string as a ModManifest."""
    try:
        data = tomllib.loads(toml_str)
    except Exception as err:
        raise ManifestError(f"Failed to parse TOML manifest: {err}") from err

    mod_section = data.get("mod")
    if not isinstance(mod_section, dict):
        raise ManifestError("Manifest missing required [mod] table.")

    mod_id = mod_section.get("id")
    if not isinstance(mod_id, str) or not _MOD_ID_REGEX.match(mod_id):
        raise ManifestError(
            f"Invalid mod id '{mod_id}'. Mod ID must be namespaced like 'author.name' (matching {_MOD_ID_REGEX.pattern})."
        )

    version = mod_section.get("version")
    if not isinstance(version, str) or not _SEMVER_REGEX.match(version):
        raise ManifestError(
            f"Invalid mod version '{version}'. Expected valid SemVer (e.g. '1.0.0')."
        )

    api_raw = mod_section.get("axiom_api")
    try:
        axiom_api = int(api_raw)
        if axiom_api < 1:
            raise ValueError()
    except (TypeError, ValueError) as err:
        raise ManifestError(
            f"Invalid axiom_api '{api_raw}'. Must be an integer >= 1."
        ) from err

    name = str(mod_section.get("name", mod_id))
    description = str(mod_section.get("description", ""))
    author = str(mod_section.get("author", ""))

    # Dependencies
    deps: dict[str, ModDependency] = {}
    deps_section = data.get("dependencies", {})
    if isinstance(deps_section, dict):
        for dep_name, dep_spec in deps_section.items():
            if isinstance(dep_spec, str):
                deps[dep_name] = ModDependency(name=dep_name, version_spec=dep_spec, optional=False)
            elif isinstance(dep_spec, dict):
                v_spec = str(dep_spec.get("version", "*"))
                opt = bool(dep_spec.get("optional", False))
                deps[dep_name] = ModDependency(name=dep_name, version_spec=v_spec, optional=opt)

    # Ordering
    ordering_section = data.get("ordering", {})
    after_list = list(ordering_section.get("after", [])) if isinstance(ordering_section, dict) else []
    before_list = list(ordering_section.get("before", [])) if isinstance(ordering_section, dict) else []
    conflicts_list = list(ordering_section.get("conflicts", [])) if isinstance(ordering_section, dict) else []
    provides_list = list(ordering_section.get("provides", [])) if isinstance(ordering_section, dict) else []
    ordering = ModOrdering(
        after=after_list,
        before=before_list,
        conflicts=conflicts_list,
        provides=provides_list,
    )

    # Contributes
    contrib_section = data.get("contributes", {})
    hooks = list(contrib_section.get("hooks", [])) if isinstance(contrib_section, dict) else []
    slots = list(contrib_section.get("slots", [])) if isinstance(contrib_section, dict) else []
    patches = list(contrib_section.get("patches", [])) if isinstance(contrib_section, dict) else []
    contributes = ModContributes(hooks=hooks, slots=slots, patches=patches)

    # Storage
    storage_section = data.get("storage", {})
    storage = dict(storage_section) if isinstance(storage_section, dict) else {}

    # Provides slots (slot declarations)
    provides_slots_section = data.get("provides_slots", {})
    provides_slots: dict[str, str] = {}
    if isinstance(provides_slots_section, dict):
        for slot_name, slot_spec in provides_slots_section.items():
            if isinstance(slot_spec, dict):
                provides_slots[slot_name] = str(slot_spec.get("rule", "collect")).lower()
            elif isinstance(slot_spec, str):
                provides_slots[slot_name] = slot_spec.lower()

    # Python dependencies (Decision D-7)
    python_section = data.get("python", {})
    if isinstance(python_section, dict):
        py_reqs = list(python_section.get("requires", []))
    else:
        py_reqs = list(data.get("python_requires", []))

    return ModManifest(
        id=mod_id,
        version=version,
        axiom_api=axiom_api,
        name=name,
        description=description,
        author=author,
        dependencies=deps,
        ordering=ordering,
        contributes=contributes,
        provides_slots=provides_slots,
        storage=storage,
        python_requires=py_reqs,
        raw_data=data,
    )



def parse_manifest_file(file_path: str | Path) -> ModManifest:
    """Read a mod.toml file from disk and return its parsed ModManifest."""
    p = Path(file_path)
    if not p.is_file():
        raise ManifestError(f"Manifest file not found: {p}")
    try:
        content = p.read_text(encoding="utf-8")
    except Exception as err:
        raise ManifestError(f"Failed to read manifest file {p}: {err}") from err
    return parse_manifest_string(content)


def load_manifest_from_archive(archive_path: str | Path) -> ModManifest:
    """Extract mod.toml from an .axmod ZIP archive into memory and parse it."""
    p = Path(archive_path)
    if not p.is_file():
        raise ManifestError(f"Mod archive not found: {p}")
    try:
        with zipfile.ZipFile(p, mode="r") as zf:
            target_name = None
            for name in zf.namelist():
                if name.lower() == "mod.toml" or name.lower().endswith("/mod.toml"):
                    target_name = name
                    break
            if not target_name:
                raise ManifestError(f"Archive '{p.name}' does not contain 'mod.toml'.")
            content = zf.read(target_name).decode("utf-8")
            return parse_manifest_string(content)
    except zipfile.BadZipFile as err:
        raise ManifestError(f"Archive '{p.name}' is not a valid ZIP/.axmod archive: {err}") from err


def load_manifest(path: str | Path) -> ModManifest:
    """Polymorphic loader for a manifest from a directory, .toml file, or .axmod archive."""
    p = Path(path)
    if p.is_dir():
        mod_toml = p / "mod.toml"
        if not mod_toml.is_file():
            raise ManifestError(f"Directory '{p}' does not contain 'mod.toml'.")
        return parse_manifest_file(mod_toml)
    elif p.is_file():
        if p.suffix.lower() == ".toml":
            return parse_manifest_file(p)
        else:
            return load_manifest_from_archive(p)
    raise ManifestError(f"Path does not exist: {p}")
