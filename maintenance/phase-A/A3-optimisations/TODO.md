# A3 — Optimisations chirurgicales (Phase A, section 3 du doc d'upgrade)

Réf : `maintenance/AXIOM_AI_UPGRADE_DETAILS.md` §3.

| # | Optimisation | Fichier(s) | Statut |
|---|-------------|------------|--------|
| 3.1 | N+1 connexions SQLite → 2 requêtes globales | `core/arbitrator.py` | ✅ fait |
| 3.2 | Batch des `append_event` (1 transaction/tour) | `database/event_sourcing.py` + `core/arbitrator.py` | ✅ fait |
| 3.3 | Cache mémoire `_stats_cache` dans Arbitrator | `core/arbitrator.py` + `ui/tabletop_view.py` | ✅ fait |
| 3.4 | `print()` → `logger` (14 occurrences) | 5 fichiers | ✅ fait |
| 3.5 | Cache hash pip install dans `run.sh` | `run.sh` | ✅ fait |
| 3.6 | Retirer `sentence_transformers`/`chromadb` du startup_check | `debug/startup_check.py` | ✅ fait |
