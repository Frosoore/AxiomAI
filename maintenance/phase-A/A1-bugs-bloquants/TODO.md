# A1 — Bugs bloquants (Phase A, section 1 du doc d'upgrade)

Réf : `maintenance/AXIOM_AI_UPGRADE_DETAILS.md` §1.

| # | Bug | Fichier | Statut |
|---|-----|---------|--------|
| 1.1 | `ChroniclerEngine` instancié avec 1 seul arg | `ui/tabletop_view.py` | ✅ fait |
| 1.2 | `rewind_to_checkpoint` inexistante (→ `execute_rewind`) | `ui/tabletop_view.py` | ✅ fait |
| 1.3 | Suppression aveugle widget statusbar | `ui/main_window.py` | ✅ fait |
| 1.4 | `tick_modifiers` ticke 1 min fixe | `core/arbitrator.py` | **reporté → Pilier 5** |
| 1.5 | `TimekeeperWorker` importé jamais instancié | `ui/tabletop_view.py` | **reporté → Pilier 5** |
| 1.6 | Race condition `DELETE FROM Entity_Stats` | `workers/db_worker.py` | ✅ fait |
| 1.7 | `get_translations_dict()` manquante | `core/localization.py` | ✅ déjà présent (doc obsolète) |
| 1.8 | `CreatePlayerEntityTask` dupliquée | `workers/db_tasks.py` | ✅ déjà résolu (1 seule def) |
| 1.9 | MapEditor affiche "m" stocke "km" | `ui/widgets/map_editor.py` | ✅ fait |
| 1.10 | Tests `debug/` jamais ramassés par pytest | `debug/test_*.py` | ✅ audité — conservés intentionnellement (voir CHANGELOG) |

## Notes
- 1.4 et 1.5 sont marqués "Fix lié au Pilier 5" dans le doc → ne pas tenter de fix complet ici, juste laisser en l'état (déjà fonctionnel par hardcode) jusqu'à la Phase B.
- Vérifier chaque référence `fichier:ligne` au moment de coder (le doc peut avoir dérivé).
- 1.1 : ajouter test d'intégration (50 turns sans exception) si faisable rapidement.
