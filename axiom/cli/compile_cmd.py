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
    parser.add_argument("src_dir", help="Universe source folder (contains universe.toml).")
    parser.add_argument(
        "-o", "--output",
        metavar="DB",
        help="Path of the .db to produce (default: <src_dir>/.axiom-cache/universe.db).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recompile even if the source hash is unchanged.",
    )


def run_compile(args: argparse.Namespace) -> int:
    """Compile une arborescence source en cache .db."""
    from axiom.compile import compile_universe, CompileError

    try:
        out = compile_universe(args.src_dir, args.output, force=args.force)
    except CompileError as exc:
        print(f"Compilation failed: {exc}", file=sys.stderr)
        return 1
    print(f"Universe compiled: {out}")
    return 0


def add_pack_arguments(parser: argparse.ArgumentParser) -> None:
    """Déclare les arguments de `axiom pack`."""
    parser.add_argument(
        "source",
        help="Universe to pack: source folder (universe.toml) or .db (decompiled on the fly).",
    )
    parser.add_argument("output", help="Path of the .axiom archive to produce.")


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
        print(f"Packaging failed: {exc}", file=sys.stderr)
        return 1
    print(f"Archive created: {out}")
    return 0


def add_import_arguments(parser: argparse.ArgumentParser) -> None:
    """Déclare les arguments de `axiom import`."""
    parser.add_argument("axiom_file", help="The .axiom archive to import (v1 or v2).")
    parser.add_argument(
        "dest_root",
        nargs="?",
        help="Destination root folder (default: ~/AxiomAI/universes).",
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
        print(f"Import failed: {exc}", file=sys.stderr)
        return 1
    print(f"Universe imported: {out}")
    return 0


def add_dev_arguments(parser: argparse.ArgumentParser) -> None:
    """Déclare les arguments de `axiom dev`."""
    parser.add_argument("src_dir", help="Universe source folder to watch.")
    parser.add_argument(
        "--db",
        metavar="DB",
        help="Path of the target .db (default: <src_dir>/.axiom-cache/universe.db).",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        metavar="S",
        help="Polling interval in seconds (default: 1.0).",
    )


def run_dev(args: argparse.Namespace) -> int:
    """Mode dev : watch + recompile in-place de la définition (hot reload)."""
    from pathlib import Path

    from axiom.dev import watch_universe

    if not (Path(args.src_dir) / "universe.toml").exists():
        print(
            f"Invalid source tree (no universe.toml): {args.src_dir}",
            file=sys.stderr,
        )
        return 1

    # flush=True : les événements doivent apparaître immédiatement, même si
    # stdout est redirigé (sinon ils restent dans le buffer process).
    print(f"Dev mode — watching {args.src_dir} (Ctrl-C to stop)", flush=True)
    try:
        watch_universe(
            args.src_dir,
            args.db,
            interval=args.interval,
            on_event=lambda msg: print(msg, flush=True),
        )
    except KeyboardInterrupt:
        print("\nDev mode stopped.")
    return 0


def add_decompile_arguments(parser: argparse.ArgumentParser) -> None:
    """Déclare les arguments de `axiom decompile`."""
    parser.add_argument("db_path", help="Path of the universe .db to decompile.")
    parser.add_argument("output_dir", help="Destination folder for the text source tree.")


def run_decompile(args: argparse.Namespace) -> int:
    """Décompile un .db en arborescence source texte."""
    from axiom.decompile import decompile_universe, DecompileError

    try:
        out = decompile_universe(args.db_path, args.output_dir)
    except DecompileError as exc:
        print(f"Decompilation failed: {exc}", file=sys.stderr)
        return 1
    print(f"Universe decompiled: {out}")
    return 0
