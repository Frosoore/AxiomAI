# Site content — edit these, the site rebuilds itself

The public **Dev page** (`landing/dev-updates.html`) and the home-page roadmap
teaser are **generated** from the two TOML files here. You don't touch HTML.

| File           | Drives                                                        |
|----------------|--------------------------------------------------------------|
| `roadmap.toml` | The roadmap: **Next up / Far away / Recently done** columns.  |
| `updates.toml` | The dev log (the month dropdown on the Dev page).            |

## How it works

On every push to `main`, a GitHub Action runs `landing/build_site.py`, which
reads these TOML files and fills the generated regions of the HTML, then
publishes to GitHub Pages. Two things are also auto-stamped at build time:

- the **engine version** (from `axiom/__init__.py`),
- the **“last updated”** date + commit hash.

GitHub stats (stars, latest release, PyPI version, open issues) are live badges
that refresh on their own — nothing to edit.

## Editing

- **Move a roadmap item** (e.g. it just shipped): open `roadmap.toml`, change
  that item's `status` from `"next"` to `"done"`, optionally add `date = "YYYY-MM"`.
- **Add a dev-log entry**: add a new `[[update]]` block at the **top** of
  `updates.toml` (newest first). Inline `<code>…</code>` / `<b>…</b>` is allowed.
- **Draft a dev-log entry from recent commits** (then trim it by hand):

  ```bash
  python landing/build_site.py --draft-update            # last 30 commits
  python landing/build_site.py --draft-update v0.1.6     # since a tag/ref
  ```
  It collects `feat:` / `fix:` commits into an `Added` / `Fixed` block to paste.

## Preview locally

```bash
python landing/build_site.py        # regenerate the HTML from the TOML
# then open landing/dev-updates.html in a browser
python landing/build_site.py --check   # CI guard: nonzero if HTML is stale
```
