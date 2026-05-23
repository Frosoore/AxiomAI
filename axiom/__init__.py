"""axiom — moteur de jeu headless (zéro dépendance Qt).

Extrait de l'app Axiom AI (Pilier 1, réf maintenance/AXIOM_AI_UPGRADE_DETAILS.md §5).

API publique :
    from axiom import Session, Universe
"""

from typing import TYPE_CHECKING

__all__ = ["Session", "Universe"]

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
