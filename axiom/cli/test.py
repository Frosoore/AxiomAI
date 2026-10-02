"""axiom.cli.test — CLI utility draft for integration tests and state canonicalization."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from axiom.testing.golden_harness import SessionStateCanonicalizer


def add_test_arguments(parser: argparse.ArgumentParser) -> None:
    """Register CLI arguments for the test command."""
    parser.add_argument(
        "db_path",
        nargs="?",
        default=None,
        help="Path to a universe or save database (.db / .axiom).",
    )
    parser.add_argument(
        "--save-id",
        dest="save_id",
        default=None,
        help="Save ID to inspect or canonicalize.",
    )
    parser.add_argument(
        "--turn",
        type=int,
        default=None,
        help="Specific turn ID to canonicalize up to.",
    )
    parser.add_argument(
        "--canonicalize",
        action="store_true",
        default=False,
        help="Print the canonical state JSON for the specified save.",
    )
    parser.add_argument(
        "--golden",
        action="store_true",
        default=False,
        help="Run the golden step integration test suite via pytest.",
    )


def run_test(args: argparse.Namespace) -> int:
    """Execute test subcommand."""
    if args.golden:
        import subprocess
        project_root = Path(__file__).resolve().parent.parent.parent
        golden = project_root / "tests" / "test_golden_step.py"
        if not golden.is_file():
            print(f"Error: golden step suite not found ({golden}); it ships with the source tree only.", file=sys.stderr)
            return 1
        cmd = [sys.executable, "-m", "pytest", str(golden), "-v"]
        result = subprocess.run(cmd, cwd=str(project_root))
        return result.returncode

    if args.canonicalize:
        if not args.db_path or not args.save_id:
            print("Error: --canonicalize requires db_path and --save-id", file=sys.stderr)
            return 1
        canonical = SessionStateCanonicalizer.canonicalize(
            args.db_path,
            args.save_id,
            at_turn=args.turn,
        )
        print(SessionStateCanonicalizer.to_json(canonical))
        return 0

    print("Use --golden to run integration tests or --canonicalize to view canonical state.")
    return 0
