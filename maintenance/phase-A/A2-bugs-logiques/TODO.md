# A2 — Bugs logiques (Phase A, section 2 du doc d'upgrade)

Réf : `maintenance/AXIOM_AI_UPGRADE_DETAILS.md` §2.

| # | Bug | Fichier | Statut |
|---|-----|---------|--------|
| 2.1 | Déduplication O(N²) dans RulesEngine chaining | `core/arbitrator.py` | ✅ fait |
| 2.2 | Disconnect-then-reconnect du signal `rewind_complete` | `ui/tabletop_view.py` | ✅ fait |
| 2.3 | `Signal(dict)` mais slot `@Slot()` sans param | `workers/db_worker.py` + `ui/tabletop_view.py` | ✅ fait |
