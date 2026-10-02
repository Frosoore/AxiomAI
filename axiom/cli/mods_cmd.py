"""axiom/cli/mods_cmd.py

CLI subcommands for mod packaging and management.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import zipfile

from axiom.kernel.manifest import ManifestError, ModManifest, parse_manifest_file
from axiom.logger import logger


def pack_mod(
    mod_dir: Path | str,
    output_path: Path | str | None = None,
) -> Path:
    """Compile a mod directory into a .axmod (ZIP) archive.

    Validates mod.toml using parse_manifest_file before packing.
    If output_path is not specified, defaults to dist/mods/{id}-{version}.axmod.
    """
    src_dir = Path(mod_dir).resolve()
    if not src_dir.is_dir():
        raise FileNotFoundError(f"Mod directory does not exist: {src_dir}")

    manifest_file = src_dir / "mod.toml"
    if not manifest_file.is_file():
        raise FileNotFoundError(f"Missing mod.toml in {src_dir}")

    manifest = parse_manifest_file(manifest_file)

    if output_path is None:
        dist_dir = Path.cwd() / "dist" / "mods"
        dist_dir.mkdir(parents=True, exist_ok=True)
        dest = dist_dir / f"{manifest.id}-{manifest.version}.axmod"
    else:
        dest = Path(output_path)
        if dest.is_dir() or (not dest.suffix and not dest.exists()):
            dest.mkdir(parents=True, exist_ok=True)
            dest = dest / f"{manifest.id}-{manifest.version}.axmod"
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)

    excluded_names = {"__pycache__", ".pytest_cache", ".git", ".DS_Store"}

    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(src_dir.rglob("*")):
            if not file.is_file():
                continue
            if any(part in excluded_names for part in file.parts):
                continue
            arcname = file.relative_to(src_dir).as_posix()
            zf.write(file, arcname=arcname)

    logger.info("Packed mod '%s' (v%s) into %s", manifest.id, manifest.version, dest)
    return dest


def discover_installed_mods(extra_dirs: list[Path] | None = None) -> list[tuple[ModManifest, Path]]:
    """Installed mods (.axmod archives or unpacked dirs) from the official mods folder and the
    user mods folder — absolute paths, independent of the current directory, `dist/` excluded."""
    from axiom.kernel.loader import discover_mods
    return discover_mods(extra_dirs)


def add_mod_arguments(parser: argparse.ArgumentParser) -> None:
    """Configure subparser for `axiom mod ...` or `axiom mods ...`."""
    sub = parser.add_subparsers(dest="mod_action", required=True)

    # list
    list_p = sub.add_parser("list", help="List installed mods, status, and API compatibility.")
    list_p.set_defaults(func=run_mod_list)

    # enable
    enable_p = sub.add_parser("enable", help="Enable a mod in configuration.")
    enable_p.add_argument("mod_id", help="ID of the mod to enable (e.g. 'core.stat_dynamics').")
    enable_p.set_defaults(func=run_mod_enable)

    # disable
    disable_p = sub.add_parser("disable", help="Disable a mod in configuration.")
    disable_p.add_argument("mod_id", help="ID of the mod to disable.")
    disable_p.set_defaults(func=run_mod_disable)

    # patches (D13)
    patches_p = sub.add_parser("patches", help="List active Python function patches (and declared ones).")
    patches_p.add_argument(
        "--load",
        action="store_true",
        default=False,
        help="Load the modpack in this process first, to list the patches really installed.",
    )
    patches_p.set_defaults(func=run_mods_patches)

    # conflicts (§8, D13)
    conflicts_p = sub.add_parser("conflicts", help="Show mod conflicts and exclusive slot winners.")
    conflicts_p.set_defaults(func=run_mods_conflicts)

    # order (§8)
    order_p = sub.add_parser("order", help="Show or set the user load order of mods.")
    order_p.add_argument(
        "mod_ids",
        nargs="*",
        help="New preferred order (highest priority first). Without ids, print the effective order.",
    )
    order_p.set_defaults(func=run_mods_order)

    # validate
    validate_p = sub.add_parser("validate", help="Statically validate a mod directory or .axmod archive.")
    validate_p.add_argument("mod_path", help="Path to mod directory or .axmod archive.")
    validate_p.set_defaults(func=run_mod_validate)

    # pack
    pack_p = sub.add_parser("pack", help="Pack a mod directory into a .axmod archive.")
    pack_p.add_argument(
        "mod_dir",
        help="Path to the mod directory containing mod.toml.",
    )
    pack_p.add_argument(
        "-o",
        "--output",
        default=None,
        help="Destination path or directory for the resulting .axmod archive.",
    )
    pack_p.set_defaults(func=run_mod_pack)

    # new (Scaffold)
    new_p = sub.add_parser("new", help="Scaffold a new mod with standard structure and templates.")
    new_p.add_argument("mod_id", help="Namespaced mod identifier (e.g. 'author.my_mod').")
    new_p.add_argument(
        "--type",
        choices=["hook", "slot", "data"],
        default="hook",
        help="Template archetype for the mod (default: 'hook').",
    )
    new_p.add_argument(
        "--dir",
        default=None,
        help="Custom destination directory (default: <user mods folder>/<mod_id>).",
    )
    new_p.add_argument("--author", default="Axiom Community", help="Author metadata.")
    new_p.add_argument("--description", default="", help="Short description.")
    new_p.set_defaults(func=run_mod_new)

    # test (Unified Mod Test Runner)
    test_p = sub.add_parser("test", help="Test and validate a mod or .axmod archive.")
    test_p.add_argument("mod_path", help="Path to mod directory or .axmod archive.")
    test_p.set_defaults(func=run_mod_test)

    # dev (Hot-reload dev watcher)
    dev_p = sub.add_parser("dev", help="Watch mod directory and hot-reload upon file changes.")
    dev_p.add_argument("mod_dir", help="Path to the mod directory containing mod.toml.")
    dev_p.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Polling interval in seconds (default: 1.0).",
    )
    dev_p.set_defaults(func=run_mod_dev)

    # generate (LLM Mod Creator)
    gen_p = sub.add_parser("generate", help="Generate or modify a mod using AI from a natural language prompt.")
    gen_p.add_argument("prompt", help="Natural language description of the desired mod functionality.")
    gen_p.add_argument(
        "--yes",
        "-y",
        action="store_true",
        default=False,
        help="Automatically apply and activate the generated mod without interactive confirmation.",
    )
    gen_p.set_defaults(func=run_mod_generate)

    # search (Store Catalog Query)
    search_p = sub.add_parser("search", help="Search mods in the store repository.")
    search_p.add_argument("query", nargs="?", default="", help="Keyword to search in mod catalogue.")
    search_p.add_argument("--repo", default=None, help="Custom repository index URL or path.")
    search_p.set_defaults(func=run_mods_search)

    # install (Store Package Installer)
    install_p = sub.add_parser("install", help="Install and verify a mod package from the store.")
    install_p.add_argument("mod_id", help="ID of the mod to install (e.g. 'axiom.world').")
    install_p.add_argument("--version", default=None, help="Specific version to install.")
    install_p.add_argument("--dest", default=None, help="Destination folder (default: the user mods folder).")
    install_p.add_argument("--repo", default=None, help="Custom repository index URL or path.")
    install_p.set_defaults(func=run_mods_install)

    # update (Store Mod Updater)
    update_p = sub.add_parser("update", help="Check for mod updates in the store.")
    update_p.add_argument("mod_id", nargs="?", default=None, help="Specific mod to update (checks all if omitted).")
    update_p.add_argument("--repo", default=None, help="Custom repository index URL or path.")
    update_p.set_defaults(func=run_mods_update)




def run_mods_patches(args: argparse.Namespace) -> int:
    """Handler for `axiom mods patches` command (Rule D13).

    Lists only patches really installed in this process (never an inactive one). In a
    fresh CLI process no mod is loaded: `--load` loads the modpack first; otherwise the
    patches declared in the manifests are shown in a separate, explicitly labelled list.
    """
    from axiom.kernel.patcher import get_active_patches

    if getattr(args, "load", False):
        from axiom.kernel.loader import get_kernel_registry
        get_kernel_registry()

    active_records = get_active_patches()
    if active_records:
        print(f"{'Target Function':<35} {'Type':<10} {'Mod ID':<20} {'Priority'}")
        print("-" * 75)
        for r in sorted(active_records, key=lambda x: (x.target_name, x.priority)):
            print(f"{r.target_name:<35} {r.patch_type.value:<10} {r.mod_id:<20} {r.priority}")
        return 0

    declared: list[tuple[str, str]] = []
    for manifest, _ in discover_installed_mods():
        for patch_target in manifest.contributes.patches:
            declared.append((patch_target, manifest.id))

    print("No active function patch in this process.")
    if declared:
        print("\nDeclared in manifests (NOT active here; run with --load to load the modpack):")
        for target, mod_id in declared:
            print(f"  {target:<35} {mod_id}")
    return 0


def run_mods_conflicts(args: argparse.Namespace) -> int:
    """Handler for `axiom mods conflicts` (§8, D13): declared conflicts, cycles and
    exclusive slots claimed by several mods (first in mod order wins)."""
    from axiom.config import load_config
    from axiom.kernel.loader import get_load_state, plan_modpack

    plan = plan_modpack(discover_installed_mods(), load_config())
    report = plan.report
    found = False
    for loser, winner, explanation in report.conflicts:
        found = True
        print(f"CONFLICT  {explanation}: '{winner}' wins, '{loser}' is not loaded.")
    for cycle in report.cycles:
        found = True
        print(f"CYCLE     {' -> '.join(cycle)}: these mods are not loaded.")
    exclusive = dict(plan.exclusive_conflicts)
    state = get_load_state()
    if state is not None:
        exclusive.update(state.registry.get_slot_conflicts())
    for slot, mods in sorted(exclusive.items()):
        found = True
        others = ", ".join(mods[1:])
        print(f"EXCLUSIVE '{slot}': {', '.join(mods)} provide it; '{mods[0]}' wins (ignored: {others}).")
    if not found:
        print("No conflict between the enabled mods.")
    return 0


def run_mods_order(args: argparse.Namespace) -> int:
    """Handler for `axiom mods order [ids...]` (§8)."""
    from axiom.config import load_config, save_config
    from axiom.kernel.loader import get_user_mod_order, plan_modpack, set_user_mod_order

    cfg = load_config()
    if args.mod_ids:
        set_user_mod_order(cfg, [m.strip() for m in args.mod_ids if m.strip()])
        save_config(cfg)
        print("Mod order saved.")
    plan = plan_modpack(discover_installed_mods(), cfg)
    print(f"User order: {', '.join(get_user_mod_order(cfg)) or '(none: alphabetical under constraints)'}")
    print("Effective load order (dependencies and before/after constraints applied):")
    for i, mod_id in enumerate(plan.load_order, 1):
        print(f"  {i:>2}. {mod_id}")
    return 0


def run_mod_validate(args: argparse.Namespace) -> int:
    """Handler for `axiom mod validate <path>` command."""
    from axiom.kernel.manifest import load_manifest, ManifestError
    from axiom.kernel.patcher import resolve_target

    target_path = Path(args.mod_path).resolve()
    if not target_path.exists():
        print(f"Error: Path does not exist: {target_path}", file=sys.stderr)
        return 1

    try:
        manifest = load_manifest(target_path)
    except ManifestError as err:
        print(f"Manifest validation failed for {target_path}: {err}", file=sys.stderr)
        return 1
    except Exception as err:
        print(f"Unexpected error loading manifest: {err}", file=sys.stderr)
        return 1

    errors: list[str] = []

    # Verify that all declared patch targets can actually be resolved
    for patch_target in manifest.contributes.patches:
        try:
            resolve_target(patch_target)
        except Exception as err:
            errors.append(f"Declared patch target '{patch_target}' cannot be resolved: {err}")

    if errors:
        print(f"Validation FAILED for mod '{manifest.id}' (v{manifest.version}):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(f"Mod '{manifest.id}' (v{manifest.version}) is valid. {len(manifest.contributes.patches)} patch target(s) verified.")
    return 0


def run_mod_list(args: argparse.Namespace) -> int:
    """Handler for `axiom mods list` command.

    Shows the real status of each mod (B5): the plan computed from the manifests
    (user choice, safe mode, Python packages, API, dependencies with cascade, conflicts,
    cycles) merged with what happened in this process if mods were loaded (init errors,
    runtime faults).
    """
    from axiom.config import load_config
    from axiom.kernel.api import KERNEL_API
    from axiom.kernel.loader import get_load_state, get_mod_search_dirs, plan_modpack

    cfg = load_config()
    mods = discover_installed_mods()

    if not mods:
        dirs = ", ".join(str(d) for d in get_mod_search_dirs())
        print(f"No mods found in the mod folders ({dirs}).")
        return 0

    plan = plan_modpack(mods, cfg)
    statuses = dict(plan.statuses)
    state = get_load_state()
    if state is not None:
        statuses.update({k: v for k, v in state.statuses.items() if k in statuses})

    print(f"{'MOD ID':<28} {'VERSION':<10} {'STATUS':<12} {'ORDER':<6} {'API':<8} {'NAME'}")
    print("-" * 90)
    for manifest, _path in mods:
        st = statuses[manifest.id]
        status = "enabled" if st.state in ("enabled", "active") else "disabled"
        order = str(st.order + 1) if st.order is not None and status == "enabled" else "-"
        api_compat = f"v{manifest.axiom_api} (OK)" if manifest.axiom_api == KERNEL_API else f"v{manifest.axiom_api} (!)"
        print(f"{manifest.id:<28} {manifest.version:<10} {status:<12} {order:<6} {api_compat:<8} {manifest.localized_name()}")
        if st.reason and st.state != "enabled":
            print(f"    -> {st.state}: {st.reason}")
    if plan.exclusive_conflicts or plan.report.conflicts or plan.report.cycles:
        print("\nConflicts found: run 'axiom mods conflicts' for details.")
    return 0


def run_mod_enable(args: argparse.Namespace) -> int:
    """Handler for `axiom mods enable <mod_id>` command."""
    from axiom.config import load_config, save_config

    mod_id = args.mod_id.strip()
    cfg = load_config()
    cfg.mod_settings.setdefault(mod_id, {})["enabled"] = True
    save_config(cfg)
    print(f"Mod '{mod_id}' enabled successfully.")
    return 0


def run_mod_disable(args: argparse.Namespace) -> int:
    """Handler for `axiom mods disable <mod_id>` command."""
    from axiom.config import load_config, save_config

    mod_id = args.mod_id.strip()
    cfg = load_config()
    cfg.mod_settings.setdefault(mod_id, {})["enabled"] = False
    save_config(cfg)
    print(f"Mod '{mod_id}' disabled successfully.")
    return 0


def run_mod_pack(args: argparse.Namespace) -> int:
    """Handler for `axiom mod pack` command."""
    try:
        dest = pack_mod(args.mod_dir, args.output)
        print(f"Mod successfully packaged: {dest}")
        return 0
    except (ManifestError, FileNotFoundError) as err:
        print(f"Error packing mod: {err}", file=sys.stderr)
        return 1
    except Exception as err:
        print(f"Unexpected error: {err}", file=sys.stderr)
        return 2


def run_mod_new(args: argparse.Namespace) -> int:
    """Handler for `axiom mod new` command."""
    from axiom.kernel.scaffold import scaffold_mod

    try:
        created_dir = scaffold_mod(
            mod_id=args.mod_id,
            mod_type=args.type,
            target_dir=args.dir,
            author=args.author,
            description=args.description,
        )
        print(f"Successfully scaffolded new '{args.type}' mod '{args.mod_id}' at:")
        print(f"  {created_dir}")
        print("\nNext steps:")
        print(f"  1. Edit {created_dir}/main.py")
        print(f"  2. Run tests: axiom mod test {created_dir}")
        print(f"  3. Enable mod: axiom mod enable {args.mod_id}")
        return 0
    except (ValueError, FileExistsError) as err:
        print(f"Error creating mod: {err}", file=sys.stderr)
        return 1
    except Exception as err:
        print(f"Unexpected error: {err}", file=sys.stderr)
        return 2


def run_mod_test(args: argparse.Namespace) -> int:
    """Handler for `axiom mod test` command."""
    from axiom.kernel.tester import test_mod

    result = test_mod(args.mod_path)
    if result.passed:
        name_str = f"'{result.manifest.id}' (v{result.manifest.version})" if result.manifest else f"'{args.mod_path}'"
        print(f"SUCCESS: Mod {name_str} passed all structural and functional tests.")
        if result.pytest_output:
            print("\nTest suite output:")
            print(result.pytest_output.strip())
        return 0
    else:
        print(f"FAILED: Mod testing failed for '{args.mod_path}':", file=sys.stderr)
        for err in result.errors:
            print(f"  - {err}", file=sys.stderr)
        if result.pytest_output:
            print("\nTest runner output:", file=sys.stderr)
            print(result.pytest_output.strip(), file=sys.stderr)
        return 1


def run_mod_dev(args: argparse.Namespace) -> int:
    """Handler for `axiom mod dev` command."""
    from axiom.kernel.dev import watch_mod

    try:
        watch_mod(args.mod_dir, interval=args.interval)
        return 0
    except KeyboardInterrupt:
        print("\n[ModDev] Stopped watching.")
        return 0
    except Exception as err:
        print(f"[ModDev] Fatal error: {err}", file=sys.stderr)
        return 1


def _print_colored_diff(diff_text: str) -> None:
    """Print diff with ANSI color formatting if terminal supports it."""
    is_tty = sys.stdout.isatty()
    green = "\033[32m" if is_tty else ""
    red = "\033[31m" if is_tty else ""
    cyan = "\033[36m" if is_tty else ""
    bold = "\033[1m" if is_tty else ""
    reset = "\033[0m" if is_tty else ""

    for line in diff_text.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            print(f"{bold}{line}{reset}")
        elif line.startswith("+"):
            print(f"{green}{line}{reset}")
        elif line.startswith("-"):
            print(f"{red}{line}{reset}")
        elif line.startswith("@@"):
            print(f"{cyan}{line}{reset}")
        else:
            print(line)


def run_mod_generate(args: argparse.Namespace) -> int:
    """Handler for `axiom mod generate` command (Rule §12 & D14).

    Nothing generated is executed before the user's confirmation: the diff and a static
    validation are shown first; the mod's tests run only after "yes", before install.
    """
    from axiom.kernel.llm_creator import ModTestsFailedError, apply_generated_mod, generate_mod

    print(f"Generating mod from prompt: \"{args.prompt}\"...")
    try:
        result = generate_mod(args.prompt)
    except Exception as err:
        print(f"Error generating mod: {err}", file=sys.stderr)
        return 1

    print("\n" + "=" * 65)
    print(f"GENERATED MOD: {result.mod_id} (v{result.manifest.version})")
    print(f"Preparation folder: {result.staged_dir}")
    print("=" * 65)

    for rel_path, diff in result.file_diffs.items():
        print(f"\nDiff for {rel_path}:")
        print("-" * 50)
        _print_colored_diff(diff)

    print("\n" + "-" * 65)
    if result.validation_passed:
        print("Static validation (no code executed): PASSED")
    else:
        print("Static validation (no code executed): PROBLEMS FOUND")
        if result.error_report:
            print(result.error_report)
    print("The mod's tests will run only after your confirmation.")

    # User confirmation gate
    if not args.yes:
        try:
            choice = input("\nConfirmer l'installation et l'activation de ce mod ? [y/N]: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            return 1

        if choice not in ("y", "yes", "oui", "o"):
            print(f"\nInstallation annulée. Les fichiers générés sont conservés dans le dossier de préparation :\n  {result.staged_dir}")
            return 0

    try:
        dest_dir, axmod_path = apply_generated_mod(result.staged_dir)
    except ModTestsFailedError as err:
        print(f"\nLes tests du mod ont échoué, rien n'a été installé :\n{err}", file=sys.stderr)
        return 1
    except Exception as err:
        print(f"\nInstallation impossible : {err}", file=sys.stderr)
        return 1
    print(f"\nMod '{result.mod_id}' installé avec succès dans : {dest_dir}")
    if axmod_path:
        print(f"Archive compilée : {axmod_path}")
    print("Mod activé dans la configuration.")
    return 0


def run_mods_search(args: argparse.Namespace) -> int:
    """Handler for `axiom mods search [query]` command."""
    from axiom.kernel.store import StoreError, search_store

    try:
        results = search_store(args.query, repo_url=args.repo)
    except StoreError as err:
        print(f"Error querying store: {err}", file=sys.stderr)
        return 1

    if not results:
        print(f"No mods found matching '{args.query}'.")
        return 0

    print(f"{'MOD ID':<25} {'VERSION':<10} {'NAME':<28} {'AUTHOR'}")
    print("-" * 80)
    for entry in results:
        print(f"{entry.id:<25} {entry.version:<10} {entry.name:<28} {entry.author or 'Community'}")
    return 0


def run_mods_install(args: argparse.Namespace) -> int:
    """Handler for `axiom mods install <mod_id>` command."""
    from axiom.kernel.store import ModIntegrityError, StoreError, install_mod_from_store

    print(f"Resolving mod '{args.mod_id}' from store...")
    try:
        installed_path = install_mod_from_store(
            mod_id=args.mod_id,
            version=args.version,
            dest_dir=args.dest,
            repo_url=args.repo,
            enable=True,
        )
        print(f"SUCCESS: Mod '{args.mod_id}' verified and installed to:")
        print(f"  {installed_path}")
        print("Mod enabled in settings.json.")
        return 0
    except ModIntegrityError as err:
        print(f"SECURITY ALERT: Cryptographic verification failed:\n{err}", file=sys.stderr)
        return 1
    except StoreError as err:
        print(f"Store installation error: {err}", file=sys.stderr)
        return 1
    except Exception as err:
        print(f"Unexpected error installing mod: {err}", file=sys.stderr)
        return 2


def run_mods_update(args: argparse.Namespace) -> int:
    """Handler for `axiom mods update [<mod_id>]` command."""
    from axiom.kernel.store import StoreError, fetch_store_index, install_mod_from_store

    try:
        remote_entries = fetch_store_index(repo_url=args.repo, refresh=True)
    except StoreError as err:
        print(f"Error fetching store index: {err}", file=sys.stderr)
        return 1

    store_map = {e.id: e for e in remote_entries}
    installed = discover_installed_mods()

    mods_to_check = installed
    if args.mod_id:
        mods_to_check = [item for item in installed if item[0].id == args.mod_id]
        if not mods_to_check:
            print(f"Mod '{args.mod_id}' is not installed locally.")
            return 1

    updates_found = 0
    for manifest, _ in mods_to_check:
        if manifest.id not in store_map:
            continue
        remote = store_map[manifest.id]
        is_newer = False
        try:
            from packaging.version import Version
            is_newer = Version(remote.version) > Version(manifest.version)
        except Exception:
            is_newer = remote.version != manifest.version

        if is_newer:
            updates_found += 1
            print(f"Update available for '{manifest.id}': v{manifest.version} -> v{remote.version}")
            try:
                install_mod_from_store(manifest.id, version=remote.version, repo_url=args.repo, enable=True)
                print(f"  -> Upgraded '{manifest.id}' to v{remote.version}")
            except Exception as exc:
                print(f"  -> Failed to upgrade '{manifest.id}': {exc}", file=sys.stderr)

    if updates_found == 0:
        print("All inspected mods are up to date.")
    return 0


