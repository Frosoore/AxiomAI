# Axiom Status

> **What this is.** A running, human-readable history of the project: what we **do**, what we
> **fix**, what we **implement**, and what we **break**. It is the narrative companion to the
> machine-formatted [`Changelog.md`](Changelog.md): shorter, plain-language, status-oriented.
>
> **🔴 The rule: update this file on every commit.** Whoever commits (a human, or an AI assistant
> like Claude / Gemini) adds **one entry at the top** of the log below, in the same change. A commit
> that touches code without a matching Axiom Status line is incomplete. Keep entries short and
> honest, including when something regressed or is still broken.
>
> **Stage of the project:** 🟧 **early alpha** (not beta). Expect rough edges and breaking changes.

---

## How to add an entry (for a human or an LLM)

Prepend a new bullet at the very top of the **Log** section, newest first, in this shape:

```
- **YYYY-MM-DD** · `<scope>` · <type>: <one-line, plain-language description>.
```

- `<scope>`: the area touched: `engine`, `ui`, `cli`, `docs`, `site`, `tests`, `ci`, `build`…
- `<type>`: one of: **add** · **fix** · **change** · **remove** · **break** · **chore**.
- Keep it to one line. If it matters to a player or a tester, say so in plain words.
- Once a month, distil the entries since the previous month into a summary on the
  **Dev updates** page (`landing/dev-updates.html`); that page is the public, monthly view of
  this same history.

---

## Log

<!-- Newest first. Add your line directly under this comment on every commit. -->

- **2026-06-16** · `site` · add: Created `AXIOM_STATUS.md` and the monthly **Dev updates** page; added an early-alpha tester banner, a feature-request form and Discord links to the landing site.
- **2026-06-16** · `docs` · change: Reframed the project status from “beta” to **early alpha** across the website and README.
