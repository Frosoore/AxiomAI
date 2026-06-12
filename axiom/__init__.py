"""axiom — headless game engine (zero Qt dependency).

Extracted from the Axiom AI desktop app.

Public API::

    from axiom import Session, Universe
    axiom.help()   # quick-start guide right in the REPL
"""

from typing import TYPE_CHECKING

# Source de vérité unique de la version du package `axiom-engine`
# (lue par pyproject.toml et par export_engine.py — littéral obligatoire).
__version__ = "0.1.3"

# `help` est volontairement hors de __all__ : un `from axiom import *`
# ne doit pas masquer le help() natif de Python.
__all__ = ["Session", "Universe"]

_HELP_TEXT = """\
================================================================
 Axiom Engine {version} — LLM-driven narrative game engine
================================================================
Headless engine (no GUI required): persistent SQLite universes,
LLM-arbitrated narration, event sourcing (rewind), vector memory,
Normal / Hardcore / Companion modes.

QUICKSTART
    import axiom
    from axiom.config import load_config, build_llm_from_config
    from axiom.db_helpers import create_new_save

    llm = build_llm_from_config(load_config())   # ~/AxiomAI config
    save_id = create_new_save("MyWorld.db", "Alice", "Normal")

    s = axiom.Session("MyWorld.db", save_id, llm=llm)
    result = s.take_turn("I open the tavern door.")
    print(result.narrative_text)

    s.rewind(s.turn_id - 1)        # go back one turn
    print(s.current_stats())       # current materialised stats

EXPLORE A UNIVERSE
    u = axiom.Universe.load("MyWorld.db")
    print(u.name, u.list_saves())

USEFUL MODULES
    axiom.compile / decompile  Universe-as-Code: text tree <-> .db
    axiom.package              .axiom archives (export / import)
    axiom.savestore            separate saves + .axiomsave archives
    axiom.populate             LLM universe content generation
    axiom.backends             LLM backends (Gemini, Ollama, OpenAI-like)

COMMAND LINE
    axiom --help               (or: python -m axiom.cli --help)
    axiom play <universe>      play in the terminal
    axiom compile / pack / populate / save-*  ...

Configuration (LLM backend, API keys, models) lives in the AxiomAI
data folder (~/AxiomAI by default, overridable via AXIOM_DATA_DIR).

Documentation: https://frosoore.github.io/AxiomAI/
"""


class _Help:
    """`axiom.help`: a guide that is both displayable AND callable (handy in a REPL).

    `axiom.help`, `print(axiom.help)` and `axiom.help()` all show the same
    guide — no heavy import is triggered.
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
