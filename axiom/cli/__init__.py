"""axiom.cli — interface ligne de commande du moteur Axiom (headless, zéro Qt).

Point d'entrée unique `main()` (dispatch de sous-commandes), pensé pour devenir
le console_script `axiom` une fois le package séparé (Pilier 1, split physique).

Sous-commandes :
    play   — jouer un univers dans le terminal (Pilier 1, Étape 8).
    (compile / test : ajoutées plus tard, Piliers 2 / 10.)

Usage :
    python -m axiom.cli play <univers.axiom>
"""

from axiom.cli.main import main

__all__ = ["main"]
