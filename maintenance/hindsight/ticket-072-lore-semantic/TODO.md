# TODO — TICKET-072 Lore sémantique + link expansion

## Moteur — VectorMemory ✅
- [x] `embed_chunk(metadata_extra=)` (entry_id sur les chunks lore).
- [x] `query(chunk_type=, exclude_chunk_type=)` + `entry_id` renvoyé + where_cond généralisé.
- [x] `sync_lore(save_id, entries)` idempotent (delete + ré-embed turn 0).

## Moteur — Arbitrator ✅
- [x] `_fetch_relevant_lore` : sync paresseux 1×/session, requête sémantique dédiée → `_expand_lore`
      (link expansion category/keywords) ; repli `_fetch_lore_by_keywords`.
- [x] Requête narrative : `exclude_chunk_type="lore"`.

## Tests ✅
- [x] VectorMemory (TestLoreSync) + Arbitrator (TestLoreSemanticRetrieval). Suite 908 verte.

## Doc ✅
- [x] Guide mémoire EN section « Lore Book retrieval » + FR traduit. Builds EN/FR strict EXIT 0.
