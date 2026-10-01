"""mods/__init__.py

Package root for mods directory.
Installs a MetaPathFinder allowing dotted mod directories (e.g. mods/axiom.time/, mods/axiom.ui.qt/)
or underscored aliases (e.g. mods/axiom_ui_qt) to be imported seamlessly as packages
(e.g. `import mods.axiom.ui.qt.ui.tabletop_view` or `import mods.axiom_ui_qt.ui.tabletop_view`).
"""

from __future__ import annotations

import sys
from importlib.abc import MetaPathFinder
from importlib.machinery import ModuleSpec, SourceFileLoader
from pathlib import Path


class _DottedModFinder(MetaPathFinder):
    """Import finder mapping `mods.<namespace>.<mod_name>...` or `mods.<mod_id_underscored>...`
    to on-disk folder `mods/<mod_id>/...`."""

    def find_spec(self, fullname: str, path=None, target=None):
        if not fullname.startswith("mods."):
            return None

        parts = fullname.split(".")
        mods_dir = Path(__file__).resolve().parent

        # 1. Try matching candidate mod folder names against disk:
        # Check longest prefix first from parts[1:]
        # e.g. for mods.axiom.ui.qt.ui -> "axiom.ui.qt", then "axiom.ui", then "axiom"
        # and also underscored versions: "axiom_ui_qt" -> "axiom.ui.qt"
        for i in range(len(parts) - 1, 0, -1):
            candidate_dotted = ".".join(parts[1:i + 1])
            candidate_underscored = parts[1].replace("_", ".") if i == 1 else None

            matched_dir = None
            consumed = 0
            if (mods_dir / candidate_dotted).is_dir():
                matched_dir = mods_dir / candidate_dotted
                consumed = i
            elif candidate_underscored and (mods_dir / candidate_underscored).is_dir():
                matched_dir = mods_dir / candidate_underscored
                consumed = 1
            elif (mods_dir / parts[1]).is_dir():
                matched_dir = mods_dir / parts[1]
                consumed = 1

            if matched_dir:
                remaining = parts[consumed + 1:]
                if not remaining:
                    init_file = matched_dir / "__init__.py"
                    has_init = init_file.is_file()
                    loader = SourceFileLoader(fullname, str(init_file)) if has_init else None
                    spec = ModuleSpec(fullname, loader, origin=str(init_file) if has_init else None, is_package=True)
                    spec.submodule_search_locations = [str(matched_dir)]
                    if has_init:
                        spec.has_location = True
                    return spec
                else:
                    target_path = matched_dir.joinpath(*remaining)
                    py_file = target_path.with_suffix(".py")
                    if py_file.is_file():
                        spec = ModuleSpec(fullname, SourceFileLoader(fullname, str(py_file)), origin=str(py_file))
                        spec.has_location = True
                        return spec
                    if target_path.is_dir():
                        init_file = target_path / "__init__.py"
                        has_init = init_file.is_file()
                        loader = SourceFileLoader(fullname, str(init_file)) if has_init else None
                        spec = ModuleSpec(fullname, loader, origin=str(init_file) if has_init else None, is_package=True)
                        spec.submodule_search_locations = [str(target_path)]
                        if has_init:
                            spec.has_location = True
                        return spec

        # Intermediate namespaces like mods.axiom, mods.core, mods.community
        if len(parts) >= 2:
            spec = ModuleSpec(fullname, None, is_package=True)
            spec.submodule_search_locations = [str(mods_dir)]
            return spec

        return None


def install_dotted_mod_finder() -> None:
    """Install the dotted mod finder into sys.meta_path if not already installed."""
    if not any(isinstance(finder, _DottedModFinder) for finder in sys.meta_path):
        sys.meta_path.insert(0, _DottedModFinder())


install_dotted_mod_finder()
