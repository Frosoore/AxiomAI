"""tests/test_kernel_discovery_and_archives.py

Discovery and archives (review 2026-10-03, 1-NOYAU I7, I8, m9):
- discovery does not depend on the current directory, never reads `dist/`;
- the user mods folder comes from `axiom.paths.get_mods_dir()`;
- a multi-file `.axmod` loads without its sources on disk (relative imports and
  `mods.<id>.<module>` imports);
- the `mods` package finder raises ImportError for unknown names;
- a missing pip package is visible in `axiom mods list`.
"""

from __future__ import annotations

import argparse
import io
import os
import sys
from pathlib import Path

import pytest

from axiom.config import AppConfig
from axiom.kernel import (
    KernelRegistry,
    bootstrap_all_mods,
    discover_mods,
    get_load_state,
    get_user_mods_dir,
    load_mod_from_archive,
    plan_modpack,
    reset_kernel_registry,
    set_safe_mode,
)
from axiom.paths import get_mods_dir

REPO_ROOT = Path(__file__).resolve().parent.parent


def _write(base: Path, mod_id: str, extra: str = "", files: dict[str, str] | None = None) -> Path:
    d = base / mod_id
    d.mkdir(parents=True)
    (d / "mod.toml").write_text(
        f'[mod]\nid = "{mod_id}"\nversion = "1.0.0"\naxiom_api = 1\n{extra}', encoding="utf-8"
    )
    for name, content in (files or {}).items():
        (d / name).parent.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(content, encoding="utf-8")
    return d


@pytest.fixture
def clean_state():
    set_safe_mode(False)
    reset_kernel_registry()
    yield
    reset_kernel_registry()


def test_discovery_is_independent_of_cwd_and_ignores_dist(tmp_path, monkeypatch, clean_state):
    monkeypatch.delenv("AXIOM_OFFICIAL_MODS_DIR", raising=False)
    user = get_user_mods_dir()
    assert user == get_mods_dir().resolve()
    assert os.environ["AXIOM_DATA_DIR"] in str(user)  # isolated by conftest
    _write(user, "user.thing", files={"main.py": "def init(ctx):\n    ctx.register_service('user_thing', 1)\n"})

    elsewhere = tmp_path / "elsewhere"
    (elsewhere / "dist" / "mods").mkdir(parents=True)
    _write(elsewhere / "dist" / "mods", "dist.artefact")
    _write(elsewhere / "mods", "cwd.mod")
    monkeypatch.chdir(elsewhere)

    ids = {m.id for m, _ in discover_mods()}
    assert "axiom.turn" in ids and "axiom.world" in ids  # official mods, found from anywhere
    assert "user.thing" in ids
    assert "dist.artefact" not in ids and "cwd.mod" not in ids
    # the qt symlink alias is not discovered as a second copy
    paths = [p for m, p in discover_mods() if m.id == "axiom.ui.qt"]
    assert len(paths) == 1


def test_scaffold_and_store_default_to_user_mods_dir(tmp_path, monkeypatch):
    import inspect
    from axiom.kernel import store
    from axiom.kernel.scaffold import scaffold_mod

    monkeypatch.chdir(tmp_path)
    created = scaffold_mod("author.defaultdir")
    assert created == get_user_mods_dir() / "author.defaultdir"
    assert not (REPO_ROOT / "mods" / "author.defaultdir").exists()
    assert inspect.signature(store.install_mod_from_store).parameters["dest_dir"].default is None


MULTI_MAIN = """
from . import helpers
from mods.multi.pack.deep.engine import power


def init(ctx):
    ctx.register_service("multi", helpers.answer() + power())
"""


def test_multi_file_axmod_loads_without_sources(tmp_path, clean_state):
    from axiom.cli.mods_cmd import pack_mod

    src = _write(tmp_path / "src", "multi.pack", files={
        "main.py": MULTI_MAIN,
        "helpers.py": "def answer():\n    return 40\n",
        "deep/__init__.py": "",
        "deep/engine.py": "def power():\n    return 2\n",
    })
    archive = pack_mod(src, tmp_path / "out" / "multi.pack.axmod")
    import shutil
    shutil.rmtree(src)  # no sources anywhere on disk

    for name in [n for n in sys.modules if n.startswith("mods.multi") or n.startswith("axiom_mod_multi")]:
        sys.modules.pop(name)
    reg = KernelRegistry()
    manifest, ctx, module = load_mod_from_archive(archive, reg, AppConfig())
    assert manifest.id == "multi.pack" and ctx is not None
    assert reg.get_service("multi") == 42


def test_axmod_with_unsafe_member_is_refused(tmp_path, clean_state):
    import zipfile
    from axiom.kernel import ModLoadError

    archive = tmp_path / "evil.axmod"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("mod.toml", '[mod]\nid = "evil.zip"\nversion = "1.0.0"\naxiom_api = 1\n')
        zf.writestr("../../escaped.py", "x = 1\n")
    with pytest.raises(ModLoadError, match="Unsafe path"):
        load_mod_from_archive(archive, KernelRegistry(), AppConfig())
    assert not (tmp_path.parent / "escaped.py").exists()


def test_mods_finder_raises_import_error_for_unknown_names():
    import mods  # noqa: F401
    with pytest.raises(ImportError):
        import mods.does_not_exist.at_all  # noqa: F401
    with pytest.raises(ImportError):
        import mods.axiom.time.no_such_module  # noqa: F401
    import mods.axiom.help_system.ui.help_system as ok  # still works
    assert ok.__name__ == "mods.axiom.help_system.ui.help_system"


def test_missing_python_dependency_visible_in_mods_list(tmp_path, monkeypatch, clean_state):
    from axiom.cli.mods_cmd import run_mod_list
    import axiom.config as config_mod

    official = tmp_path / "official"
    official.mkdir()
    monkeypatch.setenv("AXIOM_OFFICIAL_MODS_DIR", str(official))
    _write(official, "needs.pip", '[python]\nrequires = ["surely-not-installed-pkg-xyz>=1.0"]\n')
    _write(official, "needs.parent", '[dependencies]\n"needs.pip" = "*"\n')
    cfg = AppConfig()
    monkeypatch.setattr(config_mod, "load_config", lambda *a, **k: cfg)

    plan = plan_modpack(config=cfg)
    assert plan.statuses["needs.pip"].state == "missing_python_deps"
    assert plan.statuses["needs.parent"].state == "rejected"

    reg = bootstrap_all_mods(KernelRegistry(), cfg)
    assert get_load_state(reg).get_status("needs.pip").state == "missing_python_deps"

    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    run_mod_list(argparse.Namespace())
    out = buf.getvalue()
    assert "missing_python_deps" in out and "surely-not-installed-pkg-xyz" in out
