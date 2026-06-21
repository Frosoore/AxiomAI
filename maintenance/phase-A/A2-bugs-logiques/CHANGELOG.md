# A2 — Changelog

## 2026-05-22
- **2.1** `core/arbitrator.py:351` : ajout de `_seen_rule_signatures: set[str]`. La boucle de chaining passe de O(N²) (recompose la signature + `any()` sur `triggered_rules`) à O(1) (lookup set). Aucun changement de comportement.
- **2.2** `ui/tabletop_view.py` : connexion `rewind_complete → _on_rewind_done` déplacée dans `_start_workers` (setup permanent). Retrait du `connect()` dynamique dans `_show_rewind_dialog` et du `disconnect()` dans `_on_rewind_done`. Ajout du flag `_rewind_in_progress` pour ignorer les rewinds concurrents.
- **2.3** `ui/tabletop_view.py:738` : `@Slot()` → `@Slot(dict)`, signature `_on_rewind_done(self, summary: dict)`. Aligne le slot avec `Signal(dict)` déclaré dans `db_worker.py:46`.
