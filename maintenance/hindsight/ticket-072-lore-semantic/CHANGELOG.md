# CHANGELOG — TICKET-072 Lore sémantique + link expansion

## 2026-06-19 — Démarrage
- Étape créée. Décisions user : sémantique + link expansion ; requête lore dédiée.
- Re-mining Hindsight : `link_expansion_retrieval.py` (expansion entités/kNN/causal) → adapté en
  expansion category/keywords à la volée (table petite, pas de graphe pré-calculé). `query_analyzer`
  (temporel) = §7.5 différé ; `graph_retrieval` kNN précalculé = overkill ; `tags` ≈ notre `category`.
- Lecture : `_fetch_relevant_lore` (scorer mots-clés), `Lore_Book` (entry_id/category/name/keywords/content),
  `VectorMemory.embed_chunk`/`query`.

### Implémentation ✅
- **`axiom/memory.py`** : `embed_chunk(..., metadata_extra=)` (stocke `entry_id` sur les chunks lore) ;
  `query(..., chunk_type=, exclude_chunk_type=)` (where_cond généralisé en `$and`, `$eq`/`$ne`) et
  renvoie `entry_id` par candidat ; **`sync_lore(save_id, entries)`** (delete des chunks lore existants
  + ré-embed turn_id=0 → survit au rewind ; idempotent).
- **`axiom/arbitrator.py`** : requête narrative → `exclude_chunk_type="lore"` (ne gaspille pas le budget k).
  `_fetch_relevant_lore` réécrit : sync paresseux 1×/session (`self._lore_synced`), requête sémantique
  lore dédiée → graines `entry_id` → **`_expand_lore`** (link expansion : même `category` +2 / tokens
  `keywords` partagés, top `_LORE_LINK_BUDGET=2`) ; repli **`_fetch_lore_by_keywords`** (impl historique)
  si vm absent/`_disabled` ou pas de graine. Helpers `_load_lore_rows`, `_sync_lore_embeddings`,
  `_lore_tokens`.
- **Tests** : `test_vector_memory.py::TestLoreSync` (entry_id renvoyé, lore exclu du narratif, sync
  idempotent, survit au rollback) ; `test_arbitrator.py::TestLoreSemanticRetrieval` (link expansion
  déterministe même catégorie, chemin sémantique pris si vm présent, repli mots-clés si vm absent).
  Faux embedder = vecteurs aléatoires → on teste la plomberie + le link expansion en unitaire (pas la
  pertinence sémantique elle-même). **Suite complète 908 verte** (901 + 7 ambiance).
- **Doc** : guide mémoire (EN) section « Lore Book retrieval » (sémantique + link expansion + repli) +
  **FR traduit** ; builds EN & FR `sphinx -W` = EXIT 0. `conf.py` intersphinx restauré.

## TICKET-072 COMPLET. Non commité (attente feu vert). Dernier follow-up du chantier Hindsight clos.
