#!/usr/bin/env python3
"""build_site.py — regenerate the data-driven parts of the Axiom AI landing site.

Single source of truth for the public site's *content*:

    landing/content/roadmap.toml   -> the Dev page roadmap (next / far / done)
    landing/content/updates.toml   -> the Dev page changelog (dropdown by month)

This script fills the marked regions of the hand-written HTML in place, so the
pages keep their crafted layout/CSS and only the data swaps. It is **idempotent**
(safe to run repeatedly) and **dependency-free** (stdlib only: ``tomllib`` ships
with Python 3.11+). The GitHub Pages workflow runs it before publishing, so the
deployed site is always in sync with the TOML; you can also run it locally to
preview:

    python landing/build_site.py            # regenerate dev-updates.html + index.html
    python landing/build_site.py --check     # fail if regeneration would change a file (CI guard)
    python landing/build_site.py --draft-update [SINCE]
                                             # print a TOML [[update]] block drafted
                                             # from recent feat:/fix: git commits

Markers in the HTML look like ``<!-- BUILD:name -->`` … ``<!-- /BUILD:name -->``
(or ``// BUILD:name`` … ``// /BUILD:name`` inside <script>). Everything between a
pair is replaced; the markers themselves stay.
"""

from __future__ import annotations

import html
import json
import re
import subprocess
import sys
import tomllib
from datetime import date
from pathlib import Path

LANDING = Path(__file__).resolve().parent
REPO = LANDING.parent
CONTENT = LANDING / "content"


# --------------------------------------------------------------------------- IO
def _load_toml(name: str) -> dict:
    with open(CONTENT / name, "rb") as f:
        return tomllib.load(f)


def _read_version() -> str:
    """Engine version from axiom/__init__.py (no import, no network)."""
    init = (REPO / "axiom" / "__init__.py").read_text(encoding="utf-8")
    m = re.search(r'__version__\s*=\s*"([^"]+)"', init)
    return m.group(1) if m else "?"


def _git_last_updated() -> str:
    """`YYYY-MM-DD (shortsha)` of the last commit, or today's date if git is absent."""
    try:
        out = subprocess.check_output(
            ["git", "-C", str(REPO), "log", "-1", "--date=short", "--format=%cd (%h)"],
            stderr=subprocess.DEVNULL, text=True,
        ).strip()
        return out or date.today().isoformat()
    except Exception:
        return date.today().isoformat()


# ----------------------------------------------------------------- marker swap
def _replace_region(text: str, name: str, inner: str, *, comment: str = "html") -> str:
    """Replace the body between BUILD:name markers. Raises if the pair is missing."""
    if comment == "js":
        open_m, close_m = rf"// BUILD:{name}", rf"// /BUILD:{name}"
    else:
        open_m, close_m = rf"<!-- BUILD:{name} -->", rf"<!-- /BUILD:{name} -->"
    pattern = re.compile(
        re.escape(open_m) + r".*?" + re.escape(close_m), re.DOTALL
    )
    if not pattern.search(text):
        raise SystemExit(f"ERROR: marker BUILD:{name} not found (expected {open_m} … {close_m})")
    return pattern.sub(f"{open_m}\n{inner}\n        {close_m}", text)


# ------------------------------------------------------------------- rendering
_COLS = [
    ("next", "Next up", "What we're actively working toward.", "▸"),
    ("far", "Far away", "Bigger bets, further out.", "◇"),
    ("done", "Recently done", "Shipped — was on the roadmap, now live.", "✓"),
]


def _render_roadmap(roadmap: dict) -> str:
    items = roadmap.get("item", [])
    by_status: dict[str, list[dict]] = {"next": [], "far": [], "done": []}
    for it in items:
        by_status.get(it.get("status", "next"), by_status["next"]).append(it)

    cols = []
    for status, heading, sub, marker in _COLS:
        lis = []
        for it in by_status[status]:
            title = it.get("title", "")  # trusted inline HTML (authored in TOML)
            desc = it.get("desc", "")
            date_s = it.get("date")
            date_html = (
                f' <span class="rl-date">({html.escape(date_s)})</span>' if date_s else ""
            )
            lis.append(
                '          <li><span class="marker">' + marker + "</span>"
                f'<div><span class="rl-title">{title}</span>'
                f'<span class="rl-desc">{desc}{date_html}</span></div></li>'
            )
        body = "\n".join(lis) if lis else '          <li class="rl-empty"><div><span class="rl-desc">Nothing here yet.</span></div></li>'
        cols.append(
            f'      <div class="road-col {status}">\n'
            f"        <h3>{heading}</h3>\n"
            f'        <p class="sub">{sub}</p>\n'
            f'        <ul class="road-list">\n{body}\n        </ul>\n'
            f"      </div>"
        )
    return '    <div class="road-tiers reveal">\n' + "\n".join(cols) + "\n    </div>"


def _render_updates_data(updates: dict) -> str:
    """JSON island consumed by the existing dropdown renderer in dev-updates.html."""
    out = []
    for u in updates.get("update", []):
        out.append({
            "id": u.get("id", ""),
            "label": u.get("label", ""),
            "summary": u.get("summary", ""),
            "sections": [
                {"title": s.get("title", ""), "kind": s.get("kind", ""),
                 "items": list(s.get("items", []))}
                for s in u.get("section", [])
            ],
        })
    return "            const DEV_UPDATES = " + json.dumps(out, indent=12, ensure_ascii=False) + ";"


def _render_meta(version: str, updated: str) -> str:
    return (
        f'                <span class="du-stat">Engine <b>v{html.escape(version)}</b></span>\n'
        f'                <span class="du-stat">Last updated <b>{html.escape(updated)}</b></span>'
    )


def _render_roadmap_teaser(roadmap: dict, limit: int = 4) -> str:
    """A short Next-up preview for the home page, linking to the full Dev page."""
    nexts = [it for it in roadmap.get("item", []) if it.get("status") == "next"][:limit]
    lis = "\n".join(
        '        <li><span class="marker">▸</span>'
        f'<div><span class="rl-title">{it.get("title","")}</span></div></li>'
        for it in nexts
    )
    return (
        '      <ul class="road-list road-teaser">\n' + lis + "\n      </ul>\n"
        '      <a class="btn btn-primary" href="dev-updates.html">'
        "See the full roadmap &amp; dev updates →</a>"
    )


# ----------------------------------------------------------------- draft helper
def _draft_update(since: str | None) -> str:
    """Print a TOML [[update]] block drafted from recent feat:/fix: commits.

    ``since`` is an optional git ref/tag/date (e.g. a previous release tag); when
    omitted the last 30 commits are scanned.
    """
    cmd = ["git", "-C", str(REPO), "log", "--format=%s"]
    cmd += [f"{since}..HEAD"] if since else ["--max-count", "30"]
    try:
        log = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True).splitlines()
    except Exception as e:
        return f"# git log unavailable: {e}"
    added, fixed = [], []
    for line in log:
        low = line.lower()
        if low.startswith(("feat:", "feat(")):
            added.append(line.split(":", 1)[-1].strip())
        elif low.startswith(("fix:", "fix(")):
            fixed.append(line.split(":", 1)[-1].strip())

    def block(items):
        return "\n".join(f'    "{i.replace(chr(34), chr(39))}",' for i in items) or "    # (none)"

    ym = date.today().strftime("%Y-%m")
    label = date.today().strftime("%B %Y")
    return (
        f'[[update]]\nid = "{ym}"\nlabel = "{label}"\n'
        'summary = "TODO: one or two sentences on the overall direction."\n\n'
        f'[[update.section]]\ntitle = "Added"\nkind = "added"\nitems = [\n{block(added)}\n]\n\n'
        f'[[update.section]]\ntitle = "Fixed"\nkind = "fixed"\nitems = [\n{block(fixed)}\n]\n'
    )


# -------------------------------------------------------------------------- main
def build(check: bool = False) -> int:
    roadmap = _load_toml("roadmap.toml")
    updates = _load_toml("updates.toml")
    version = _read_version()
    updated = _git_last_updated()

    targets = {
        LANDING / "dev-updates.html": [
            ("roadmap", _render_roadmap(roadmap), "html"),
            ("updates-data", _render_updates_data(updates), "js"),
            ("meta", _render_meta(version, updated), "html"),
        ],
        LANDING / "index.html": [
            ("roadmap-teaser", _render_roadmap_teaser(roadmap), "html"),
        ],
    }

    changed = []
    for path, regions in targets.items():
        original = path.read_text(encoding="utf-8")
        text = original
        for name, inner, comment in regions:
            text = _replace_region(text, name, inner, comment=comment)
        if text != original:
            changed.append(path.name)
            if not check:
                path.write_text(text, encoding="utf-8")

    if check:
        if changed:
            print("Out of date (run python landing/build_site.py): " + ", ".join(changed))
            return 1
        print("Site content up to date.")
        return 0
    print(f"Generated from TOML (v{version}, {updated}). "
          + ("Updated: " + ", ".join(changed) if changed else "No changes."))
    return 0


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--draft-update":
        print(_draft_update(argv[1] if len(argv) > 1 else None))
        return 0
    return build(check="--check" in argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
