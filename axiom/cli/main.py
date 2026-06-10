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

    dev_p = sub.add_parser(
        "dev", help="Mode dev : surveiller une arborescence source et recompiler à chaud (§7.7)."
    )
    add_dev_arguments(dev_p)
    dev_p.set_defaults(func=run_dev)

    import_p = sub.add_parser(
        "import", help="Importer un .axiom (v1 ou v2) en arborescence source jouable."
    )
    add_import_arguments(import_p)
    import_p.set_defaults(func=run_import)

    populate_p = sub.add_parser(
        "populate", help="Générer du contenu d'univers via LLM (entities/lore/map/…)."
    )
    add_populate_arguments(populate_p)
    populate_p.set_defaults(func=run_populate)

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

    save_edit = sub.add_parser("save-edit", help="Corriger une save existante (édition en place).")
    add_save_edit_arguments(save_edit)
    save_edit.set_defaults(func=run_save_edit)

    save_pack = sub.add_parser("save-pack", help="Exporter une save en archive .axiomsave.")
    add_save_pack_arguments(save_pack)
    save_pack.set_defaults(func=run_save_pack)

    save_unpack = sub.add_parser("save-unpack", help="Importer une archive .axiomsave dans un univers.")
    add_save_unpack_arguments(save_unpack)
    save_unpack.set_defaults(func=run_save_unpack)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée du CLI. Retourne un code de sortie process."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
