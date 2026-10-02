"""axiom/kernel/tester.py

Unified mod testing and structural verification engine (`axiom mod test`).
Validates manifest, hook/slot declarations, forbidden UI imports (Rule D4),
and executes pytest test suites in an isolated subprocess.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any
import zipfile

from axiom.kernel.context import ModContext
from axiom.kernel.manifest import ManifestError, ModManifest, load_manifest
from axiom.kernel.registry import KernelRegistry
from axiom.logger import logger


_HOOK_SLOT_NAME_REGEX = re.compile(r"^[a-zA-Z0-9_.-]+:[a-zA-Z0-9_.-]+$")

_FORBIDDEN_UI_MODULES = {
    "PySide6",
    "PySide2",
    "PyQt6",
    "PyQt5",
    "ui",
    "main_web",
}

# ctx methods whose first literal argument names a hook / a slot
_HOOK_CALLS = {"register_hook"}
_SLOT_CALLS = {"contribute_slot"}


@dataclass
class ModTestResult:
    """Outcome of testing and validating a mod."""

    passed: bool
    manifest: ModManifest | None
    errors: list[str] = field(default_factory=list)
    pytest_output: str = ""


def _scan_for_forbidden_ui_imports(py_file: Path) -> list[str]:
    """Scan a Python file for direct imports of UI packages without declared dependency."""
    violations: list[str] = []
    try:
        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(py_file))
    except Exception as err:
        violations.append(f"Syntax error reading {py_file.name}: {err}")
        return violations

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_pkg = alias.name.split(".")[0]
                if root_pkg in _FORBIDDEN_UI_MODULES:
                    violations.append(
                        f"Line {node.lineno}: forbidden UI import 'import {alias.name}'"
                    )
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root_pkg = node.module.split(".")[0]
                if root_pkg in _FORBIDDEN_UI_MODULES:
                    violations.append(
                        f"Line {node.lineno}: forbidden UI import 'from {node.module} import ...'"
                    )
    return violations


def _scan_extension_point_calls(py_file: Path) -> list[tuple[str, str, int]]:
    """Return (kind, name, line) for ctx.register_hook("...") / ctx.contribute_slot("...") literals."""
    found: list[tuple[str, str, int]] = []
    try:
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    except Exception:
        return found
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        attr = node.func.attr
        kind = "hook" if attr in _HOOK_CALLS else "slot" if attr in _SLOT_CALLS else None
        if kind is None or not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            found.append((kind, first.value, node.lineno))
    return found


def validate_mod_static(target_dir: Path | str) -> ModTestResult:
    """Validate an unpacked mod WITHOUT executing any of its code.

    Checks the manifest (namespaced id, SemVer, kernel API, dependency specs), the
    syntax of every .py file (AST), the hook/slot names declared in the manifest and
    used literally in the code against the public catalogue (`axiom.kernel.api`), and
    forbidden UI imports (Rule D4).
    """
    from axiom.kernel.api import KERNEL_API, check_extension_point

    target_dir = Path(target_dir).resolve()
    errors: list[str] = []
    try:
        manifest = load_manifest(target_dir)
    except ManifestError as err:
        return ModTestResult(passed=False, manifest=None, errors=[f"Manifest error: {err}"])
    except Exception as err:
        return ModTestResult(passed=False, manifest=None, errors=[f"Unexpected manifest failure: {err}"])

    if manifest.axiom_api != KERNEL_API:
        errors.append(f"Manifest requires axiom_api={manifest.axiom_api}; this kernel provides {KERNEL_API}.")

    own_slots = frozenset(manifest.provides_slots)
    for hook_name in manifest.contributes.hooks:
        msg = check_extension_point(hook_name, "hook", own_slots)
        if msg:
            errors.append(f"mod.toml [contributes].hooks: {msg}")
    for slot_name in manifest.contributes.slots:
        msg = check_extension_point(slot_name, "slot", own_slots)
        if msg:
            errors.append(f"mod.toml [contributes].slots: {msg}")

    for py_file in sorted(target_dir.rglob("*.py")):
        rel = py_file.relative_to(target_dir).as_posix()
        try:
            ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except SyntaxError as err:
            errors.append(f"Syntax error in '{rel}' line {err.lineno}: {err.msg}")
            continue
        except Exception as err:
            errors.append(f"Cannot read '{rel}': {err}")
            continue
        if "tests" in py_file.relative_to(target_dir).parts:
            continue
        for kind, name, line in _scan_extension_point_calls(py_file):
            msg = check_extension_point(name, kind, own_slots)
            if msg:
                errors.append(f"'{rel}' line {line}: {msg}")

    errors.extend(_check_ui_imports(target_dir, manifest))
    return ModTestResult(passed=not errors, manifest=manifest, errors=errors)


def _check_ui_imports(target_dir: Path, manifest: ModManifest) -> list[str]:
    """Rule D4: no UI import unless an explicit UI mod dependency is declared."""
    errors: list[str] = []
    has_ui_dep = any(dep_id.startswith("axiom.ui.") for dep_id in manifest.dependencies)
    if has_ui_dep:
        return errors
    for py_file in target_dir.rglob("*.py"):
        # Exclude tests folder from UI import check if tests need test client
        if "tests" in py_file.relative_to(target_dir).parts:
            continue
        for v in _scan_for_forbidden_ui_imports(py_file):
            rel = py_file.relative_to(target_dir).as_posix()
            errors.append(
                f"Forbidden UI dependency violation in '{rel}': {v} "
                f"(Rule D4: Declare an explicit UI dependency in mod.toml if UI is required)."
            )
    return errors


def test_mod(mod_path: Path | str) -> ModTestResult:
    """Test and validate a mod directory or .axmod archive.

    Checks:
      1. Manifest parsing and SemVer validation.
      2. Hooks/slots declared or used are real public extension points (no unknown
         `axiom.*` name), every .py file parses.
      3. Absence of forbidden UI imports (Rule D4) unless UI dependencies are declared.
      4. Runtime initialization inside an isolated ModContext (EXECUTES the mod's code).
      5. Execution of pytest suite inside tests/ if present (EXECUTES the tests).

    For code that must not run yet (e.g. LLM-generated, before confirmation), use
    `validate_mod_static()` instead.

    Returns:
        ModTestResult with pass/fail status, errors, and test output.
    """
    path = Path(mod_path).resolve()
    if not path.exists():
        return ModTestResult(
            passed=False,
            manifest=None,
            errors=[f"Target path does not exist: {path}"],
        )

    errors: list[str] = []

    # If it's a file, check if it's an .axmod archive
    if path.is_file():
        if path.suffix.lower() not in (".axmod", ".zip"):
            return ModTestResult(
                passed=False,
                manifest=None,
                errors=[f"Unsupported mod file extension: {path.name} (expected .axmod)"],
            )
        # Unpack archive into temporary directory for structural and pytest inspection
        temp_dir = tempfile.TemporaryDirectory()
        try:
            with zipfile.ZipFile(path, "r") as zf:
                zf.extractall(temp_dir.name)
            target_dir = Path(temp_dir.name)
            return _test_mod_directory(target_dir, is_archive=True, original_path=path)
        finally:
            temp_dir.cleanup()
    else:
        return _test_mod_directory(path, is_archive=False, original_path=path)


def _test_mod_directory(
    target_dir: Path,
    is_archive: bool = False,
    original_path: Path | None = None,
) -> ModTestResult:
    """Internal test runner for an unpacked mod directory."""
    errors: list[str] = []
    manifest: ModManifest | None = None

    # 1-3. Static validation (manifest, names of hooks/slots, AST, UI imports)
    static = validate_mod_static(target_dir)
    if static.manifest is None:
        return static
    manifest = static.manifest
    errors.extend(static.errors)

    # 4. Runtime load & init check
    main_py = target_dir / "main.py"
    if main_py.is_file():
        registry = KernelRegistry()
        ctx = ModContext(manifest, registry)
        module_name = f"test_load_mod_{manifest.id.replace('.', '_')}"

        try:
            spec = importlib.util.spec_from_file_location(
                module_name, main_py, submodule_search_locations=[str(target_dir)]
            )
            if spec is None or spec.loader is None:
                errors.append(f"Cannot load module spec for {main_py}")
            else:
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)

                if hasattr(module, "init") and callable(module.init):
                    module.init(ctx)
        except Exception as err:
            errors.append(f"Runtime initialization init(ctx) error: {err}")
        finally:
            ctx.cleanup()
            for name in [n for n in sys.modules if n == module_name or n.startswith(module_name + ".")]:
                sys.modules.pop(name, None)

    # 5. Execute test suite if tests/ directory exists
    tests_dir = target_dir / "tests"
    pytest_output = ""
    has_tests = tests_dir.is_dir() and any(
        f.suffix == ".py" and (f.name.startswith("test_") or f.name.endswith("_test.py"))
        for f in tests_dir.iterdir()
    )

    if has_tests:
        project_root = Path(__file__).resolve().parent.parent.parent
        env = dict(os.environ)
        # Ensure AxiomAI project root is on PYTHONPATH
        current_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            f"{project_root}{os.pathsep}{current_pythonpath}"
            if current_pythonpath
            else str(project_root)
        )

        cmd = [
            sys.executable,
            "-m",
            "pytest",
            str(tests_dir),
            "-q",
            "--no-header",
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                env=env,
                cwd=str(project_root),
            )
            pytest_output = proc.stdout + ("\n" + proc.stderr if proc.stderr else "")
            if proc.returncode != 0:
                errors.append(
                    f"Unit tests in '{tests_dir.name}' failed with return code {proc.returncode}."
                )
        except subprocess.TimeoutExpired:
            errors.append("Unit tests timed out after 60 seconds.")
        except Exception as err:
            errors.append(f"Failed to execute pytest on '{tests_dir}': {err}")

    passed = len(errors) == 0
    return ModTestResult(
        passed=passed,
        manifest=manifest,
        errors=errors,
        pytest_output=pytest_output,
    )


test_mod.__test__ = False  # Prevent pytest from treating this engine function as a test

