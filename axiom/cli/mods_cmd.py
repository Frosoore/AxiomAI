"""axiom/cli/mods_cmd.py

CLI subcommands for mod packaging and management.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import zipfile

from axiom.kernel.manifest import ManifestError, parse_manifest_file
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
        dist_dir = Path("dist/mods")
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
    """Scan standard locations for installed mods (.axmod archives or unpacked dirs)."""
    search_dirs: list[Path] = [Path("mods"), Path("dist/mods")]
    if extra_dirs:
        search_dirs.extend(extra_dirs)

    found: dict[str, tuple[ModManifest, Path]] = {}

    for base_dir in search_dirs:
        if not base_dir.is_dir():
            continue

        # 1. Unpacked directories
        for sub_dir in sorted(base_dir.iterdir()):
            if sub_dir.is_dir() and (sub_dir / "mod.toml").is_file():
                try:
                    manifest = parse_manifest_file(sub_dir / "mod.toml")
                    found[manifest.id] = (manifest, sub_dir)
                except Exception as err:
                    logger.debug("Failed to parse manifest in %s: %s", sub_dir, err)

        # 2. .axmod archives
        for archive_file in sorted(base_dir.glob("*.axmod")):
            try:
                from axiom.kernel.manifest import load_manifest_from_archive
                manifest = load_manifest_from_archive(archive_file)
                if manifest.id not in found:
                    found[manifest.id] = (manifest, archive_file)
            except Exception as err:
                logger.debug("Failed to read archive %s: %s", archive_file, err)

    return sorted(found.values(), key=lambda t: t[0].id)


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
    patches_p = sub.add_parser("patches", help="List active or declared Python function patches.")
    patches_p.set_defaults(func=run_mods_patches)

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
        help="Custom destination directory (default: mods/<mod_id>).",
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
    install_p.add_argument("--dest", default="mods", help="Destination folder (default: mods).")
    install_p.add_argument("--repo", default=None, help="Custom repository index URL or path.")
    install_p.set_defaults(func=run_mods_install)

    # update (Store Mod Updater)
    update_p = sub.add_parser("update", help="Check for mod updates in the store.")
    update_p.add_argument("mod_id", nargs="?", default=None, help="Specific mod to update (checks all if omitted).")
    update_p.add_argument("--repo", default=None, help="Custom repository index URL or path.")
    update_p.set_defaults(func=run_mods_update)




def run_mods_patches(args: argparse.Namespace) -> int:
    """Handler for `axiom mods patches` command (Rule D13)."""
    from axiom.kernel.patcher import get_active_patches

    active_records = get_active_patches()

    # Also inspect installed mods for declared patches
    declared: list[tuple[str, str, str, int]] = []
    if not active_records:
        installed = discover_installed_mods()
        for manifest, _ in installed:
            for patch_target in manifest.contributes.patches:
                declared.append((patch_target, "declared", manifest.id, 100))

    if not active_records and not declared:
        print("No active or declared function patches.")
        return 0

    print(f"{'Target Function':<35} {'Type':<10} {'Mod ID':<20} {'Priority'}")
    print("-" * 75)

    if active_records:
        for r in sorted(active_records, key=lambda x: (x.target_name, x.priority)):
            print(f"{r.target_name:<35} {r.patch_type.value:<10} {r.mod_id:<20} {r.priority}")
    else:
        for target, ptype, mod_id, priority in declared:
            print(f"{target:<35} {ptype:<10} {mod_id:<20} {priority}")

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
    """Handler for `axiom mods list` command."""
    from axiom.config import load_config
    from axiom.kernel.loader import is_mod_enabled

    cfg = load_config()
    mods = discover_installed_mods()

    if not mods:
        print("No mods found in standard directories (mods/, dist/mods/).")
        return 0

    print(f"{'MOD ID':<28} {'VERSION':<10} {'STATUS':<10} {'API':<8} {'NAME'}")
    print("-" * 75)
    for manifest, _path in mods:
        enabled = is_mod_enabled(manifest.id, cfg)
        status = "enabled" if enabled else "disabled"
        api_compat = "v1 (OK)" if manifest.axiom_api == 1 else f"v{manifest.axiom_api} (!)"
        print(f"{manifest.id:<28} {manifest.version:<10} {status:<10} {api_compat:<8} {manifest.name}")
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
    """Handler for `axiom mod generate` command (Rule §12 & D14)."""
    from axiom.kernel.llm_creator import apply_generated_mod, generate_mod

    print(f"Generating mod from prompt: \"{args.prompt}\"...")
    try:
        result = generate_mod(args.prompt)
    except Exception as err:
        print(f"Error generating mod: {err}", file=sys.stderr)
        return 1

    print("\n" + "=" * 65)
    print(f"GENERATED MOD: {result.mod_id} (v{result.manifest.version})")
    print(f"Staged at: {result.staged_dir}")
    print("=" * 65)

    for rel_path, diff in result.file_diffs.items():
        print(f"\nDiff for {rel_path}:")
        print("-" * 50)
        _print_colored_diff(diff)

    print("\n" + "-" * 65)
    if result.tests_passed:
        print("Sandbox Tests & Validation: PASSED")
    else:
        print("Sandbox Tests & Validation: WARNINGS/FAILURES ENCOUNTERED")
        if result.error_report:
            print(result.error_report)

    # User confirmation gate
    if not args.yes:
        try:
            choice = input("\nConfirmer l'installation et l'activation de ce mod ? [y/N]: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            return 1

        if choice not in ("y", "yes", "oui", "o"):
            print(f"\nInstallation annulée. Les fichiers générés sont conservés dans :\n  {result.staged_dir}")
            return 0

    dest_dir, axmod_path = apply_generated_mod(result.staged_dir)
    print(f"\nMod '{result.mod_id}' installé avec succès dans : {dest_dir}")
    if axmod_path:
        print(f"Archive compilée : {axmod_path}")
    print(f"Mod activé dans la configuration.")
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


