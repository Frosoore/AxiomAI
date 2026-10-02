"""axiom/kernel/manifest.py

Declarative manifest parser and strict validator for Axiom AI mods (.axmod).
Reads mod.toml from disk or ZIP archive without executing any Python code.
"""

from __future__ import annotations

import json
import re
import tomllib
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from axiom.logger import logger


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
    # True when the mod runs "raw" code with side effects the kernel cannot undo
    # (monkeypatching, global state...): it can only be disabled at next launch (D-5).
    raw_code: bool = False


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
    locales: dict[str, dict[str, Any]] = field(default_factory=dict)

    def localized_name(self, lang: str | None = None) -> str:
        """Return the localized name/title of this mod for the specified language.

        If no language is specified, the application's active language is used.
        Fallback chain:
        1. Requested language (from locales/<lang>.json or locales/<lang>.toml)
        2. English ('en')
        3. Any first available translation defined in the mod
        4. Manifest default name (from mod.toml)
        """
        if lang is None:
            try:
                from axiom.config import load_config
                lang = getattr(load_config(), "language", "en")
            except Exception:
                lang = "en"

        # 1. Requested language
        if lang in self.locales:
            val = self.locales[lang].get("title") or self.locales[lang].get("name")
            if val:
                return str(val)

        # 2. English fallback
        if "en" in self.locales:
            val = self.locales["en"].get("title") or self.locales["en"].get("name")
            if val:
                return str(val)

        # 3. Any available translation (e.g. community mod providing only one language)
        for loc_dict in self.locales.values():
            val = loc_dict.get("title") or loc_dict.get("name")
            if val:
                return str(val)

        # 4. Manifest default
        return self.name or self.id

    def localized_description(self, lang: str | None = None) -> str:
        """Return the localized description of this mod for the specified language.

        If no language is specified, the application's active language is used.
        Fallback chain:
        1. Requested language (from locales/<lang>.json or locales/<lang>.toml)
        2. English ('en')
        3. Any first available translation defined in the mod
        4. Manifest default description (from mod.toml)
        """
        if lang is None:
            try:
                from axiom.config import load_config
                lang = getattr(load_config(), "language", "en")
            except Exception:
                lang = "en"

        # 1. Requested language
        if lang in self.locales:
            val = self.locales[lang].get("description")
            if val:
                return str(val)

        # 2. English fallback
        if "en" in self.locales:
            val = self.locales["en"].get("description")
            if val:
                return str(val)

        # 3. Any available translation (e.g. community mod providing only one language)
        for loc_dict in self.locales.values():
            val = loc_dict.get("description")
            if val:
                return str(val)

        # 4. Manifest default
        return self.description


def parse_manifest_string(toml_str: str, locales: dict[str, dict[str, Any]] | None = None) -> ModManifest:
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
            else:
                raise ManifestError(
                    f"Invalid dependency '{dep_name}': expected a version string or a table."
                )
        from axiom.kernel.api import validate_version_spec
        for dep in deps.values():
            try:
                validate_version_spec(dep.version_spec)
            except ValueError as err:
                raise ManifestError(f"Dependency '{dep.name}': {err}") from err

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
    raw_code = bool(contrib_section.get("raw_code", False)) if isinstance(contrib_section, dict) else False
    contributes = ModContributes(hooks=hooks, slots=slots, patches=patches, raw_code=raw_code)

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
        locales=locales or {},
    )



def parse_manifest_file(file_path: str | Path) -> ModManifest:
    """Read a mod.toml file from disk and return its parsed ModManifest.

    Automatically reads any translation files located in the adjacent `locales/` directory.
    """
    p = Path(file_path)
    if not p.is_file():
        raise ManifestError(f"Manifest file not found: {p}")
    try:
        content = p.read_text(encoding="utf-8")
    except Exception as err:
        raise ManifestError(f"Failed to read manifest file {p}: {err}") from err

    locales: dict[str, dict[str, Any]] = {}
    locales_dir = p.parent / "locales"
    if locales_dir.is_dir():
        for loc_file in sorted(locales_dir.iterdir()):
            if not loc_file.is_file():
                continue
            lang_code = loc_file.stem.lower()
            try:
                raw_text = loc_file.read_text(encoding="utf-8")
                if loc_file.suffix.lower() == ".json":
                    d = json.loads(raw_text)
                elif loc_file.suffix.lower() == ".toml":
                    d = tomllib.loads(raw_text)
                else:
                    continue
                if isinstance(d, dict):
                    locales[lang_code] = d
            except Exception as err:
                logger.debug("Failed to read locale file %s: %s", loc_file, err)

    return parse_manifest_string(content, locales=locales)


def load_manifest_from_archive(archive_path: str | Path) -> ModManifest:
    """Extract mod.toml from an .axmod ZIP archive into memory and parse it.

    Automatically extracts any translation files located in the archive's `locales/` directory.
    """
    p = Path(archive_path)
    if not p.is_file():
        raise ManifestError(f"Mod archive not found: {p}")
    try:
        with zipfile.ZipFile(p, mode="r") as zf:
            target_name = None
            locale_names: list[str] = []
            for name in zf.namelist():
                norm = name.replace("\\", "/")
                norm_lower = norm.lower()
                if norm_lower == "mod.toml" or norm_lower.endswith("/mod.toml"):
                    target_name = name
                elif "/locales/" in norm_lower or norm_lower.startswith("locales/"):
                    if norm_lower.endswith(".json") or norm_lower.endswith(".toml"):
                        locale_names.append(name)

            if not target_name:
                raise ManifestError(f"Archive '{p.name}' does not contain 'mod.toml'.")
            content = zf.read(target_name).decode("utf-8")

            locales: dict[str, dict[str, Any]] = {}
            for loc_entry in locale_names:
                stem = Path(loc_entry).stem.lower()
                try:
                    raw_text = zf.read(loc_entry).decode("utf-8")
                    if loc_entry.lower().endswith(".json"):
                        d = json.loads(raw_text)
                    elif loc_entry.lower().endswith(".toml"):
                        d = tomllib.loads(raw_text)
                    else:
                        continue
                    if isinstance(d, dict):
                        locales[stem] = d
                except Exception as err:
                    logger.debug("Failed to read locale entry %s in %s: %s", loc_entry, p, err)

            return parse_manifest_string(content, locales=locales)
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
