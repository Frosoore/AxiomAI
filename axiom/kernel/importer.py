"""axiom/kernel/importer.py

Import support for loaded mods, independent of the current directory and of the
repository's `mods/` package.

Every mod loaded by the kernel registers its root folder here (an unpacked directory
or the extraction cache of a `.axmod`). The finder then resolves
`mods.<mod_id>.<module>` (e.g. `mods.axiom.living_memory.living_memory`) to that
root, so a multi-file mod works from a `.axmod` archive without its sources on disk.
Unknown names are left to the other finders (and end in ImportError).
"""

from __future__ import annotations

from importlib.abc import MetaPathFinder
from importlib.machinery import ModuleSpec, PathFinder, SourceFileLoader
from pathlib import Path
import sys
import threading

_ROOTS: dict[str, Path] = {}
_LOCK = threading.Lock()


def register_mod_root(mod_id: str, root: Path | str) -> None:
    """Map `mods.<mod_id>` (and `mods.<mod_id with _>`) to a folder."""
    with _LOCK:
        _ROOTS[mod_id] = Path(root).resolve()
    install_mod_finder()


def get_mod_root(mod_id: str) -> Path | None:
    return _ROOTS.get(mod_id)


def _package_spec(fullname: str, folder: Path) -> ModuleSpec:
    init_file = folder / "__init__.py"
    if init_file.is_file():
        spec = ModuleSpec(fullname, SourceFileLoader(fullname, str(init_file)), origin=str(init_file), is_package=True)
        spec.has_location = True
    else:
        spec = ModuleSpec(fullname, None, is_package=True)
    spec.submodule_search_locations = [str(folder)]
    return spec


class _ModRootFinder(MetaPathFinder):
    def find_spec(self, fullname: str, path=None, target=None):
        if fullname == "mods":
            # Only when no real `mods` package exists (e.g. pip install of the kernel).
            if _ROOTS and PathFinder.find_spec("mods") is None:
                spec = ModuleSpec("mods", None, is_package=True)
                spec.submodule_search_locations = []
                return spec
            return None
        if not fullname.startswith("mods.") or not _ROOTS:
            return None
        rest = fullname[len("mods."):]
        with _LOCK:
            roots = dict(_ROOTS)

        best: tuple[str, Path] | None = None
        for mod_id, root in roots.items():
            for alias in (mod_id, mod_id.replace(".", "_")):
                if rest == alias or rest.startswith(alias + "."):
                    if best is None or len(alias) > len(best[0]):
                        best = (alias, root)
        if best is not None:
            alias, root = best
            remaining = rest[len(alias):].lstrip(".")
            if not remaining:
                return _package_spec(fullname, root)
            target_path = root.joinpath(*remaining.split("."))
            py_file = target_path.with_suffix(".py")
            if py_file.is_file():
                spec = ModuleSpec(fullname, SourceFileLoader(fullname, str(py_file)), origin=str(py_file))
                spec.has_location = True
                return spec
            if target_path.is_dir():
                return _package_spec(fullname, target_path)
            return None

        # Intermediate namespace (mods.axiom for mods.axiom.time) of a registered mod
        if any(mod_id.startswith(rest + ".") for mod_id in roots):
            spec = ModuleSpec(fullname, None, is_package=True)
            spec.submodule_search_locations = []
            return spec
        return None


_FINDER = _ModRootFinder()


def install_mod_finder() -> None:
    if _FINDER not in sys.meta_path:
        sys.meta_path.insert(0, _FINDER)
