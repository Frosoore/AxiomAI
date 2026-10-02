import os
import pathlib
import pytest
import sys
import types
from pathlib import Path
from PySide6.QtWidgets import QApplication

from axiom import paths as _axiom_paths

# Vrais dossiers de l'utilisateur, figés AVANT tout patch : référence du garde-fou.
_REAL_CONFIG_DIR = _axiom_paths.get_app_config_dir()
_REAL_DATA_DIR = _axiom_paths.get_app_data_dir()
_REAL_CACHE_DIR = _axiom_paths.get_app_cache_dir()
_REPO_ROOT = Path(__file__).resolve().parent.parent

_PROJECT_PACKAGES = {"axiom", "core", "mods", "workers", "ui", "database", "main", "main_web"}
_ISOLATED_NAMES = ("axiom_config", "axiom_data", "axiom_cache")


@pytest.fixture(scope="session", autouse=True)
def q_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


def _snapshot(root: Path, depth: int) -> dict | None:
    """Empreinte (mtime, taille) des entrées de `root` jusqu'à `depth` niveaux."""
    if not root.exists():
        return None
    snap = {}
    stack = [(root, 0)]
    while stack:
        p, d = stack.pop()
        try:
            st = p.stat()
        except OSError:
            continue
        snap[str(p)] = (st.st_mtime_ns, st.st_size)
        if d < depth and p.is_dir():
            try:
                stack.extend((c, d + 1) for c in p.iterdir())
            except OSError:
                pass
    return snap


def _listing(root: Path) -> set[str] | None:
    return {c.name for c in root.iterdir()} if root.is_dir() else None


def _guard_state() -> dict:
    return {
        "config": _snapshot(_REAL_CONFIG_DIR, depth=3),
        "data": _snapshot(_REAL_DATA_DIR, depth=2),
        "repo mods/": _listing(_REPO_ROOT / "mods"),
        "repo dist/mods/": _listing(_REPO_ROOT / "dist" / "mods"),
    }


def _remap(value, real_map, basetemp, tmp_map):
    """Ré-aiguille un Path/str figé sous une vraie racine (ou sous la racine isolée
    d'un test précédent : un module importé pendant un test fige le tmp de ce test)
    vers son équivalent dans le tmp du test courant. None si rien à changer."""
    if isinstance(value, str):
        if not os.path.isabs(value):
            return None
        new = _remap(Path(value), real_map, basetemp, tmp_map)
        return None if new is None else str(new)
    if not isinstance(value, Path) or not value.is_absolute():
        return None
    for old, new in real_map:
        if value == old or old in value.parents:
            return new / value.relative_to(old)
    if basetemp in value.parents:
        parts = value.relative_to(basetemp).parts
        # <basetemp>/<dossier du test>/axiom_xxx/...
        if len(parts) >= 2 and parts[1] in tmp_map:
            new = tmp_map[parts[1]].joinpath(*parts[2:])
            return None if new == value else new
    return None


def _redirect_defaults(monkeypatch, func, maps):
    """Valeurs par défaut figées d'une fonction (ex. `library_dir=UNIVERSES_DIR`)."""
    defaults = getattr(func, "__defaults__", None)
    if defaults:
        new = tuple(_remap(v, *maps) for v in defaults)
        if any(n is not None for n in new):
            monkeypatch.setattr(func, "__defaults__",
                                tuple(o if n is None else n for o, n in zip(defaults, new)))
    kwdefaults = getattr(func, "__kwdefaults__", None)
    if kwdefaults:
        new_kw = {k: _remap(v, *maps) for k, v in kwdefaults.items()}
        if any(n is not None for n in new_kw.values()):
            monkeypatch.setattr(func, "__kwdefaults__",
                                {k: (v if new_kw[k] is None else new_kw[k]) for k, v in kwdefaults.items()})


def _redirect_frozen_constants(monkeypatch, *maps):
    """Patche les chemins figés à l'import (CONFIG_DIR, GLOBAL_DB_FILE, UNIVERSES_DIR…)
    dans les modules du projet déjà chargés : attributs de module, attributs de
    classe et valeurs par défaut des fonctions/méthodes."""
    for name, mod in list(sys.modules.items()):
        if mod is None or name.split(".")[0] not in _PROJECT_PACKAGES:
            continue
        try:
            items = list(vars(mod).items())
        except TypeError:
            continue
        for attr, value in items:
            new = _remap(value, *maps)
            if new is not None:
                monkeypatch.setattr(mod, attr, new)
            elif isinstance(value, types.FunctionType) and value.__module__ == name:
                _redirect_defaults(monkeypatch, value, maps)
            elif isinstance(value, type) and getattr(value, "__module__", None) == name:
                for cattr, cvalue in list(vars(value).items()):
                    cnew = _remap(cvalue, *maps)
                    if cnew is not None:
                        monkeypatch.setattr(value, cattr, cnew)
                        continue
                    func = getattr(cvalue, "__func__", cvalue)
                    if isinstance(func, types.FunctionType):
                        _redirect_defaults(monkeypatch, func, maps)


@pytest.fixture(autouse=True)
def isolated_axiom_data_dir(tmp_path, tmp_path_factory, monkeypatch):
    """Aucun test ne lit ni n'écrit la vraie config (~/.config/AxiomAI), les vraies
    données (~/AxiomAI) ou le vrai cache (~/.cache/AxiomAI) de l'utilisateur.

    - AXIOM_CONFIG_DIR / AXIOM_DATA_DIR pointent vers tmp_path : un test qui fait son
      propre configure() garde la priorité, et un paths.reset() retombe sur l'env.
    - Les constantes figées à l'import (paths.CONFIG_DIR, config.GLOBAL_DB_FILE,
      hub_view.UNIVERSES_DIR…) et Path.home() sont redirigés vers tmp_path.
    - Garde-fou : le test échoue s'il a modifié la vraie config / les vraies données,
      ou ajouté/supprimé une entrée dans `mods/` ou `dist/mods/` du dépôt.
    """
    cfg_dir = tmp_path / "axiom_config"
    data_dir = tmp_path / "axiom_data"
    cache_dir = tmp_path / "axiom_cache"
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    before = _guard_state()

    monkeypatch.setenv("AXIOM_CONFIG_DIR", str(cfg_dir))
    monkeypatch.setenv("AXIOM_DATA_DIR", str(data_dir))
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: cls(fake_home)))

    real_map = [(_REAL_CONFIG_DIR, cfg_dir), (_REAL_CACHE_DIR, cache_dir), (_REAL_DATA_DIR, data_dir)]
    tmp_map = dict(zip(_ISOLATED_NAMES, (cfg_dir, data_dir, cache_dir)))
    _redirect_frozen_constants(monkeypatch, real_map, tmp_path_factory.getbasetemp(), tmp_map)

    _axiom_paths.reset()
    try:
        from axiom import config as _axiom_config
        _axiom_config._CONFIG_CACHE.clear()
    except Exception:
        pass

    yield data_dir

    _axiom_paths.reset()
    after = _guard_state()
    touched = [k for k in before if before[k] != after[k]]
    if touched:
        pytest.fail(
            "Test non hermétique : il a modifié " + ", ".join(touched)
            + f" (config réelle : {_REAL_CONFIG_DIR}, données réelles : {_REAL_DATA_DIR})."
        )


@pytest.fixture
def no_first_launch(monkeypatch):
    """Neutralise le Quick Tour modal de MainWindow (sans settings.json, il bloque le test)."""
    from mods.axiom.ui.qt.ui.main_window import MainWindow
    monkeypatch.setattr(MainWindow, "_check_first_launch", lambda self: None)


@pytest.fixture(autouse=True)
def reset_i18n_cache():
    """Vide le cache i18n (langue courante + tables) avant ET après chaque test.

    `core.localization` met en cache la langue courante (`_CURRENT_LANG`) ; un test
    qui change de langue (ex. test_help_system) la laisserait fuiter vers les tests
    suivants. Sans ce reset, tout test qui lit du texte localisé (ex. le rapport de
    diagnostic) dépendrait de l'ordre d'exécution.
    """
    try:
        from core.localization import reload_translations
        reload_translations()
    except Exception:
        pass
    yield
    try:
        from core.localization import reload_translations
        reload_translations()
    except Exception:
        pass
