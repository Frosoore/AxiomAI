"""axiom.cli.compile_cmd — sous-commandes `axiom compile` et `axiom decompile`.

Câblage CLI fin du Pilier 2 (Universe-as-Code) : la logique vit dans
`axiom.compile` / `axiom.decompile`, ce module ne fait que parser les args et
afficher le résultat.
"""

from __future__ import annotations

import argparse
import sys


def add_compile_arguments(parser: argparse.ArgumentParser) -> None:
    """Déclare les arguments de `axiom compile`."""
    parser.add_argument("src_dir", help="Dossier source de l'univers (contient universe.toml).")
    parser.add_argument(
        "-o", "--output",
        metavar="DB",
        help="Chemin du .db à produire (défaut : <src_dir>/.axiom-cache/universe.db).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recompiler même si le hash source est inchangé.",
    )


def run_compile(args: argparse.Namespace) -> int:
    """Compile une arborescence source en cache .db."""
    from axiom.compile import compile_universe, CompileError

    try:
        out = compile_universe(args.src_dir, args.output, force=args.force)
    except CompileError as exc:
        print(f"Échec de compilation : {exc}", file=sys.stderr)
        return 1
    print(f"Univers compilé : {out}")
    return 0


def add_pack_arguments(parser: argparse.ArgumentParser) -> None:
    """Déclare les arguments de `axiom pack`."""
    parser.add_argument(
        "source",
        help="Univers à empaqueter : dossier source (universe.toml) ou .db (décompilé à la volée).",
    )
    parser.add_argument("output", help="Chemin de l'archive .axiom à produire.")


def run_pack(args: argparse.Namespace) -> int:
    """Empaquette un univers (arbo source ou .db) en archive .axiom v2."""
    from pathlib import Path

    from axiom.package import export_db_to_axiom, pack_universe, PackageError

    try:
        if Path(args.source).is_file():
            out = export_db_to_axiom(args.source, args.output)
        else:
            out = pack_universe(args.source, args.output)
    except PackageError as exc:
        print(f"Échec du packaging : {exc}", file=sys.stderr)
        return 1
    print(f"Archive créée : {out}")
    return 0


def add_import_arguments(parser: argparse.ArgumentParser) -> None:
    """Déclare les arguments de `axiom import`."""
    parser.add_argument("axiom_file", help="Archive .axiom à importer (v1 ou v2).")
    parser.add_argument(
        "dest_root",
        nargs="?",
        help="Dossier racine de destination (défaut : ~/AxiomAI/universes).",
    )


def run_import(args: argparse.Namespace) -> int:
    """Dépaquette un .axiom (v1/v2) en arborescence source jouable."""
    from axiom.package import unpack_universe, PackageError

    dest_root = args.dest_root
    if dest_root is None:
        from axiom import paths
        dest_root = paths.UNIVERSES_DIR

    try:
        out = unpack_universe(args.axiom_file, dest_root)
    except PackageError as exc:
        print(f"Échec de l'import : {exc}", file=sys.stderr)
        return 1
    print(f"Univers importé : {out}")
    return 0


def add_dev_arguments(parser: argparse.ArgumentParser) -> None:
    """Déclare les arguments de `axiom dev`."""
    parser.add_argument("src_dir", help="Dossier source de l'univers à surveiller.")
    parser.add_argument(
        "--db",
        metavar="DB",
        help="Chemin du .db cible (défaut : <src_dir>/.axiom-cache/universe.db).",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        metavar="S",
        help="Période de polling en secondes (défaut : 1.0).",
    )


def run_dev(args: argparse.Namespace) -> int:
    """Mode dev : watch + recompile in-place de la définition (hot reload)."""
    from pathlib import Path

    from axiom.dev import watch_universe

    if not (Path(args.src_dir) / "universe.toml").exists():
        print(
            f"Arborescence source invalide (pas de universe.toml) : {args.src_dir}",
            file=sys.stderr,
        )
        return 1

    # flush=True : les événements doivent apparaître immédiatement, même si
    # stdout est redirigé (sinon ils restent dans le buffer process).
    print(f"Mode dev — surveillance de {args.src_dir} (Ctrl-C pour arrêter)", flush=True)
    try:
        watch_universe(
            args.src_dir,
            args.db,
            interval=args.interval,
            on_event=lambda msg: print(msg, flush=True),
        )
    except KeyboardInterrupt:
        print("\nArrêt du mode dev.")
    return 0


def add_decompile_arguments(parser: argparse.ArgumentParser) -> None:
    """Déclare les arguments de `axiom decompile`."""
    parser.add_argument("db_path", help="Chemin du .db univers à décompiler.")
    parser.add_argument("output_dir", help="Dossier de destination de l'arborescence texte.")


def run_decompile(args: argparse.Namespace) -> int:
    """Décompile un .db en arborescence source texte."""
    from axiom.decompile import decompile_universe, DecompileError

    try:
        out = decompile_universe(args.db_path, args.output_dir)
    except DecompileError as exc:
        print(f"Échec de décompilation : {exc}", file=sys.stderr)
        return 1
    print(f"Univers décompilé : {out}")
    return 0
