# A3 — Changelog

## 2026-05-22
- **3.1** `core/arbitrator.py` : `_fetch_effective_stats` remplacé — 2N+1 connexions → 1 conn + 2 SELECT globaux (`State_Cache` + `Active_Modifiers`). `fmt_num` importé inline.
- **3.2** `database/event_sourcing.py` : ajout de `append_events_batch`. `core/arbitrator.py` : `process_turn` collecte les events dans `_pending_events` (list), flush unique via `append_events_batch` à la fin du tour. Seuls `user_input` et `hero_intent` restent immédiats. `_apply_inventory_change` accepte `pending_events` optionnel.
- **3.3** `core/arbitrator.py` : `_stats_cache: dict|None` — seedé depuis `_fetch_effective_stats` si None, mis à jour depuis `all_stats` en fin de tour, invalidé par `invalidate_stats_cache()`. `ui/tabletop_view.py` : appel à `invalidate_stats_cache()` dans `_on_rewind_done`.
- **3.4** `print()` → `logger.debug/error` dans 5 fichiers : `core/arbitrator.py` (3), `core/chronicler.py` (1), `workers/db_helpers.py` (2), `workers/db_tasks.py` (3), `workers/timekeeper_worker.py` (1), `database/schema.py` (4). Import `from core.logger import logger` ajouté dans chacun.
- **3.5** `run.sh` : `pip install` conditionnel basé sur hash `sha256sum requirements.txt`. Skip si `$VENV_DIR/.deps_hash` correspond → ~3-5 sec économisées au lancement quotidien.
- **3.6** `debug/startup_check.py` : `sentence_transformers` et `chromadb` retirés du check import au démarrage (chargeaient torch ~500 MB avant que la fenêtre soit visible).
- 61 tests arbitrator+event_sourcing+modifier_processor : tous verts.
- Note : `State_Cache` n'est toujours pas mis à jour après les tours côté sidebar → TICKET-002 ouvert dans PENDING.md.
