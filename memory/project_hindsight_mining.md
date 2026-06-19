---
name: project-hindsight-mining
description: Chantier "Hindsight Mining" — refonte ambitieuse de la mémoire du moteur (recherche + croyances), deux modes togglables ; Phases 1→4 IMPLÉMENTÉES et COMMITÉES (2965279) le 2026-06-18 ; restent TICKET-073/072/074-076
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
**Côté MOTEUR la Phase 2 est COMPLÈTE** (items 1,2,3,5) + couche app item 4 (worker QThread + panneau
GUI Mémoire + i18n ×10). Doc Sphinx mise à jour (guide `docs/guides/memory.md` + API `docs/api/memory.md`).

**Phase 3 (croyances/observations) COMPLÈTE le 2026-06-18** — moteur : table `Observations`,
`axiom/observations.py` (stockage + `rollback_observations` turn-keyed atomique branché dans
`checkpoint.rewind`), `axiom/consolidate.py` (consolidateur LLM CREATE/UPDATE/DELETE, garde-fous fact_ids
hallucinés), injection hiérarchique `Belief:`→`Known fact:`→chunks dans l'arbitrator, faits+croyances
ajoutés à l'export `.axiomsave` ; app : `workers/fact_worker.py` chaîne la consolidation post-extraction,
toggle GUI « Croyances évolutives » (grisé hors Vivant), i18n+doc ×10. `config.memory_beliefs_enabled` +
helper `memory_beliefs_active`. Suite 872 ✅. Détail `maintenance/hindsight-phase3-croyances/`.

**Phase 4 (périmètre demandé : B-3 + prompt caching) COMPLÈTE le 2026-06-18** — B-3 missions de croyance
par perso/univers (`axiom/missions.py`, stockage `Universe_Meta` `belief_mission`/`belief_missions` JSON →
zéro schéma, round-trip `[extra]`, section « Character memory styles » dans `consolidate`, champ GUI Studio
Metadata) ; prompt caching Gemini (cache explicite guardé/opt-in/fallback gracieux dans `GeminiClient`,
seuil `_PROMPT_CACHE_MIN_CHARS=8000`, `config.memory_prompt_cache_enabled` — honnête : no-op pour nos
petits prompts). Suite 884 ✅. Détail `maintenance/hindsight-phase4-raffinements/`.

**TOUT COMMITÉ le 2026-06-18** : commit `2965279` "hindsight inspired modifications", branche
`hindsight-idead`, poussé sur origin (arbre de travail propre). Restent NON demandés : modèles mentaux
(§7.8), directives/persona (§7.9), extraction temporelle (§7.5). **Cluster de follow-ups TICKET-073/074/
075/076 IMPLÉMENTÉ le 2026-06-19** (⚠ NON commité, `maintenance/hindsight-followups-073-076/`) : 073
noms des persos en scène ajoutés à `focus_terms` (réordonnancement maîtrisé, cap 5) ; 075 rewind
« dé-tire » `Fired_Scheduled_Events` (colonne `fired_turn_id` + purge) ; 074 rewind restaure
`Active_Modifiers` (décision user = **Option A snapshot par tour** : table `Modifier_Snapshots` +
`snapshot_modifiers`/`rollback_modifiers`) ; 076 champ mort `config.chronicler_interval` retiré (load_config
filtre les clés inconnues → vieux settings OK). Suite **901 verte**.

**TICKET-072 (lore book sémantique + link expansion) IMPLÉMENTÉ le 2026-06-19** (⚠ NON commité,
`maintenance/ticket-072-lore-semantic/`) — re-mining Hindsight `link_expansion_retrieval`. `VectorMemory` :
`sync_lore` (embed turn 0 idempotent, survit rewind), `query(chunk_type/exclude_chunk_type)` + `entry_id`,
`embed_chunk(metadata_extra)`. Arbitrator : `_fetch_relevant_lore` sémantique dédié → `_expand_lore`
(catégorie/mots-clés partagés, budget 2) → repli mots-clés si embedding indispo ; requête narrative exclut
le lore. Suite **908 verte**, doc EN+FR (sphinx -W EXIT 0). **→ Tout le chantier Hindsight (recherche +
faits + croyances + 073/074/075/076 + 072) est désormais clos.** Restent NON demandés : modèles mentaux
(§7.8), directives/persona (§7.9), extraction temporelle (§7.5).

**QA du chantier (2026-06-19, ⚠ NON commité, `maintenance/qa-hindsight-2026-06-19/`)** : gros contrôle
qualité demandé. Verdict = code de très haute qualité, **aucun bug de correction**. 6 findings de
coût/scaling (mode « living ») + robustesse → PENDING TICKET-077→082. **4 corrigés** : 077 (prompt de
consolidation borné : `consolidate(max_existing=24)` scope aux sujets du batch + récentes), 078 (cache
d'index BM25 dans `memory.query` par empreinte d'ids du corpus → le lore figé ne reconstruit plus chaque
tour ; `lexical.build_bm25`/`rank_with_bm25` séparés), 079 (`get_facts`/`get_observations` `LIMIT` SQL
sans filtre ; arbitrator `_fetch_relevant_facts/_beliefs` = 1 lecture + priorisation mémoire, M+1→1), 080
(`insert_facts` stampe `fact_id`/`turn_id` en place, fin du couplage `zip` dans `fact_worker`). Suite
périmètre vert + tests neufs (scope_existing, stamping, cache BM25). **TICKET-081 (feature `Trend`)
IMPLÉMENTÉ ensuite** : `axiom/observations.py::compute_trend(source_turns, now_turn)` + `TREND_*` +
`Observation.trend()` (algo Hindsight `reflect/observations.py` transposé jours→`turn_id`, fenêtres
15/45, zéro LLM, calcul à la volée, pas de schéma) ; arbitrator annote les croyances à signal directionnel
(`strengthening`/`weakening`/`stale` → « … (stale) »), `new`/`stable` nues. **Vue GUI livrée** :
`ui/memory_browser.py::MemoryBrowserDialog` (lecture seule, onglets Croyances [tendance colorée] + Faits,
bornés au tour courant) + bouton « Explorer la mémoire… » dans les réglages (signal `view_memory_requested`
→ `tabletop_view.open_memory_browser`), i18n 24 clés ×10, tests `test_memory_browser.py`. **Doc Sphinx
moteur** EN+FR à jour (section *Belief trends* + cache BM25 + scoping consolidation dans
`docs/guides/memory.md` ; FR via gettext `.po`/`.mo`), notes d'API non touchées (auto). Suites vertes.
**Ouvert** : 082 (modèles mentaux §7.8 / directives §7.9 / extraction temporelle §7.5).

Respecter [[user-profile-non-coder]] (expliquer les dépendances/archi avant de trancher) et
[[feedback-execution-style]] (no superpowers, no commit sans feu vert).
