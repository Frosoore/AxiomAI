#!/usr/bin/env python3
"""export_engine.py — exporte le moteur `axiom/` en package PyPI-ready.

Clone le moteur (et uniquement lui) dans un dossier autonome qu'on peut
construire et publier tel quel sur PyPI, sans rien changer au repo :

    dist/axiomai-engine/
    ├── axiom/            (copie du moteur, sans __pycache__)
    ├── pyproject.toml    (copie de celui du repo)
    ├── LICENSE
    ├── NOTICE            (copyright + obligation de citation, GPLv3 §7(b))
    └── README.md         (README spécifique librairie, généré)

Usage :
    python export_engine.py                      # export simple dans dist/axiomai-engine/
    python export_engine.py --bump patch        # 0.1.0 -> 0.1.1 (réécrit axiom/__init__.py) puis export
    python export_engine.py --bump minor        # 0.1.0 -> 0.2.0
    python export_engine.py --bump major        # 0.1.0 -> 1.0.0
    python export_engine.py --set-version 1.2.3 # version explicite
    python export_engine.py --build             # + construit sdist et wheel dans l'export
    python export_engine.py mon/dossier --force # destination custom, écrase l'export précédent

La version vit dans `axiom/__init__.py::__version__` (source de vérité unique) :
un bump modifie le repo PUIS exporte, pour que repo et package restent alignés.

Garde anti-fuite : l'export échoue si un fichier du moteur importe l'app
(PySide6/PyQt, ui, workers, core, database) — le contrat « moteur headless »
est vérifié à chaque export.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
ENGINE_DIR = REPO_ROOT / "axiom"
INIT_FILE = ENGINE_DIR / "__init__.py"
DEFAULT_DEST = REPO_ROOT / "dist" / "axiomai-engine"

_VERSION_RE = re.compile(r'^__version__\s*=\s*"(\d+)\.(\d+)\.(\d+)"[ \t]*$', re.MULTILINE)

# Imports interdits dans le moteur (= dépendances vers l'app Qt ou le reste du repo).
_FORBIDDEN_IMPORT_RE = re.compile(
    r"^\s*(?:from|import)\s+(PySide6|PyQt[456]?|ui|workers|core|database)\b",
    re.MULTILINE,
)

_README_TEMPLATE = """\
# axiomai-engine

Moteur de jeu narratif piloté par LLM, **headless** (aucune interface graphique requise).

- Univers persistants en SQLite, versionnables en arborescence texte (« Universe-as-Code »)
- Narration arbitrée par LLM (Gemini, Ollama, ou tout endpoint OpenAI-compatible)
- Event-sourcing : chaque tour est rejouable, le temps de jeu est *rembobinable* (`rewind`)
- Mémoire vectorielle long-terme (ChromaDB + sentence-transformers)
- Modes de jeu : Normal, Hardcore (mort permanente), Companion (héros co-piloté par IA)
- CLI complet : `axiom play`, `axiom compile`, `axiom populate`, `axiom save-*` …

## Installation

```bash
pip install axiomai-engine
```

## Démarrage rapide

```python
import axiom
axiom.help()   # guide intégré : API, modules, CLI
```

```python
from axiom.config import load_config, build_llm_from_config
from axiom.db_helpers import create_new_save

llm = build_llm_from_config(load_config())
save_id = create_new_save("MonUnivers.db", "Alice", "Normal")

s = axiom.Session("MonUnivers.db", save_id, llm=llm)
result = s.take_turn("J'ouvre la porte de la taverne.")
print(result.narrative_text)
```

## Projet

Code source, application graphique (vitrine du moteur) et suivi des bugs :
**https://github.com/Frosoore/AxiomAI**

## Licence

AGPL-3.0-or-later — voir `LICENSE`. Citation de l'origine requise en cas de
redistribution (terme additionnel AGPLv3 §7(b)) — voir `NOTICE`.

*Ce package est développé dans le mono-repo [Axiom AI](https://github.com/Frosoore/AxiomAI),
dont l'application graphique sert de vitrine au moteur. Version {version}.*
"""


def read_version() -> tuple[int, int, int]:
    """Lit la version actuelle dans axiom/__init__.py. Échoue si introuvable."""
    match = _VERSION_RE.search(INIT_FILE.read_text(encoding="utf-8"))
    if not match:
        sys.exit(f"ERREUR : __version__ = \"X.Y.Z\" introuvable dans {INIT_FILE}")
    return tuple(int(p) for p in match.groups())  # type: ignore[return-value]


def bump_version(current: tuple[int, int, int], part: str) -> tuple[int, int, int]:
    """Incrémente la partie demandée (les parties plus fines repartent à 0)."""
    major, minor, patch = current
    if part == "major":
        return (major + 1, 0, 0)
    if part == "minor":
        return (major, minor + 1, 0)
    return (major, minor, patch + 1)


def write_version(version: tuple[int, int, int]) -> str:
    """Réécrit __version__ dans axiom/__init__.py (repo = source de vérité)."""
    text = INIT_FILE.read_text(encoding="utf-8")
    version_str = ".".join(str(p) for p in version)
    new_text = _VERSION_RE.sub(f'__version__ = "{version_str}"', text, count=1)
    INIT_FILE.write_text(new_text, encoding="utf-8")
    return version_str


def check_headless(engine_dir: Path) -> list[str]:
    """Retourne les violations « import app » trouvées dans le moteur."""
    violations = []
    for py_file in sorted(engine_dir.rglob("*.py")):
        if "__pycache__" in py_file.parts:
            continue
        for match in _FORBIDDEN_IMPORT_RE.finditer(py_file.read_text(encoding="utf-8")):
            rel = py_file.relative_to(engine_dir.parent)
            violations.append(f"{rel}: {match.group(0).strip()}")
    return violations


def export(dest: Path, version_str: str, force: bool) -> None:
    """Copie axiom/ + pyproject.toml + LICENSE + README librairie dans `dest`."""
    if dest.exists():
        if not force:
            sys.exit(
                f"ERREUR : {dest} existe déjà. Relance avec --force pour l'écraser."
            )
        # Garde-fou : on n'écrase que ce qui ressemble à un export précédent.
        if not (dest / "pyproject.toml").exists() and any(dest.iterdir()):
            sys.exit(
                f"ERREUR : {dest} n'est pas vide et ne ressemble pas à un export "
                "précédent (pas de pyproject.toml) — je refuse de l'écraser."
            )
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    shutil.copytree(
        ENGINE_DIR,
        dest / "axiom",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    shutil.copy2(REPO_ROOT / "pyproject.toml", dest / "pyproject.toml")
    shutil.copy2(REPO_ROOT / "LICENSE", dest / "LICENSE")
    shutil.copy2(REPO_ROOT / "NOTICE", dest / "NOTICE")
    (dest / "README.md").write_text(
        _README_TEMPLATE.format(version=version_str), encoding="utf-8"
    )


def build_dist(dest: Path) -> bool:
    """Construit sdist + wheel dans dest/dist/. Retourne True si OK."""
    try:
        import build  # noqa: F401
    except ImportError:
        print(
            "\n[--build] le module 'build' n'est pas installé "
            f"({sys.executable} -m pip install build), construction sautée."
        )
        return False
    result = subprocess.run(
        [sys.executable, "-m", "build", "--sdist", "--wheel", str(dest)],
        cwd=dest,
    )
    return result.returncode == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Exporte le moteur axiom/ en package PyPI-ready autonome.",
    )
    parser.add_argument(
        "dest",
        nargs="?",
        default=str(DEFAULT_DEST),
        help=f"Dossier de destination (défaut : {DEFAULT_DEST.relative_to(REPO_ROOT)}/)",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--bump",
        choices=("patch", "minor", "major"),
        help="Incrémente la version dans axiom/__init__.py avant l'export.",
    )
    group.add_argument(
        "--set-version",
        metavar="X.Y.Z",
        help="Fixe explicitement la version avant l'export.",
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help="Construit aussi sdist + wheel dans l'export (module 'build' requis).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Écrase un export précédent à la même destination.",
    )
    args = parser.parse_args(argv)

    # 1. Garde headless — on n'exporte jamais un moteur qui fuit vers l'app.
    violations = check_headless(ENGINE_DIR)
    if violations:
        print("ERREUR : le moteur importe du code de l'app — export refusé :")
        for v in violations:
            print(f"  - {v}")
        return 1

    # 2. Versionnement (source de vérité : axiom/__init__.py, dans le repo).
    current = read_version()
    if args.set_version:
        if not re.fullmatch(r"\d+\.\d+\.\d+", args.set_version):
            sys.exit(f"ERREUR : version invalide {args.set_version!r} (attendu X.Y.Z)")
        version_str = write_version(tuple(int(p) for p in args.set_version.split(".")))
    elif args.bump:
        version_str = write_version(bump_version(current, args.bump))
    else:
        version_str = ".".join(str(p) for p in current)
    if args.bump or args.set_version:
        print(f"Version : {'.'.join(str(p) for p in current)} -> {version_str} "
              f"(écrit dans {INIT_FILE.relative_to(REPO_ROOT)})")

    # 3. Export.
    dest = Path(args.dest).resolve()
    export(dest, version_str, force=args.force)
    print(f"Moteur exporté dans : {dest}")

    # 4. Build optionnel.
    built = build_dist(dest) if args.build else False

    # 5. Prochaines étapes.
    print("\nProchaines étapes pour publier sur PyPI :")
    if not built:
        print(f"  cd {dest}")
        print("  python -m build          # construit dist/*.tar.gz et dist/*.whl")
    print(f"  python -m twine check {dest / 'dist'}/*")
    print(f"  python -m twine upload {dest / 'dist'}/*   # compte PyPI + token requis")
    print("\nTest local sans publier :")
    print(f"  pip install {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
