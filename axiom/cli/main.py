"""axiom.cli.main — dispatch des sous-commandes du CLI.

`main(argv)` parse les arguments et délègue à la sous-commande. Conçu pour être
le point d'entrée du futur console_script `axiom` (entry point `axiom.cli:main`).
"""

from __future__ import annotations

import argparse

from axiom.cli.compile_cmd import (
    add_compile_arguments,
    add_decompile_arguments,
    add_dev_arguments,
    add_import_arguments,
    add_pack_arguments,
    run_compile,
    run_decompile,
    run_dev,
    run_import,
    run_pack,
)
from axiom.cli.play import add_play_arguments, run_play
from axiom.cli.populate_cmd import add_populate_arguments, run_populate
from axiom.cli.saves_cmd import (
    add_save_edit_arguments,
    add_save_export_arguments,
    add_save_fork_arguments,
    add_save_import_arguments,
    add_save_pack_arguments,
    add_save_show_arguments,
    add_save_unpack_arguments,
    run_save_edit,
    run_save_export,
    run_save_fork,
    run_save_import,
    run_save_pack,
    run_save_show,
    run_save_unpack,
)


def build_parser() -> argparse.ArgumentParser:
    """Construit le parseur d'arguments racine + ses sous-commandes."""
    parser = argparse.ArgumentParser(
        prog="axiom",
        description="Axiom AI — headless command-line game engine.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="Enable debug mode (verbose console output, full log verbosity).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    play = sub.add_parser("play", help="Play a universe in the terminal.")
    add_play_arguments(play)
    play.set_defaults(func=run_play)

    compile_p = sub.add_parser(
        "compile", help="Compile a universe source tree into a .db cache."
    )
    add_compile_arguments(compile_p)
    compile_p.set_defaults(func=run_compile)

    decompile_p = sub.add_parser(
        "decompile", help="Decompile a .db universe into a text source tree."
    )
    add_decompile_arguments(decompile_p)
    decompile_p.set_defaults(func=run_decompile)

    pack_p = sub.add_parser(
        "pack", help="Pack a source tree into a .axiom v2 archive."
    )
    add_pack_arguments(pack_p)
    pack_p.set_defaults(func=run_pack)

    dev_p = sub.add_parser(
        "dev", help="Dev mode: watch a source tree and hot-recompile (§7.7)."
    )
    add_dev_arguments(dev_p)
    dev_p.set_defaults(func=run_dev)

    import_p = sub.add_parser(
        "import", help="Import a .axiom (v1 or v2) into a playable source tree."
    )
    add_import_arguments(import_p)
    import_p.set_defaults(func=run_import)

    populate_p = sub.add_parser(
        "populate", help="Generate universe content via LLM (entities/lore/map/…)."
    )
    add_populate_arguments(populate_p)
    populate_p.set_defaults(func=run_populate)

    save_show = sub.add_parser("save-show", help="Show a save's state at a given point.")
    add_save_show_arguments(save_show)
    save_show.set_defaults(func=run_save_show)

    save_export = sub.add_parser("save-export", help="Export a save to an editable save_state.toml.")
    add_save_export_arguments(save_export)
    save_export.set_defaults(func=run_save_export)

    save_import = sub.add_parser("save-import", help="Create a save from a save_state.toml.")
    add_save_import_arguments(save_import)
    save_import.set_defaults(func=run_save_import)

    save_fork = sub.add_parser("save-fork", help="Fork a save (journal truncated at a point).")
    add_save_fork_arguments(save_fork)
    save_fork.set_defaults(func=run_save_fork)

    save_edit = sub.add_parser("save-edit", help="Fix an existing save (in-place edit).")
    add_save_edit_arguments(save_edit)
    save_edit.set_defaults(func=run_save_edit)

    save_pack = sub.add_parser("save-pack", help="Export a save to a .axiomsave archive.")
    add_save_pack_arguments(save_pack)
    save_pack.set_defaults(func=run_save_pack)

    save_unpack = sub.add_parser("save-unpack", help="Import a .axiomsave archive into a universe.")
    add_save_unpack_arguments(save_unpack)
    save_unpack.set_defaults(func=run_save_unpack)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée du CLI. Retourne un code de sortie process."""
    from axiom.logger import enable_debug_mode

    parser = build_parser()
    args = parser.parse_args(argv)
    if args.debug:
        enable_debug_mode()
    return args.func(args)
