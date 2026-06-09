"""axiom.cli.main — dispatch des sous-commandes du CLI.

`main(argv)` parse les arguments et délègue à la sous-commande. Conçu pour être
le point d'entrée du futur console_script `axiom` (entry point `axiom.cli:main`).
"""

from __future__ import annotations

import argparse

from axiom.cli.compile_cmd import (
    add_compile_arguments,
    add_decompile_arguments,
    add_import_arguments,
    add_pack_arguments,
    run_compile,
    run_decompile,
    run_import,
    run_pack,
)
from axiom.cli.play import add_play_arguments, run_play
from axiom.cli.saves_cmd import (
    add_save_export_arguments,
    add_save_fork_arguments,
    add_save_import_arguments,
    add_save_show_arguments,
    run_save_export,
    run_save_fork,
    run_save_import,
    run_save_show,
)


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

    compile_p = sub.add_parser(
        "compile", help="Compiler une arborescence source d'univers en cache .db."
    )
    add_compile_arguments(compile_p)
    compile_p.set_defaults(func=run_compile)

    decompile_p = sub.add_parser(
        "decompile", help="Décompiler un univers .db en arborescence source texte."
    )
    add_decompile_arguments(decompile_p)
    decompile_p.set_defaults(func=run_decompile)

    pack_p = sub.add_parser(
        "pack", help="Empaqueter une arborescence source en archive .axiom v2."
    )
    add_pack_arguments(pack_p)
    pack_p.set_defaults(func=run_pack)

    import_p = sub.add_parser(
        "import", help="Importer un .axiom (v1 ou v2) en arborescence source jouable."
    )
    add_import_arguments(import_p)
    import_p.set_defaults(func=run_import)

    save_show = sub.add_parser("save-show", help="Afficher l'état d'une sauvegarde à un point.")
    add_save_show_arguments(save_show)
    save_show.set_defaults(func=run_save_show)

    save_export = sub.add_parser("save-export", help="Exporter une save en save_state.toml éditable.")
    add_save_export_arguments(save_export)
    save_export.set_defaults(func=run_save_export)

    save_import = sub.add_parser("save-import", help="Créer une save depuis un save_state.toml.")
    add_save_import_arguments(save_import)
    save_import.set_defaults(func=run_save_import)

    save_fork = sub.add_parser("save-fork", help="Forker une save (journal tronqué à un point).")
    add_save_fork_arguments(save_fork)
    save_fork.set_defaults(func=run_save_fork)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée du CLI. Retourne un code de sortie process."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
