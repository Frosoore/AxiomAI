"""axiom.cli.main — dispatch des sous-commandes du CLI.

`main(argv)` parse les arguments et délègue à la sous-commande. Conçu pour être
le point d'entrée du futur console_script `axiom` (entry point `axiom.cli:main`).
"""

from __future__ import annotations

import argparse

from axiom.cli.play import add_play_arguments, run_play


def build_parser() -> argparse.ArgumentParser:
    """Construit le parseur d'arguments racine + ses sous-commandes."""
    parser = argparse.ArgumentParser(
        prog="axiom",
        description="Axiom AI — moteur de jeu en ligne de commande (headless).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    play = sub.add_parser("play", help="Jouer un univers dans le terminal.")
    add_play_arguments(play)
    play.set_defaults(func=run_play)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée du CLI. Retourne un code de sortie process."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
