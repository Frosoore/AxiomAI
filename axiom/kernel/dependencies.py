"""axiom/kernel/dependencies.py

Python package dependency verification for mods (Decision D-7).
Inspects `[python].requires` in `mod.toml` using `importlib.metadata`
without running heavy or invasive pip installs.
"""

from __future__ import annotations

import importlib.metadata
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from axiom.kernel.manifest import ModManifest

from axiom.logger import logger


_REQ_REGEX = re.compile(
    r"^\s*([a-zA-Z0-9_.-]+)\s*([><!=~^]=?|[=]{2})?\s*([0-9a-zA-Z_.-]*)\s*$"
)


def _parse_version_tuple(v_str: str) -> tuple[int, ...]:
    """Parse version string into tuple of integers for comparison."""
    parts = []
    for part in re.split(r"[.\-_+]", v_str):
        if part.isdigit():
            parts.append(int(part))
        else:
            digits = re.findall(r"\d+", part)
            if digits:
                parts.append(int(digits[0]))
    return tuple(parts) if parts else (0,)


def check_python_requirement(req_str: str) -> tuple[bool, str | None]:
    """Check whether a Python package requirement is satisfied in the current environment.

    Args:
        req_str: PEP 508 requirement string, e.g. 'rank-bm25>=0.2.2' or 'httpx'.

    Returns:
        (satisfied: bool, message: str | None)
    """
    req_str = req_str.strip()
    if not req_str:
        return True, None

    # Try using packaging.requirements if available
    try:
        from packaging.requirements import Requirement
        from packaging.version import Version

        req = Requirement(req_str)
        pkg_name = req.name
        try:
            installed_version_str = importlib.metadata.version(pkg_name)
        except importlib.metadata.PackageNotFoundError:
            return False, f"Package '{pkg_name}' is not installed."

        if req.specifier:
            installed_v = Version(installed_version_str)
            if not req.specifier.contains(installed_v):
                return (
                    False,
                    f"Package '{pkg_name}' version {installed_version_str} does not satisfy specifier '{req.specifier}'.",
                )
        return True, None
    except ImportError:
        pass

    # Standard-library fallback parser
    match = _REQ_REGEX.match(req_str)
    if not match:
        pkg_name = req_str.split()[0]
        try:
            importlib.metadata.version(pkg_name)
            return True, None
        except importlib.metadata.PackageNotFoundError:
            return False, f"Package '{pkg_name}' is not installed."

    pkg_name, op, req_ver_str = match.groups()
    try:
        installed_version_str = importlib.metadata.version(pkg_name)
    except importlib.metadata.PackageNotFoundError:
        return False, f"Package '{pkg_name}' is not installed."

    if op and req_ver_str:
        inst_tuple = _parse_version_tuple(installed_version_str)
        req_tuple = _parse_version_tuple(req_ver_str)

        # Pad to equal length
        max_len = max(len(inst_tuple), len(req_tuple))
        inst_tuple = inst_tuple + (0,) * (max_len - len(inst_tuple))
        req_tuple = req_tuple + (0,) * (max_len - len(req_tuple))

        if op in (">=", "=>") and not (inst_tuple >= req_tuple):
            return False, f"Package '{pkg_name}' (v{installed_version_str}) does not satisfy '>={req_ver_str}'."
        elif op in ("==", "=") and not (inst_tuple == req_tuple):
            return False, f"Package '{pkg_name}' (v{installed_version_str}) does not satisfy '=={req_ver_str}'."
        elif op == ">" and not (inst_tuple > req_tuple):
            return False, f"Package '{pkg_name}' (v{installed_version_str}) does not satisfy '>{req_ver_str}'."
        elif op in ("<=", "=<") and not (inst_tuple <= req_tuple):
            return False, f"Package '{pkg_name}' (v{installed_version_str}) does not satisfy '<={req_ver_str}'."
        elif op == "<" and not (inst_tuple < req_tuple):
            return False, f"Package '{pkg_name}' (v{installed_version_str}) does not satisfy '<{req_ver_str}'."

    return True, None


def check_mod_python_dependencies(manifest: ModManifest) -> list[str]:
    """Inspect all declared Python requirements of a mod and return unsatisfied messages.

    Args:
        manifest: Parsed mod manifest.

    Returns:
        List of human-readable warnings for unsatisfied dependencies.
    """
    unsatisfied: list[str] = []
    for req in getattr(manifest, "python_requires", []):
        ok, msg = check_python_requirement(req)
        if not ok and msg:
            unsatisfied.append(
                f"Mod '{manifest.id}' requires Python package '{req}', which is not satisfied: {msg}"
            )
    return unsatisfied
