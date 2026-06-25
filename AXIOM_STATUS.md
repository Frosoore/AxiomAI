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

- **2026-06-23** · `engine` · add: Structured JSON output for pure-JSON LLM calls (Pilier 8, §23.2). Backends gained an optional `response_schema`; Gemini now honors JSON mode (`response_mime_type` + `response_json_schema`) — it ignored it before, so populate/consolidate/fact-extraction/Timekeeper all silently relied on regex; Ollama passes the schema as `format`; the Timekeeper requests a strict `{elapsed_minutes}` schema. UniversalClient stays on `json_object` for cross-provider safety. The streamed narrative turn keeps the regex fallback by design. +9 tests.
- **2026-06-23** · `engine` · add: Arbitrator now enforces declared stat bounds deterministically (Pilier 8, §23.2): `min`/`max` and enumerated `allowed` values declared in `Stat_Definitions.parameters` (JSON, zero schema migration), plus `Location` must be a known place. Over-max assignments clamp to the ceiling; below-min/invalid-enum/illegal-teleport are rejected. Stats without declared bounds are unaffected (retro-compat); +7 tests.
- **2026-06-23** · `engine` · fix: Companion "plot armor" now actually keeps the Hero alive: a would-be-negative resource change is floored at 0 (was applied raw, dropping the Hero below 0). `_validate_change` returns a `(valid, reason, clamp_value)` triple; +1 regression test.
- **2026-06-23** · `site` · add: Blog post "We asked an AI to tear Axiom apart" (Arbitrator + competitive audit write-up); refreshed the Dev-page roadmap (new Arbitrator-reliability and cost-controls items, NPC item narrowed to the actor model since memory shipped).
- **2026-06-21** · `chore` · change: Renamed the author pseudonym `17h59` to `Pinpanicaille` across the tree (NOTICE, README, docs, landing site, Myria credit).
- **2026-06-21** · `ui` · fix: `retranslate_tooltips` no longer crashes on language change when a documented widget's C++ object was already deleted (CI 3.12 flake); guard + prune via `shiboken6.isValid`.
- **2026-06-21** · `site` · add: Blog post "Under the hood: how saves and universes work"; moved the save/universe QC item to Done on the roadmap and logged it in the June dev update.
- **2026-06-21** · `engine` · fix: `fired_turn_id` is preserved when exporting (`extract_save`/`.axiomsave`) and forking a save, so rewind can still un-fire scheduled events; added a guard test against save copy-list vs schema drift.
- **2026-06-20** · `ui` · fix: Player message editor now correctly rolls back VectorMemory semantic database and cleans up illustration assets.
- **2026-06-20** · `ui` · fix: Aligned memory and database user_input turn IDs to prevent complete history deletion during message rollbacks.
- **2026-06-16** · `site` · add: Created `AXIOM_STATUS.md` and the monthly **Dev updates** page; added an early-alpha tester banner, a feature-request form and Discord links to the landing site.
- **2026-06-16** · `docs` · change: Reframed the project status from “beta” to **early alpha** across the website and README.
