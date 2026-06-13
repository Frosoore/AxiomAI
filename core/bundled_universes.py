"""
core/bundled_universes.py

First-launch installation of the bundled default universe(s) — TICKET-062.

The repo ships ready-to-play universes as Universe-as-Code sources under
`universes/<name>/` (today: Myria). On startup, each one is copied into the
Hub library (`~/AxiomAI/universes/<name>/`), where the normal discovery
(axiom.library.discover_universes) compiles it on demand.

Each bundle is offered ONCE ever, tracked in a marker file: a user who
deletes the universe from their library must not get it back on every
launch. An existing folder with the same name is never overwritten.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from axiom.compile import CACHE_DIRNAME
from axiom.logger import logger
from axiom.paths import CONFIG_DIR, UNIVERSES_DIR

# Repo root /universes — the app runs from the repo (run.sh / run.bat).
BUNDLED_ROOT: Path = Path(__file__).resolve().parent.parent / "universes"
_MARKER_FILE: Path = CONFIG_DIR / "installed_bundles.txt"
_SOURCE_MARKER = "universe.toml"

# The compile cache is rebuilt by discovery on the user's machine; .git would
# be the repo's own metadata.
_EXCLUDED_TOP_LEVEL = (CACHE_DIRNAME, ".git")


def install_bundled_universes(
    bundle_root: str | Path = BUNDLED_ROOT,
    library_dir: str | Path = UNIVERSES_DIR,
    marker_file: str | Path = _MARKER_FILE,
) -> list[str]:
    """Copy each bundled universe into the library, once ever per bundle.

    Never raises: a problem with the bundled content must not prevent the
    app from starting (warning logged instead).

    Returns:
        The names of the universes actually installed by this call.
    """
    bundle_root = Path(bundle_root)
    library_dir = Path(library_dir)
    marker_file = Path(marker_file)
    installed: list[str] = []

    try:
        if not bundle_root.is_dir():
            return installed

        offered: set[str] = set()
        if marker_file.is_file():
            offered = {
                line.strip()
                for line in marker_file.read_text(encoding="utf-8").splitlines()
                if line.strip()
            }

        for src in sorted(p for p in bundle_root.iterdir() if p.is_dir()):
            if not (src / _SOURCE_MARKER).is_file() or src.name in offered:
                continue
            dest = library_dir / src.name
            if dest.exists():
                logger.info(
                    "Bundled universe '%s' not installed: '%s' already exists.",
                    src.name, dest,
                )
            else:
                shutil.copytree(
                    src, dest, ignore=shutil.ignore_patterns(*_EXCLUDED_TOP_LEVEL)
                )
                installed.append(src.name)
                logger.info("Bundled universe '%s' installed in the library.", src.name)
            # Existing or just installed: either way, never offer it again.
            offered.add(src.name)

        marker_file.parent.mkdir(parents=True, exist_ok=True)
        marker_file.write_text(
            "\n".join(sorted(offered)) + "\n" if offered else "",
            encoding="utf-8",
        )
    except Exception as exc:  # noqa: BLE001 — le démarrage ne doit jamais en mourir
        logger.warning("Bundled universe installation failed: %s", exc)

    return installed
