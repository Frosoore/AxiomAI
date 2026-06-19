# Phase 1 — Couche recherche (Mode Léger, sans LLM)

Étape de code du chantier **Hindsight Mining** (voir `../hindsight-mining/DOC.md` pour la reconnaissance
complète, les ancres et le plan par phases). Objectif : refondre la recherche mémoire d'Axiom en
important les algorithmes de Hindsight **sans LLM, sans réseau, en restant déterministe et offline**.

## Décisions (2026-06-18)
- Arme lexicale : **`rank_bm25`** (lib Python pure). Cross-encoder : **optionnel, OFF par défaut**.
- On démarre par l'**item 1 : refonte du scoring** de `axiom/memory.py:query`.

## Items
1. **Scoring multiplicatif modulé + récence en `turn_id` + passthrough** — remplace
   `final_score = semantic × time_weight` (récence qui écrase, plancher 0,10) par la forme de Hindsight
   `score = base × recency_boost` où `recency_boost = 1 + α·(recency − 0,5)` (modulation ±α/2, défaut
   α=0,2 → ±10 %). La récence est calculée en **âge de tours** (`current_turn_id − turn_id`) et non en
   jours. Lore / `turn_id == 0` / pas de `current_turn_id` → récence neutre (0,5 → boost 1,0).
2. Arme lexicale BM25 + fusion RRF (`axiom/retrieval/`).
3. Cross-encoder optionnel + fallback no-op.
4. (option) boosts de stratégie (lieu/perso en scène).

## Invariants re-testés à chaque item
- Rollback par `turn_id` intact · tests déterministes verts · offline (zéro réseau) · dégradation
  gracieuse (`_disabled`).

## Réf Hindsight (clone hors-repo, MIT)
`hindsight-api-slim/hindsight_api/engine/search/reranking.py:20` (`apply_combined_scoring`),
`:15-17` (alphas), `:87-98` (passthrough). Algo **réécrit** adapté à Chroma/`turn_id` (jamais copié).
</content>
</invoke>
