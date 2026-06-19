# TODO — Hindsight follow-ups 073/074/075/076

## TICKET-073 — Focus boost noms persos ✅
- [x] Remonter la lecture noms/types + persona avant la requête RAG (réordonnancement maîtrisé).
- [x] Construire `focus_terms = [lieu] + noms des persos en scène` (borné), avant `query`.
- [x] Test arbitrator : `focus_terms` reçu par `query` contient les noms en scène. 43/43 verts.

## TICKET-074 — Rewind Active_Modifiers ✅ (Option A : snapshot par tour)
- [x] Table `Modifier_Snapshots` + `ensure_modifier_snapshots_table` (auto-migration).
- [x] `snapshot_modifiers` (post-tick, no-op si vide) appelé par l'arbitrator ; `rollback_modifiers`
      branché dans `checkpoint.rewind` (atomique).
- [x] Round-trips savestore/package. Tests checkpoint + modifier_processor. 82 verts.

## TICKET-075 — Rewind Fired_Scheduled_Events ✅
- [x] Colonne `fired_turn_id` + `ensure_fired_event_turn_column` (auto-migration).
- [x] `_mark_event_as_fired` enregistre le tour ; purge au rewind par `fired_turn_id > N`.
- [x] Tests checkpoint (futur/passé/legacy) + arbitrator (tag). 59 + 97 verts.

## TICKET-076 — Nettoyage chronicler_interval ✅
- [x] Grep exhaustif : aucun chemin de déclenchement ne lit `chronicler_interval`.
- [x] Champ retiré (config + GUI collect_config + `_loaded_config`) ; load_config filtre les clés
      inconnues → anciens settings OK (couvert par `test_unknown_keys_ignored`).
- [x] test_config réfs remplacées. config 29 + dialog 14 verts.
