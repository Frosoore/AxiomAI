"""axiom.cli.saves_cmd — sous-commandes d'édition de saves (Pilier 2, Phase 6).

Câblage CLI fin : la logique vit dans `axiom.saves`. L'argument `universe` accepte
n'importe quelle forme (.db / dossier source / .axiom) via le résolveur de `play`.
"""

from __future__ import annotations

import argparse
import sys


def _point_args(parser: argparse.ArgumentParser) -> None:
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument("--turn", type=int, metavar="N", help="Target turn N.")
    grp.add_argument("--minute", type=int, metavar="M", help="Target in-game time M (minutes).")


def _resolve_db(universe: str) -> str | None:
    from axiom.cli.play import _resolve_playable_db
    return _resolve_playable_db(universe)


def _resolve_save(universe: str, save_id: str) -> tuple[str | None, str | None]:
    """Résout (base univers, base contenant la save — séparée §7.6 ou embarquée)."""
    from axiom.savestore import resolve_save_db

    universe_db = _resolve_db(universe)
    if universe_db is None:
        return None, None
    return universe_db, resolve_save_db(universe_db, save_id)


# --- save-show -------------------------------------------------------------

def add_save_show_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("universe", help="Universe (.db / source folder / .axiom).")
    parser.add_argument("save_id", help="Save identifier.")
    _point_args(parser)


def run_save_show(args: argparse.Namespace) -> int:
    from axiom.saves import materialize_state, SaveError

    universe_db, db = _resolve_save(args.universe, args.save_id)
    if universe_db is None:
        print(f"Universe not found: {args.universe}", file=sys.stderr)
        return 2
    if db is None:
        print(f"Save {args.save_id} not found in this universe.", file=sys.stderr)
        return 2
    try:
        state = materialize_state(db, args.save_id, at_turn=args.turn, at_minute=args.minute)
    except SaveError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    s = state["save"]
    p = state["point"]
    print(f"Save: {s['player_name']} ({s['difficulty']}) — turn {p['turn_id']}, "
          f"{p['in_game_minutes']} in-game min")
    for eid, stats in state["entities"].items():
        print(f"  {eid}:")
        for k, v in stats.items():
            print(f"    {k} = {v}")
    if state["inventory"]:
        print("  Inventory:")
        for it in state["inventory"]:
            print(f"    {it['entity_id']} × {it['quantity']} {it['item_id']}")
    return 0


# --- save-export -----------------------------------------------------------

def add_save_export_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("universe", help="Universe (.db / source folder / .axiom).")
    parser.add_argument("save_id", help="Save identifier.")
    parser.add_argument("output", help="Path of the save_state.toml to write.")
    _point_args(parser)


def run_save_export(args: argparse.Namespace) -> int:
    from axiom.saves import export_save_state, SaveError

    universe_db, db = _resolve_save(args.universe, args.save_id)
    if universe_db is None:
        print(f"Universe not found: {args.universe}", file=sys.stderr)
        return 2
    if db is None:
        print(f"Save {args.save_id} not found in this universe.", file=sys.stderr)
        return 2
    try:
        out = export_save_state(db, args.save_id, args.output,
                                at_turn=args.turn, at_minute=args.minute)
    except SaveError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Save state exported: {out}")
    return 0


# --- save-import -----------------------------------------------------------

def add_save_import_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("universe", help="Universe (.db / source folder / .axiom).")
    parser.add_argument("state_file", help="The save_state.toml to import.")
    parser.add_argument("--name", help="Player name (otherwise from the file).")


def run_save_import(args: argparse.Namespace) -> int:
    from axiom.saves import import_save_state, SaveError
    from axiom.savestore import (
        SaveStoreError,
        finalize_save_container,
        new_save_container,
    )

    db = _resolve_db(args.universe)
    if db is None:
        print(f"Universe not found: {args.universe}", file=sys.stderr)
        return 2
    try:
        # §7.6 : la save importée naît dans son propre fichier sous saves/.
        container = new_save_container(db)
        save_id = import_save_state(str(container), args.state_file, player_name=args.name)
        final_db = finalize_save_container(container, save_id)
    except (SaveError, SaveStoreError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"New save created: {save_id} ({final_db})")
    return 0


# --- save-edit -------------------------------------------------------------

def add_save_edit_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("universe", help="Universe (.db / source folder / .axiom).")
    parser.add_argument("save_id", help="Save to fix in place.")
    parser.add_argument("patch_file", help="Correction TOML ([state.<id>], [[inventory]], [[modifiers]]).")
    parser.add_argument("--turn", type=int, metavar="N",
                        help="Apply the correction at turn N (default: last turn).")


def run_save_edit(args: argparse.Namespace) -> int:
    from axiom.saves import apply_correction_file, SaveError

    universe_db, db = _resolve_save(args.universe, args.save_id)
    if universe_db is None:
        print(f"Universe not found: {args.universe}", file=sys.stderr)
        return 2
    if db is None:
        print(f"Save {args.save_id} not found in this universe.", file=sys.stderr)
        return 2
    try:
        turn = apply_correction_file(db, args.save_id, args.patch_file, at_turn=args.turn)
    except SaveError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Correction applied (turn {turn}).")
    return 0


# --- save-pack / save-unpack (§7.6 : saves exportables) ----------------------

def add_save_pack_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("universe", help="Universe (.db / source folder / .axiom).")
    parser.add_argument("save_id", help="Save to export.")
    parser.add_argument("output", help="Path of the .axiomsave archive to produce.")


def run_save_pack(args: argparse.Namespace) -> int:
    from axiom.savestore import SaveStoreError, pack_save

    db = _resolve_db(args.universe)
    if db is None:
        print(f"Universe not found: {args.universe}", file=sys.stderr)
        return 2
    try:
        out = pack_save(db, args.save_id, args.output)
    except SaveStoreError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Save exported: {out}")
    return 0


def add_save_unpack_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("universe", help="Destination universe (.db / source folder / .axiom).")
    parser.add_argument("archive", help="The .axiomsave archive to import.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Import even if the archive comes from another universe.",
    )


def run_save_unpack(args: argparse.Namespace) -> int:
    from axiom.savestore import SaveStoreError, unpack_save

    db = _resolve_db(args.universe)
    if db is None:
        print(f"Universe not found: {args.universe}", file=sys.stderr)
        return 2
    try:
        info = unpack_save(args.archive, db, force=args.force)
    except SaveStoreError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Save imported: {info['save_id']} ({info['db_path']})")
    print("Note: vector memory starts empty (it rebuilds as you play).")
    return 0


# --- save-fork -------------------------------------------------------------

def add_save_fork_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("universe", help="Universe (.db / source folder / .axiom).")
    parser.add_argument("save_id", help="Source save to fork.")
    parser.add_argument("--name", help="Player name for the new save.")
    _point_args(parser)


def run_save_fork(args: argparse.Namespace) -> int:
    from axiom.saves import fork_save, SaveError

    universe_db, db = _resolve_save(args.universe, args.save_id)
    if universe_db is None:
        print(f"Universe not found: {args.universe}", file=sys.stderr)
        return 2
    if db is None:
        print(f"Save {args.save_id} not found in this universe.", file=sys.stderr)
        return 2
    try:
        save_id = fork_save(db, args.save_id, at_turn=args.turn,
                            at_minute=args.minute, player_name=args.name)
    except SaveError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Save forked: {save_id}")
    return 0
