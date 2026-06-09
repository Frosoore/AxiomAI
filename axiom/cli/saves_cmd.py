"""axiom.cli.saves_cmd — sous-commandes d'édition de saves (Pilier 2, Phase 6).

Câblage CLI fin : la logique vit dans `axiom.saves`. L'argument `universe` accepte
n'importe quelle forme (.db / dossier source / .axiom) via le résolveur de `play`.
"""

from __future__ import annotations

import argparse
import sys


def _point_args(parser: argparse.ArgumentParser) -> None:
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument("--turn", type=int, metavar="N", help="Cibler le tour N.")
    grp.add_argument("--minute", type=int, metavar="M", help="Cibler le temps in-game M (minutes).")


def _resolve_db(universe: str) -> str | None:
    from axiom.cli.play import _resolve_playable_db
    return _resolve_playable_db(universe)


# --- save-show -------------------------------------------------------------

def add_save_show_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("universe", help="Univers (.db / dossier source / .axiom).")
    parser.add_argument("save_id", help="Identifiant de la sauvegarde.")
    _point_args(parser)


def run_save_show(args: argparse.Namespace) -> int:
    from axiom.saves import materialize_state, SaveError

    db = _resolve_db(args.universe)
    if db is None:
        print(f"Univers introuvable : {args.universe}", file=sys.stderr)
        return 2
    try:
        state = materialize_state(db, args.save_id, at_turn=args.turn, at_minute=args.minute)
    except SaveError as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1

    s = state["save"]
    p = state["point"]
    print(f"Save : {s['player_name']} ({s['difficulty']}) — tour {p['turn_id']}, "
          f"{p['in_game_minutes']} min in-game")
    for eid, stats in state["entities"].items():
        print(f"  {eid}:")
        for k, v in stats.items():
            print(f"    {k} = {v}")
    if state["inventory"]:
        print("  Inventaire :")
        for it in state["inventory"]:
            print(f"    {it['entity_id']} × {it['quantity']} {it['item_id']}")
    return 0


# --- save-export -----------------------------------------------------------

def add_save_export_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("universe", help="Univers (.db / dossier source / .axiom).")
    parser.add_argument("save_id", help="Identifiant de la sauvegarde.")
    parser.add_argument("output", help="Chemin du save_state.toml à écrire.")
    _point_args(parser)


def run_save_export(args: argparse.Namespace) -> int:
    from axiom.saves import export_save_state, SaveError

    db = _resolve_db(args.universe)
    if db is None:
        print(f"Univers introuvable : {args.universe}", file=sys.stderr)
        return 2
    try:
        out = export_save_state(db, args.save_id, args.output,
                                at_turn=args.turn, at_minute=args.minute)
    except SaveError as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    print(f"État de save exporté : {out}")
    return 0


# --- save-import -----------------------------------------------------------

def add_save_import_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("universe", help="Univers (.db / dossier source / .axiom).")
    parser.add_argument("state_file", help="Le save_state.toml à importer.")
    parser.add_argument("--name", help="Nom du joueur (sinon celui du fichier).")


def run_save_import(args: argparse.Namespace) -> int:
    from axiom.saves import import_save_state, SaveError

    db = _resolve_db(args.universe)
    if db is None:
        print(f"Univers introuvable : {args.universe}", file=sys.stderr)
        return 2
    try:
        save_id = import_save_state(db, args.state_file, player_name=args.name)
    except SaveError as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    print(f"Nouvelle save créée : {save_id}")
    return 0


# --- save-fork -------------------------------------------------------------

def add_save_fork_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("universe", help="Univers (.db / dossier source / .axiom).")
    parser.add_argument("save_id", help="Sauvegarde source à forker.")
    parser.add_argument("--name", help="Nom du joueur de la nouvelle save.")
    _point_args(parser)


def run_save_fork(args: argparse.Namespace) -> int:
    from axiom.saves import fork_save, SaveError

    db = _resolve_db(args.universe)
    if db is None:
        print(f"Univers introuvable : {args.universe}", file=sys.stderr)
        return 2
    try:
        save_id = fork_save(db, args.save_id, at_turn=args.turn,
                            at_minute=args.minute, player_name=args.name)
    except SaveError as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    print(f"Save forkée : {save_id}")
    return 0
