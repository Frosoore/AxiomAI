"""tests/test_test_isolation.py

Garde-fou de l'hermétisme de la suite (revue 2026-10-03, 0-SYNTHESE « Points urgents » 1) :
aucun test ne doit lire ni écrire la vraie config (~/.config/AxiomAI), les vraies données
(~/AxiomAI) ou le vrai cache (~/.cache/AxiomAI) de l'utilisateur. L'isolation est
automatique (fixture autouse `isolated_axiom_data_dir` de conftest.py).
"""

from __future__ import annotations

from pathlib import Path

import pytest

import tests.conftest as conftest
from axiom import paths
from core import bundled_universes  # importé à la collecte : défauts figés sur les vrais dossiers


_REAL_ROOTS = (conftest._REAL_CONFIG_DIR, conftest._REAL_DATA_DIR, conftest._REAL_CACHE_DIR)


def _outside_real_dirs(p: Path) -> bool:
    p = Path(p)
    return all(p != r and r not in p.parents for r in _REAL_ROOTS)


def test_resolved_paths_point_to_tmp(tmp_path: Path) -> None:
    """Toutes les résolutions de chemins (dynamiques ET constantes figées) tombent dans tmp."""
    from axiom import config

    resolved = [
        paths.get_config_dir(),
        paths.get_settings_file(),
        paths.get_global_db_file(),
        paths.get_saves_dir(),
        paths.get_vector_dir(),
        paths.get_assets_dir(),
        paths.get_log_dir(),
        paths.CONFIG_DIR,
        paths.SETTINGS_FILE,
        paths.GLOBAL_DB_FILE,
        paths.DATA_DIR,
        paths.UNIVERSES_DIR,
        paths.SAVES_DIR,
        paths.VECTOR_DIR,
        paths.CACHE_DIR,
        paths.LOG_DIR,
        config._resolve_config_file(),
        config._resolve_global_db_file(),
        config._CONFIG_FILE,
        config.GLOBAL_DB_FILE,
        Path.home(),
    ]
    for p in resolved:
        assert _outside_real_dirs(p), f"{p} pointe vers un vrai dossier de l'utilisateur"
        assert tmp_path in Path(p).parents or Path(p) == tmp_path / "home", p


def test_reset_without_env_still_isolated(monkeypatch) -> None:
    """Même sans AXIOM_CONFIG_DIR (test qui le retire) et après paths.reset(), on reste
    hors du vrai dossier : les constantes figées sont redirigées."""
    monkeypatch.delenv("AXIOM_CONFIG_DIR", raising=False)
    monkeypatch.delenv("AXIOM_DATA_DIR", raising=False)
    paths.reset()
    assert _outside_real_dirs(paths.get_settings_file())
    assert _outside_real_dirs(paths.get_saves_dir())


def test_save_config_writes_in_tmp(tmp_path: Path) -> None:
    """save_config (appelé par l'install `enable=True`, le toggle du dialogue Mods…)
    écrit dans le dossier isolé, jamais dans la vraie settings.json."""
    from axiom.config import AppConfig, load_config, save_config

    cfg = AppConfig()
    cfg.mod_settings["community.isolation_probe"] = {"enabled": False}
    save_config(cfg)

    assert (tmp_path / "axiom_config" / "settings.json").is_file()
    assert load_config().mod_settings["community.isolation_probe"] == {"enabled": False}
    real = conftest._REAL_CONFIG_DIR / "settings.json"
    if real.is_file():
        assert "community.isolation_probe" not in real.read_text(encoding="utf-8")


def test_guard_detects_writes_to_real_config(tmp_path: Path) -> None:
    """L'empreinte utilisée par le garde-fou de conftest change dès qu'un fichier du
    dossier surveillé est modifié ou créé (vérifié sur un faux « vrai » dossier)."""
    fake_real = tmp_path / "fake_real_config"
    fake_real.mkdir()
    (fake_real / "settings.json").write_text("{}", encoding="utf-8")

    before = conftest._snapshot(fake_real, depth=3)
    (fake_real / "settings.json").write_text('{"llm_backend": "x"}', encoding="utf-8")
    assert conftest._snapshot(fake_real, depth=3) != before

    before = conftest._snapshot(fake_real, depth=3)
    (fake_real / "global.db").write_bytes(b"")
    assert conftest._snapshot(fake_real, depth=3) != before

    # Dossier absent puis créé : détecté aussi (cas de la CI, HOME vierge).
    missing = tmp_path / "absent"
    assert conftest._snapshot(missing, depth=3) is None
    missing.mkdir()
    assert conftest._snapshot(missing, depth=3) is not None


@pytest.mark.parametrize("folder", ["mods", "dist/mods"])
def test_guard_watches_repo_mod_folders(folder: str) -> None:
    """Le garde-fou surveille aussi `mods/` et `dist/mods/` du dépôt (pollution par un
    .axmod de test chargé ensuite comme un vrai mod, revue 3-MODS I9)."""
    state = conftest._guard_state()
    key = f"repo {folder}/"
    assert key in state


def test_frozen_function_defaults_redirected() -> None:
    """Les valeurs par défaut figées à l'import (ex. install_bundled_universes(
    library_dir=UNIVERSES_DIR, marker_file=CONFIG_DIR/…)) sont redirigées aussi."""
    import inspect

    sig = inspect.signature(bundled_universes.install_bundled_universes)
    for name in ("library_dir", "marker_file"):
        assert _outside_real_dirs(Path(sig.parameters[name].default)), name
