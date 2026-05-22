# A4 — Nettoyage code mort (Phase A, section 4 du doc d'upgrade)

Réf : `maintenance/AXIOM_AI_UPGRADE_DETAILS.md` §4.

| Item | Fichier | Statut |
|------|---------|--------|
| Import `TimekeeperWorker` inutilisé | `ui/tabletop_view.py:45` | ✅ fait |
| Définition dupliquée `CreatePlayerEntityTask` | `workers/db_tasks.py` | ✅ déjà résolu (A1-1.8) |
| `debug/test_*.py` | — | ✅ traité en A1-1.10 (conservés intentionnellement) |
| Commentaires `# Hacky, but works` | — | ✅ déjà supprimé (A1-1.3) |
