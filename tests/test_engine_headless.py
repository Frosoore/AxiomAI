"""
tests/test_engine_headless.py

Test de garde de la frontière moteur/app : importer le package moteur `axiom`
ne doit JAMAIS charger Qt (PySide6).

C'est l'invariant central de l'extraction (Pilier 1) : `axiom/` est headless et
ne dépend que de stdlib + libs moteur (LLM, chromadb…), jamais de `ui/` ni
`workers/`. Un import retour accidentel (`axiom` -> `ui`/`workers` -> PySide6)
casserait le CLI, les tests headless et la future distribution.

On vérifie dans un interpréteur frais (sous-process) : si un autre test du même
process a déjà chargé PySide6, `sys.modules` serait pollué et le test perdrait
son sens.
"""

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Modules moteur représentatifs : la façade publique, la boucle de tour, le
# Chronicler, les backends et le CLI. Si l'un d'eux tire Qt, le test échoue.
_ENGINE_IMPORTS = (
    "import axiom",
    "from axiom import Session, Universe",
    "import axiom.session, axiom.arbitrator, axiom.chronicler, axiom.rules",
    "import axiom.events, axiom.checkpoint, axiom.modifiers, axiom.memory",
    "import axiom.config, axiom.prompts, axiom.db_helpers",
    "import axiom.backends.base, axiom.backends.gemini",
    "import axiom.cli.main, axiom.cli.play",
)


def test_importing_engine_does_not_load_qt():
    """`import axiom` (+ ses sous-modules) ne doit pas charger PySide6."""
    script = (
        "import sys\n"
        + "\n".join(_ENGINE_IMPORTS)
        + "\n"
        "qt = sorted(m for m in sys.modules if m.split('.')[0] in ('PySide6', 'PyQt5', 'PyQt6', 'shiboken6'))\n"
        "assert not qt, 'Le moteur a chargé Qt : ' + ', '.join(qt)\n"
        "print('OK headless')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        "Frontière moteur/app violée : importer `axiom` charge Qt "
        "(import retour axiom -> ui/workers ?).\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
    assert "OK headless" in result.stdout
