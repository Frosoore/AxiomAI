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
from datetime import date, datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape as _xml_escape

LANDING = Path(__file__).resolve().parent
REPO = LANDING.parent
CONTENT = LANDING / "content"
BLOG_SRC = CONTENT / "blog"
BLOG_OUT = LANDING / "blog"
# Public base URL (GitHub Pages). Used for absolute links in the RSS feed.
SITE_BASE = "https://frosoore.github.io/AxiomAI"


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
    # No `reveal` class here: the Dev page has no scroll-reveal observer (unlike
    # index.html), so a revealed element would stay invisible. Keep it always shown.
    return '    <div class="road-tiers">\n' + "\n".join(cols) + "\n    </div>"


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


# ------------------------------------------------------------------------ blog
def _md_renderer():
    """markdown-it renderer (ships transitively with myst-parser, used by docs)."""
    try:
        from markdown_it import MarkdownIt
    except ImportError as e:  # pragma: no cover
        raise SystemExit(
            "ERROR: markdown-it-py is required to build the blog "
            "(pip install markdown-it-py). It normally comes with myst-parser."
        ) from e
    return MarkdownIt("commonmark", {"typographer": False}).enable(["table", "strikethrough"])


def _fmt_date(iso: str) -> str:
    """'2026-06-20' -> 'June 20, 2026' (no leading zero on the day)."""
    try:
        d = datetime.strptime(iso, "%Y-%m-%d")
        return f"{d.strftime('%B')} {d.day}, {d.year}"
    except ValueError:
        return iso


def _load_posts() -> list[dict]:
    """Parse landing/content/blog/*.md (TOML front matter + Markdown body).

    Front matter is delimited by ``+++`` lines. Posts are returned newest first.
    """
    posts: list[dict] = []
    if not BLOG_SRC.is_dir():
        return posts
    for path in BLOG_SRC.glob("*.md"):
        raw = path.read_text(encoding="utf-8").lstrip()
        if raw.startswith("+++"):
            _, fm, body = raw.split("+++", 2)
            meta = tomllib.loads(fm)
        else:
            meta, body = {}, raw
        meta.setdefault("slug", path.stem)
        meta.setdefault("title", path.stem)
        meta.setdefault("date", "")
        meta.setdefault("author", "")
        meta["summary"] = list(meta.get("summary", []))
        meta["body"] = body.strip()
        posts.append(meta)
    posts.sort(key=lambda p: (p.get("date", ""), p.get("slug", "")), reverse=True)
    return posts


_HEAD = (
    '<!doctype html>\n<html lang="en">\n<head>\n'
    '<meta charset="UTF-8" />\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1.0" />\n'
    "<title>{title}</title>\n"
    '<meta name="description" content="{desc}" />\n'
    '<meta name="theme-color" content="#1e1e2e" />\n'
    '<link rel="icon" href="{p}assets/icon.svg" type="image/svg+xml" />\n'
    '<link rel="alternate" type="application/rss+xml" title="Axiom AI blog" href="{p}feed.xml" />\n'
    '<link rel="preconnect" href="https://fonts.googleapis.com" />\n'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />\n'
    '<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,600;1,9..144,500&family=Hanken+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet" />\n'
    '<link rel="stylesheet" href="{p}styles.css" />\n'
    "</head>\n<body>\n"
)


def _shell(prefix: str, title: str, desc: str, body: str) -> str:
    """Full page (banner + nav + body + footer), matching the rest of the site.

    ``prefix`` is the relative path back to the site root ("" for root pages,
    "../" for pages under blog/).
    """
    p = prefix
    head = _HEAD.format(title=html.escape(title), desc=html.escape(desc), p=p)
    nav = f"""        <div class="alpha-banner" role="alert">
            <div class="wrap alpha-inner">
                <span class="alpha-tag">EARLY ALPHA</span>
                <p>For testers: until <b>June&nbsp;30</b>, free API keys are built right in, so you can play with zero setup. Expect rough edges and breaking changes.</p>
            </div>
        </div>
        <header class="nav">
            <div class="wrap nav-inner">
                <a class="brand" href="{p}index.html#top"><img src="{p}assets/icon.svg" alt="Axiom AI logo" /><b>Axiom&nbsp;AI</b></a>
                <nav class="nav-links">
                    <a href="{p}index.html#how">How it works</a>
                    <a href="{p}index.html#features">Features</a>
                    <a href="{p}dev-updates.html">Roadmap</a>
                    <a href="{p}blog/index.html">Blog</a>
                    <a class="nav-cta" href="https://github.com/Frosoore/AxiomAI" target="_blank" rel="noopener">GitHub ↗</a>
                </nav>
            </div>
        </header>
"""
    footer = f"""        <footer>
            <div class="wrap">
                <div class="foot-bottom">
                    <span>AGPL-3.0-or-later · built by 17h59 &amp; Frosoore</span>
                    <span><a href="{p}feed.xml">RSS feed</a> · <a href="{p}blog/index.html">Blog</a> · <a href="{p}dev-updates.html">Dev updates</a></span>
                </div>
            </div>
        </footer>
"""
    return head + nav + body + footer + "    </body>\n</html>\n"


def _tldr(summary: list[str]) -> str:
    if not summary:
        return ""
    lis = "\n".join(f"                <li>{html.escape(s)}</li>" for s in summary)
    return (
        '            <div class="tldr"><span class="tldr-label">TL;DR</span>\n'
        f"            <ul>\n{lis}\n            </ul></div>\n"
    )


def _render_post_page(post: dict, md) -> str:
    meta = _fmt_date(post["date"])
    if post.get("author"):
        meta += f" · {html.escape(post['author'])}"
    body = (
        '        <article class="post">\n'
        '            <p class="post-back"><a href="index.html">← All posts</a></p>\n'
        f'            <h1 class="post-title">{html.escape(post["title"])}</h1>\n'
        f'            <p class="post-meta">{meta}</p>\n'
        f"{_tldr(post['summary'])}"
        f'            <div class="post-body">\n{md.render(post["body"])}\n            </div>\n'
        '            <p class="post-foot"><a href="index.html">← Back to the blog</a> · '
        '<a href="../index.html#top">Home</a></p>\n'
        "        </article>\n"
    )
    desc = post["summary"][0] if post["summary"] else post["title"]
    return _shell("../", f"{post['title']} · Axiom AI blog", desc,
                  '        <section class="post-section"><div class="wrap">\n'
                  + body + "        </div></section>\n")


def _render_blog_index(posts: list[dict]) -> str:
    cards = []
    for post in posts:
        meta = _fmt_date(post["date"])
        if post.get("author"):
            meta += f" · {html.escape(post['author'])}"
        bullets = "\n".join(
            f"                    <li>{html.escape(s)}</li>" for s in post["summary"]
        )
        tldr = f'                <ul class="card-tldr">\n{bullets}\n                </ul>\n' if bullets else ""
        cards.append(
            '            <article class="post-card">\n'
            f'                <p class="post-meta">{meta}</p>\n'
            f'                <h2><a href="{post["slug"]}.html">{html.escape(post["title"])}</a></h2>\n'
            f"{tldr}"
            '                <span class="post-readmore">Read →</span>\n'
            "            </article>"
        )
    listing = "\n".join(cards) if cards else '            <p class="du-empty">No posts yet.</p>'
    body = (
        '        <section class="blog-hero"><div class="wrap">\n'
        '            <p class="eyebrow">Blog</p>\n'
        "            <h1>News, deep dives, and the life of the project.</h1>\n"
        "            <p>The longer story behind what we build. For the terse, "
        'per-month changelog see <a href="../dev-updates.html">Dev updates</a>. '
        'Prefer a reader? Subscribe via <a href="../feed.xml">RSS</a>.</p>\n'
        "        </div></section>\n"
        '        <section class="blog-list-section"><div class="wrap blog-list">\n'
        + listing + "\n        </div></section>\n"
    )
    return _shell("../", "Blog · Axiom AI",
                  "News, deep dives and the life of the Axiom AI project.", body)


def _rss_date(iso: str) -> str:
    """RFC-822 date for the RSS feed, at 00:00 UTC. Empty/invalid -> "" (skipped)."""
    try:
        dt = datetime.strptime(iso, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return format_datetime(dt)
    except ValueError:
        return ""


def _render_rss(posts: list[dict]) -> str:
    # Deterministic: lastBuildDate tracks the newest post, never the wall clock,
    # so re-running the build with unchanged content leaves the feed byte-identical
    # (the --check CI guard relies on this).
    build_date = _rss_date(posts[0]["date"]) if posts else ""
    items = []
    for post in posts:
        link = f"{SITE_BASE}/blog/{post['slug']}.html"
        pub = _rss_date(post["date"]) or build_date
        desc = " / ".join(post["summary"]) if post["summary"] else post["title"]
        items.append(
            "    <item>\n"
            f"      <title>{_xml_escape(post['title'])}</title>\n"
            f"      <link>{_xml_escape(link)}</link>\n"
            f'      <guid isPermaLink="true">{_xml_escape(link)}</guid>\n'
            f"      <pubDate>{pub}</pubDate>\n"
            f"      <description>{_xml_escape(desc)}</description>\n"
            "    </item>"
        )
    body = "\n".join(items)
    last_build = f"    <lastBuildDate>{build_date}</lastBuildDate>\n" if build_date else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "  <channel>\n"
        "    <title>Axiom AI blog</title>\n"
        f"    <link>{SITE_BASE}/blog/index.html</link>\n"
        '    <atom:link href="' + SITE_BASE + '/feed.xml" rel="self" type="application/rss+xml" />\n'
        "    <description>News, deep dives and the life of the Axiom AI project.</description>\n"
        "    <language>en</language>\n"
        f"{last_build}"
        f"{body}\n"
        "  </channel>\n</rss>\n"
    )


def _build_blog(check: bool) -> list[str]:
    """Generate blog/index.html, blog/<slug>.html and feed.xml. Returns changed names."""
    posts = _load_posts()
    md = _md_renderer()
    outputs: dict[Path, str] = {
        BLOG_OUT / "index.html": _render_blog_index(posts),
        LANDING / "feed.xml": _render_rss(posts),
    }
    for post in posts:
        outputs[BLOG_OUT / f"{post['slug']}.html"] = _render_post_page(post, md)

    changed = []
    for path, content in outputs.items():
        old = path.read_text(encoding="utf-8") if path.exists() else None
        if old != content:
            changed.append(str(path.relative_to(LANDING)))
            if not check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
    return changed


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

    # Blog: full generated pages (index + one per article) and the RSS feed.
    changed += _build_blog(check)

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
