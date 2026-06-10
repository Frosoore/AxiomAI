"""axiom.cli.populate_cmd — sous-commande `populate` (authoring LLM headless).

Câblage CLI fin : la logique vit dans `axiom.populate` (migration B3). Comme le
GUI, le résultat atterrit dans le `.db` ET dans la source texte d'un
univers-dossier (TICKET-027). Nécessite un backend LLM configuré.
"""

from __future__ import annotations

import argparse
import sys

TARGET_CHOICES = ("meta", "stats", "entities", "rules", "events", "lore", "map")


def add_populate_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("universe", help="Univers (.db / dossier source / .axiom).")
    parser.add_argument(
        "--target", "-t",
        action="append",
        choices=TARGET_CHOICES,
        required=True,
        help="Quoi générer (répétable : -t entities -t lore).",
    )
    parser.add_argument(
        "--text",
        help="Consigne libre (mode custom) — sinon, inférence depuis le lore existant.",
    )


def run_populate(args: argparse.Namespace) -> int:
    from axiom.backends.base import LLMConnectionError
    from axiom.cli.play import _resolve_playable_db
    from axiom.populate import POPULATE_TARGETS

    db = _resolve_playable_db(args.universe)
    if db is None:
        print(f"Univers introuvable : {args.universe}", file=sys.stderr)
        return 2

    mode = "custom" if args.text else "auto"
    for target in args.target:
        try:
            result = POPULATE_TARGETS[target](
                db, mode, args.text, on_status=lambda msg: print(f"  {msg}"))
        except LLMConnectionError as exc:
            print(f"Erreur LLM ({target}) : {exc}", file=sys.stderr)
            return 1
        print(f"{target} : {result}")
    return 0
