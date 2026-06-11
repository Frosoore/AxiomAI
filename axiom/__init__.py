"""axiom — moteur de jeu headless (zéro dépendance Qt).

Extrait de l'app Axiom AI (Pilier 1, réf maintenance/AXIOM_AI_UPGRADE_DETAILS.md §5).

API publique :
    from axiom import Session, Universe
    axiom.help()   # guide de démarrage rapide dans le REPL
"""

from typing import TYPE_CHECKING

# Source de vérité unique de la version du package `axiom-engine`
# (lue par pyproject.toml et par export_engine.py — littéral obligatoire).
__version__ = "0.1.2"

# `help` est volontairement hors de __all__ : un `from axiom import *`
# ne doit pas masquer le help() natif de Python.
__all__ = ["Session", "Universe"]

_HELP_TEXT = """\
================================================================
 Axiom Engine {version} — moteur de jeu narratif piloté par LLM
================================================================
Moteur headless (aucune interface graphique requise) : univers
persistants en SQLite, narration arbitrée par LLM, event-sourcing
(rewind), mémoire vectorielle, modes Normal / Hardcore / Companion.

DÉMARRAGE RAPIDE
    import axiom
    from axiom.config import load_config, build_llm_from_config
    from axiom.db_helpers import create_new_save

    llm = build_llm_from_config(load_config())   # config ~/AxiomAI
    save_id = create_new_save("MonUnivers.db", "Alice", "Normal")

    s = axiom.Session("MonUnivers.db", save_id, llm=llm)
    result = s.take_turn("J'ouvre la porte de la taverne.")
    print(result.narrative_text)

    s.rewind(s.turn_id - 1)        # revenir un tour en arrière
    print(s.current_stats())       # stats matérialisées courantes

EXPLORER UN UNIVERS
    u = axiom.Universe.load("MonUnivers.db")
    print(u.name, u.list_saves())

MODULES UTILES
    axiom.compile / decompile  Universe-as-Code : arbo texte <-> .db
    axiom.package              archives .axiom (export / import)
    axiom.savestore            saves séparées + archives .axiomsave
    axiom.populate             génération de contenu d'univers (LLM)
    axiom.backends             backends LLM (Gemini, Ollama, OpenAI-like)

LIGNE DE COMMANDE
    axiom --help               (ou : python -m axiom.cli --help)
    axiom play <univers>       jouer dans le terminal
    axiom compile / pack / populate / save-*  ...

La config (backend LLM, clés API, modèles) vit dans le dossier de
données AxiomAI (~/AxiomAI par défaut, modifiable via AXIOM_DATA_DIR).
"""


class _Help:
    """`axiom.help` : guide affichable ET appelable (pratique en REPL).

    `axiom.help`, `print(axiom.help)` et `axiom.help()` affichent tous
    le même guide — aucun import lourd n'est déclenché.
    """

    def __call__(self) -> None:
        print(self.__repr__())

    def __repr__(self) -> str:
        return _HELP_TEXT.format(version=f"v{__version__}")


help = _Help()

if TYPE_CHECKING:
    from axiom.session import Session
    from axiom.universe import Universe


def __getattr__(name: str):
    # Exposition paresseuse : `import axiom` reste léger (pas de chromadb/LLM
    # chargés tant qu'on ne touche pas à Session/Universe).
    if name == "Session":
        from axiom.session import Session
        return Session
    if name == "Universe":
        from axiom.universe import Universe
        return Universe
    raise AttributeError(f"module 'axiom' has no attribute {name!r}")
