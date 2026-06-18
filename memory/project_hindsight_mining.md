---
name: project-hindsight-mining
description: Chantier "Hindsight Mining" — refonte ambitieuse de la mémoire du moteur (recherche + croyances), deux modes togglables ; doc de handoff prête, no code
metadata:
  type: project
---

Chantier décidé le 2026-06-17 : **miner les algorithmes et le modèle de connaissance de Hindsight**
(système de mémoire agentique open-source MIT, [github.com/vectorize-io/hindsight](https://github.com/vectorize-io/hindsight))
et **refondre la mémoire du moteur Axiom**, adaptée à notre stack (ChromaDB + SQLite + sentence-transformers
+ `LLMBackend`), **sans** porter leur serveur Postgres+FastAPI.

**Clone de référence** : `/home/garen/coding/hindsight/` (HORS de l'arbre git, lecture seule, MIT). Le jus
algorithmique est dans `hindsight-api-slim/hindsight_api/engine/` (`search/` = recherche sans LLM ;
`retain/`, `consolidation/`, `reflect/` = cognition LLM).

**Cap fixé par l'utilisateur** : viser le MEILLEUR système possible, dépendances autorisées, croyances
prioritaires, et **DEUX MODES togglables** — *Léger* (déterministe, hors-ligne, zéro LLM) / *Vivant*
(LLM : extraction de faits + croyances qui évoluent + modèles mentaux). Le rollback des croyances est
résolu (via `source_memory_ids` + `_filter_live_source_memories` + recalcul). Synergie repérée avec le
Pilier 5 (relations causales entre faits).

**État (2026-06-18)** : reconnaissance faite (`maintenance/hindsight-mining/`) **et Phase 1 IMPLÉMENTÉE**
(`maintenance/hindsight-phase1-recherche/`). Décisions tranchées : arme lexicale = **`rank_bm25`**,
cross-encoder = **optionnel OFF par défaut**, mode par défaut = **Léger**.
Phase 1 (Mode Léger / recherche, sans LLM, offline, déterministe, rollback intact) — items 1→4 livrés :
1) scoring `memory.py:query` refondu (récence **modulée** ±10 % en `turn_id`, plus « écrasée ») ;
2) **recherche hybride** sémantique (Chroma) + lexicale (BM25) → fusion **RRF** (nouveau pkg
`axiom/retrieval/` : `fusion.py`, `lexical.py`) ; 3) **cross-encoder optionnel** (`reranker.py`,
flag `config.memory_reranker_enabled`, no-op gracieux Windows/torch) ; 4) **focus boost** de scène
(`focus_terms`, lieu câblé dans l'arbitrator ; noms persos = TICKET-073). Dépendance ajoutée :
`rank-bm25`. **Non commité** (attente feu vert). Plan : P1 ✅ → P2 (en cours) → P3 croyances → P4 raffinements.

**Phase 2 (infra deux modes + faits)** — `maintenance/hindsight-phase2-faits/`, démarrée 2026-06-18,
items 1-3 faits : 1) toggle **`config.memory_mode`** (« lite »/« living », défaut lite) +
`memory_mode_is_living()` ; 2) **table SQLite `Facts`** (who/what/when/where/why + type + entités +
statement, clé save_id+turn_id) via `axiom/facts.py`, **rollback branché dans `checkpoint.rewind`**
(faits supprimés atomiquement avec les events) ; 3) **extraction LLM** `axiom/factextract.py` (prompt
adapté Hindsight, `LLMBackend.complete` JSON, dégradation gracieuse, mocké en test). Config :
`memory_fact_interval` (N tours, désactivable) + `memory_fact_model` (override). 5) **faits injectés dans
le prompt** : `arbitrator._fetch_relevant_facts` (scène d'abord, puis récents, borné `max_turn_id`),
fusionnés en tête de `rag_chunks` (`Known fact:`) **en `living` seul** (`lite` inchangé). Suite **844 ✅**.
**Décisions user (2026-06-18)** : extraction tous les N tours (N réglable/désactivable) + bouton « à la
demande » (reset N) ; modèle = backend configuré par défaut, surchargeable ; causal différé.
**Côté MOTEUR la Phase 2 est COMPLÈTE** (items 1,2,3,5). **Doc Sphinx mise à jour** (guide
`docs/guides/memory.md` + API `docs/api/memory.md`, build `-W` OK). **Reste item 4 = app-layer** (worker
QThread + panneau GUI Mémoire + i18n ×10), **documenté** dans `maintenance/hindsight-phase2-faits/ITEM4_HANDOFF.md`.
**Non commité.**

Respecter [[user-profile-non-coder]] (expliquer les dépendances/archi avant de trancher) et
[[feedback-execution-style]] (no superpowers, no commit sans feu vert).
