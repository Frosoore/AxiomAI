"""Tests du packaging pip du moteur (étape feature-packaging-pip).

Couvre : `axiom.__version__` + `axiom.help`, le pyproject racine (n'emballe que
axiom/), et l'utilitaire export_engine.py (bump, export, garde headless).
"""

import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import axiom
import export_engine


# ---------------------------------------------------------------- axiom.help

def test_version_is_semver_literal():
    assert re.fullmatch(r"\d+\.\d+\.\d+", axiom.__version__)


def test_help_repr_is_the_guide():
    text = repr(axiom.help)
    assert "Session" in text
    assert "take_turn" in text
    assert axiom.__version__ in text


def test_help_is_callable_and_prints(capsys):
    axiom.help()
    out = capsys.readouterr().out
    assert "Session" in out
    assert out.strip() == repr(axiom.help).strip()


def test_help_not_exported_by_star_import():
    # `from axiom import *` ne doit pas masquer le help() natif.
    assert "help" not in axiom.__all__


# ------------------------------------------------------------- pyproject.toml

def test_pyproject_packages_only_axiom():
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["name"] == "axiomai-engine"
    include = data["tool"]["setuptools"]["packages"]["find"]["include"]
    assert include == ["axiom*"]
    # Le moteur reste zéro Qt : PySide6 ne doit jamais être une dépendance.
    assert not any("PySide" in dep for dep in data["project"]["dependencies"])
    assert data["project"]["scripts"]["axiom"] == "axiom.cli.main:main"


def test_pyproject_version_is_dynamic_from_init():
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "version" in data["project"]["dynamic"]
    assert data["tool"]["setuptools"]["dynamic"]["version"]["attr"] == "axiom.__version__"


# ------------------------------------------------------------ export_engine

def test_bump_version_parts():
    assert export_engine.bump_version((1, 2, 3), "patch") == (1, 2, 4)
    assert export_engine.bump_version((1, 2, 3), "minor") == (1, 3, 0)
    assert export_engine.bump_version((1, 2, 3), "major") == (2, 0, 0)


def test_read_version_matches_package():
    assert ".".join(map(str, export_engine.read_version())) == axiom.__version__


def test_write_version_preserves_surrounding_lines(tmp_path, monkeypatch):
    fake_init = tmp_path / "__init__.py"
    original = '"""doc"""\n\n__version__ = "1.0.0"\n\n# commentaire suivant\n'
    fake_init.write_text(original, encoding="utf-8")
    monkeypatch.setattr(export_engine, "INIT_FILE", fake_init)

    assert export_engine.write_version((1, 0, 1)) == "1.0.1"
    # Seule la version change — la ligne vide et le commentaire restent intacts.
    assert fake_init.read_text(encoding="utf-8") == original.replace("1.0.0", "1.0.1")


def test_check_headless_engine_is_clean():
    assert export_engine.check_headless(export_engine.ENGINE_DIR) == []


def test_check_headless_detects_app_import(tmp_path):
    bad = tmp_path / "engine"
    bad.mkdir()
    (bad / "leaky.py").write_text("from PySide6.QtCore import QObject\nimport ui\n")
    violations = export_engine.check_headless(bad)
    assert len(violations) == 2
    assert "PySide6" in violations[0]


def test_export_produces_standalone_package(tmp_path):
    dest = tmp_path / "axiomai-engine"
    export_engine.export(dest, axiom.__version__, force=False)

    assert (dest / "axiom" / "__init__.py").exists()
    assert (dest / "axiom" / "cli" / "main.py").exists()
    assert (dest / "pyproject.toml").exists()
    assert (dest / "LICENSE").exists()
    readme = (dest / "README.md").read_text(encoding="utf-8")
    assert axiom.__version__ in readme
    # Rien d'autre que le moteur : pas d'app, pas de caches.
    assert not (dest / "ui").exists()
    assert not list(dest.rglob("__pycache__"))
    assert not list(dest.rglob("*.pyc"))


def test_export_refuses_existing_dir_without_force(tmp_path):
    dest = tmp_path / "axiomai-engine"
    dest.mkdir()
    (dest / "important.txt").write_text("ne pas écraser")
    try:
        export_engine.export(dest, "0.0.0", force=False)
    except SystemExit as exc:
        assert "--force" in str(exc.code)
    else:
        raise AssertionError("export aurait dû refuser d'écraser le dossier")


def test_export_force_refuses_non_export_dir(tmp_path):
    # --force n'écrase QUE ce qui ressemble à un export précédent.
    dest = tmp_path / "mes-photos"
    dest.mkdir()
    (dest / "vacances.jpg").write_text("précieux")
    try:
        export_engine.export(dest, "0.0.0", force=True)
    except SystemExit as exc:
        assert "refuse" in str(exc.code)
    else:
        raise AssertionError("export --force aurait dû refuser un dossier inconnu")


def test_export_force_overwrites_previous_export(tmp_path):
    dest = tmp_path / "axiomai-engine"
    export_engine.export(dest, "0.0.0", force=False)
    export_engine.export(dest, "0.0.0", force=True)  # ne doit pas lever
    assert (dest / "axiom" / "__init__.py").exists()
