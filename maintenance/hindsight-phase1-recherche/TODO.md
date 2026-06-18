# TODO — Phase 1 (couche recherche)

## Item 1 — refonte du scoring ✅ (2026-06-18)
- [x] Remplacer `final_score = semantic × time_weight` par la forme multiplicative modulée.
- [x] Récence calculée en âge de **tours** (`turn_id`), neutre (0,5) pour lore / turn_id 0 / pas de current.
- [x] Constantes de calibrage (`_RECENCY_ALPHA`, horizon de tours) en tête de module.
- [x] Nettoyer le filtre mort résiduel (`arbitrator.py:229`, `session.py:661`) — rendu correct (`chunk_type`).
- [x] Conserver les clés de résultat (`text/turn_id/chunk_type/distance/score`).
- [x] Tests : `test_vector_memory.py` vert (28) + 2 tests de la nouvelle modulation ; arbitrator/session OK.

## Item 2 — arme lexicale BM25 + fusion RRF ✅ (2026-06-18)
- [x] `axiom/retrieval/fusion.py` (RRF + cap). [interleave reporté : utile surtout pour la dédup
      des croyances en Phase 3, pas pour la recherche].
- [x] Arme lexicale `rank_bm25` (`axiom/retrieval/lexical.py`) branchée à côté du sémantique Chroma,
      fusion RRF, base = score RRF normalisé. Dégradation gracieuse si `rank_bm25` absent.
- [x] Dépendance `rank-bm25` ajoutée (pyproject + requirements). Tests dédiés. Suite 807 ✅.

## Item 3 — cross-encoder optionnel ✅ (2026-06-18)
- [x] `axiom/retrieval/reranker.py` (`CrossEncoderReranker`) + fallback no-op (Windows/torch HS).
- [x] Branché dans `VectorMemory.query` (remplace la base quand activé) ; flag config
      `memory_reranker_enabled` (OFF) ; câblage `session.py` ; tests (modèle injecté). Suite 813 ✅.
- [ ] ⏳ Exposition GUI du toggle → à faire avec le panneau « mémoire » de la **Phase 2**
      (avec `memory_mode` Léger/Vivant + i18n ×10).

## Item 4 (option) — finition ✅ (2026-06-18)
- [x] Boost de focus moteur (`focus_terms` + `_FOCUS_BOOST`, match tous-tokens). Tests.
- [x] Câblage arbitrator : **lieu en scène** passé en `focus_terms` (zéro coût ajouté).
- [ ] ⏳ Suivi : **noms des persos en scène** en focus (besoin de la table id→nom ; éviter de réordonner
      le hot path) → consigné dans PENDING.

## ✅ Phase 1 terminée — items 1→4 livrés, suite 815 ✅, offline/déterministe/rollback OK.
</content>
