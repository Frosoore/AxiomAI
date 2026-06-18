# Hindsight Mining — refonte ambitieuse de la mémoire du moteur Axiom

> **Nature de cette page.** Doc de *préparation / handoff*, pas une étape de code.
> Objectif : qu'un agent au contexte vierge puisse reprendre le chantier en sachant
> **exactement où chercher, quoi chercher, dans quel but, et avec quelles contraintes**.
> **Aucun code n'a encore été écrit.** Cette page est de la reconnaissance technique + un plan cible.
>
> Rédigée le 2026-06-17, enrichie le même jour après cadrage avec l'utilisateur (voir §1.1).
> Les ancres `fichier:ligne` côté Hindsight valent pour le clone décrit en §3 (commit `55f70e1d`) —
> **les revérifier par grep** avant de coder, le repo amont bouge vite.

---

## 0. TL;DR pour l'agent qui reprend

On ne *porte pas* le serveur Hindsight (FastAPI + Postgres/pgvector + pipelines LLM). On **mine ses
algorithmes et son modèle de connaissance**, et on les **réimplémente, adaptés à notre stack**
(ChromaDB + SQLite + sentence-transformers + notre `LLMBackend`), en préservant nos invariants
(rollback par `turn_id`, déterminisme des tests, jeu jouable hors-ligne).

**Cap fixé par l'utilisateur (2026-06-17) : viser le MEILLEUR système possible, pas le minimum.**
- Phase 1 (recherche) **et** Phases 2-3 (faits + croyances) sont **toutes prioritaires** ;
- les **dépendances supplémentaires sont acceptées** (rank_bm25, cross-encoder, etc.) ;
- livrer **DEUX MODES togglables** par préférence utilisateur :
  - **Mode Léger** (déterministe, hors-ligne, **zéro LLM** côté mémoire) ;
  - **Mode Vivant** (LLM : extraction de faits, croyances qui évoluent, raisonnement).

La grande nouvelle technique : **Hindsight lui-même supporte `llm_provider="none"`** et des flags
`ENABLE_OBSERVATIONS` / `ENABLE_AUTO_CONSOLIDATION` — *leur* archi se dégrade déjà proprement sans LLM.
Ça **valide architecturalement le toggle deux modes** : le Mode Léger = couche recherche seule ; le
Mode Vivant = couche recherche + couche cognitive (croyances). Voir §6.

Et le **rollback des croyances** (le point dur, §8) a une solution née de leur code :
`source_memory_ids` + `_filter_live_source_memories` + recalcul.

---

## 1. Objectif & ambitions

**Constat.** La mémoire narrative d'Axiom (`axiom/memory.py`) est un RAG basique : recherche purement
sémantique (ChromaDB) + pondération de récence linéaire maison. Hindsight (open-source MIT,
[github.com/vectorize-io/hindsight](https://github.com/vectorize-io/hindsight)) fait l'état de l'art
(91,4 % LongMemEval) avec : recherche hybride (sémantique + lexical + graphe + temporel), fusion de
classements, reranking cross-encoder, **extraction de faits**, **consolidation de croyances**,
**modèles mentaux**, **directives**, et raisonnement agentique.

**Ambition cible :** doter Axiom d'une **mémoire cognitive** où les PNJ et le monde *se souviennent,
révisent leurs croyances et apprennent de l'expérience* — sans casser le côté offline/léger/rollback.

### 1.1 Cadrage validé avec l'utilisateur (2026-06-17)
- **Q1 périmètre** → « le plus clean et complet possible, sois ambitieux ». ⇒ on conçoit la cible
  complète (recherche + faits + croyances), pas un MVP.
- **Q2 dépendances** → « oui, on peut en ajouter, pas dérangeant ».
- **Q3 croyances/consolidation** → « si ça ajoute des trucs cool, c'est prioritaire ». ⇒ Phase 3 est
  un objectif de premier plan (explication pédagogique de ce que c'est en §4).
- **Q4 budget LLM** → « deux modes de préférence, un avec et un sans, togglables ». ⇒ §6.

L'utilisateur **ne code pas** (pilote par IA) : toute décision de dépendance/archi doit lui être
expliquée en langage accessible avec trade-offs avant d'être tranchée.

---

## 2. Contraintes non négociables d'Axiom (cahier des charges)

Tout ce qu'on extrait doit respecter ces invariants. **Chaque entrée du catalogue (§5) les re-teste.**

| Invariant | Détail | Pourquoi |
|---|---|---|
| **Rollback par `turn_id`** | Pouvoir « supprimer/annuler tout ce qui a `turn_id > N` », **y compris les croyances dérivées**. | Cœur du Pilier 2 (checkpoint/rewind/multivers). `VectorMemory.rollback` (`axiom/memory.py:260`). Solution croyances : §8. |
| **Jeu jouable hors-ligne** | La boucle de jeu de base doit tourner sans réseau (Mode Léger). Embeddings locaux (MiniLM). | Machine sans IPv6 fiable vers Google (`IPv4FirstTransport`). Le Mode Vivant peut, lui, exiger le réseau (LLM cloud) — c'est un choix utilisateur assumé. |
| **Pas de LLM local** | Machine AMD sans CUDA. LLM = cloud (Gemini/Fireworks) via `LLMBackend`. | Tout appel LLM coûte et passe par le réseau → réservé au Mode Vivant. |
| **Déterminisme des tests** | ~750 tests s'appuient sur une mémoire prévisible. | Le Mode Léger doit rester 100 % déterministe. Le Mode Vivant se teste avec un `LLMBackend` mocké (faits/croyances injectés). |
| **Windows fragile sur torch** | torch crashe sans VC++ Redistributable (TICKET-070) ; dégradation gracieuse obligatoire (`_disabled`). | Toute dépendance native (cross-encoder…) doit garder le fallback no-op. |
| **Moteur léger publié PyPI** | `axiom/` est packagé (`axiomai-engine`). Pas de Postgres, pas de FastAPI. | Le moteur reste `pip install` + import. On garde ChromaDB+SQLite. |

> **Dépendances déjà présentes :** `chromadb` + `sentence-transformers` (`pyproject.toml:36-37`) → torch
> est déjà là. Un **cross-encoder** (`sentence_transformers.CrossEncoder`) n'ajoute donc pas une
> nouvelle classe de dépendance. Avec l'accord « dépendances OK », on peut viser large.

---

## 3. Les deux codebases : emplacements & hygiène licence

| | Chemin | Rôle |
|---|---|---|
| **Axiom (nous)** | `/home/garen/coding/AxiomAI/` | Le moteur cible. Git AGPL-3.0-or-later. |
| **Hindsight (eux)** | `/home/garen/coding/hindsight/` | **Clone de référence, HORS de notre arbre git.** Lecture uniquement. |

**Hygiène licence (projet AGPL + obligation de citation §7(b)) :**
- Hindsight est **MIT** (`/home/garen/coding/hindsight/LICENSE`, © 2025 Vectorize AI, Inc.) → absorbable
  dans un projet AGPL.
- **Ne JAMAIS** copier/commiter le clone dans l'arbre git d'Axiom.
- Code **verbatim substantiel** → conserver l'attribution MIT (en-tête + `NOTICE`). Code **réécrit/adapté**
  (cas normal) → libre ; une mention « algorithme inspiré de Hindsight (MIT) » en commentaire est correcte.

**Où vit le jus algorithmique :**
`/home/garen/coding/hindsight/hindsight-api-slim/hindsight_api/engine/`
(Tous les chemins `engine/...` ci-dessous sont relatifs à ce dossier.) `hindsight-api-slim` = même code
que `hindsight-api` sans modèles ML embarqués → c'est **la source à lire**. Le `hindsight-client`
installé dans notre `.venv` ne contient **que** le SDK HTTP — zéro algo, ignorer.

---

## 4. Comprendre le modèle de connaissance de Hindsight (pédagogique)

C'est *le* concept à saisir, car c'est lui qu'on importe. Hindsight n'a pas « une » mémoire mais une
**hiérarchie à 3 niveaux** + des règles transverses. Du plus brut au plus raffiné :

### 4.1 Les FAITS (raw facts) — la vérité de base
À l'ingestion (`retain`), un LLM lit le texte et en extrait des **faits atomiques** structurés.
Source : `engine/retain/fact_extraction.py`.
- Schéma d'un fait : **who / what / when / where / why** + `fact_type` (`world` = sur le monde,
  `experience`/`assistant` = vécu/dit) + `entities[]` + **relations causales** (`CausalRelation`,
  `FactCausalRelation` : « ce fait découle de tel fait antérieur »).
- → **Synergie Pilier 5 (Temps causal) :** leurs relations causales entre faits sont exactement le
  genre de structure que ton pilier temporel veut. À étudier de près.
- Pour Axiom : un « fait » = une bribe vérifiable tirée du tour (« Kael a juré fidélité à la reine au
  tour 12 »), taguée `turn_id` → **rollback trivial** (c'est atomique et daté).

### 4.2 Les OBSERVATIONS (croyances consolidées) — bottom-up, automatiques
Un job de fond (`engine/consolidation/consolidator.py`) agrège les faits en **observations** =
croyances synthétiques qui **évoluent**. Chaque observation porte :
- `proof_count` (nb de faits qui la soutiennent), `source_memory_ids[]` (les faits sources),
  `history` (JSONB des changements dans le temps).
- Le LLM décide **CREATE / UPDATE / DELETE** selon des règles fines (prompt
  `engine/consolidation/prompts.py`, vraiment riche) : préférer UPDATE pour ne pas créer de doublons,
  une observation = une facette, gérer les **changements d'état** (« a vendu X », « X est mort »),
  cascader (« retirer C du groupe »), **ne jamais calculer** (pas d'arithmétique), préserver l'historique.
- **Dédup** : similarité sémantique au-dessus d'un seuil + **adjudication LLM 1-à-1** (`_dedup_adjudicate`,
  « fusionner ou garder ? »).
- **Mission personnalisable** (`observations_mission`) : *quoi* retenir, configurable **par banque**.
  → Pour Axiom : configurable **par univers et/ou par personnage** (un PNJ rancunier « retient les
  trahisons », un marchand « retient les transactions »). C'est ça, « les trucs cool ».
- C'est ce qui fait qu'un **PNJ se souvient d'une trahison 200 tours plus tard** et révise son opinion.

### 4.3 Les MODÈLES MENTAUX (mental models) — top-down, curés
`engine/reflect/` : des **résumés de plus haute qualité**, soit définis par l'utilisateur (des
« questions épinglées » que le système garde répondues), soit raffinés à la demande. Rafraîchis via
`reflect`. C'est la couche « ce que le personnage *croit savoir* en synthèse ».
- Pour Axiom : pourrait alimenter une **fiche de personnage vivante** ou un **état du monde résumé**
  réinjecté dans le prompt, recomposé périodiquement.

### 4.4 Les DIRECTIVES — règles dures transverses
`engine/directives/` + `reflect/prompts.py::build_directives_section` : des **règles impératives** que
toute réponse doit respecter.
- Pour Axiom : à distinguer de nos **Rules déterministes** (table `Rules`, moteur causal). Les
  directives Hindsight sont des **consignes au LLM** (style, ton, contraintes de persona) — elles
  pourraient nourrir le Basic Prompt / la persona, pas le moteur de règles.

### 4.5 La RECHERCHE (recall) — comment tout ça remonte
Hiérarchie de récupération (`reflect/agent.py`) : **mental_models → observations → recall (faits bruts)**.
La recherche elle-même (`engine/search/`) est hybride : 4 armes (sémantique, lexical/BM25, graphe,
temporel) → **fusion RRF** → **reranking cross-encoder** → **scoring combiné** (récence × proximité
temporelle × proof_count). C'est la partie **sans LLM**, la base du Mode Léger.

**Schéma mental de la cible Axiom :**
```
                 ┌─────────────── MODE VIVANT (LLM, opt-in) ───────────────┐
 texte du tour → │  extraction de FAITS (who/what/when/where/why, causal)   │
 (narratif)      │            ↓ (job de fond, indexé turn_id)               │
                 │  consolidation → OBSERVATIONS (croyances, proof_count,    │
                 │                  source_memory_ids, history) par perso   │
                 │            ↓                                             │
                 │  (option) MODÈLES MENTAUX : fiches perso/monde résumées  │
                 └──────────────────────────────────────────────────────────┘
 requête (tour) →  RECHERCHE hybride + fusion RRF + rerank + scoring   ← MODE LÉGER (toujours actif)
                   (sémantique Chroma + lexical + temporel/turn_id)
                            ↓
                   contexte réinjecté dans le prompt de l'Arbitrator/Héros
```
Le **Mode Léger** = la ligne du bas (recherche). Le **Mode Vivant** = + le bloc du haut (cognition).

---

## 5. État des lieux : la mémoire d'Axiom aujourd'hui (points d'intégration)

Anchors vérifiés le 2026-06-17 — **revérifier par grep avant d'éditer.**

### 5.1 Mémoire vectorielle (`axiom/memory.py`)
- `VectorMemory` : ChromaDB persistant par `save_id`, embeddings `all-MiniLM-L6-v2`, `local_files_only=True`.
- `embed_chunk(save_id, turn_id, text, chunk_type)` — `:155`. Tag `turn_id` sur chaque chunk.
- `query(...)` — `:181`. **Cœur du scoring**, `:230-258` : `final_score = semantic_score × time_weight`
  (récence −1 %/tour, plancher 0,10). **C'est ce que la Phase 1 remplace.**
- `rollback(save_id, target_turn_id)` — `:260`. Supprime les chunks `turn_id > N`. **Invariant.**
- `update_turn_narrative(...)` — `:281`. Dégradation gracieuse via `self._disabled` (`:129`, `:147`).

### 5.2 Usage dans la boucle (`axiom/arbitrator.py`)
- RAG : `self._vector_memory.query(...)` — `:222` (avec `current_turn_id`, `max_turn_id`).
- Embedding du tour : `embed_chunk(...)` — `:565`.
- Lore structuré : `_fetch_relevant_lore(...)` — `:828` (lit `Lore_Book` en **SQL direct**).
- **⚠️ filtre mort résiduel (déjà traité)** : `:229` (idem `session.py:661`)
  `r.get("metadata", {}).get("type") != "lore"` — `query()` ne renvoie jamais de clé `metadata`, donc
  toujours vrai. La **vraie casse** (« Lore Book RAG mort ») a déjà été corrigée par l'audit moteur du
  **2026-06-14** (étape `audit-moteur-2026-06-14`, bug **B1**, lore passé en SQL direct). Il ne reste
  qu'une **expression morte inoffensive** sur les chunks vectoriels, à nettoyer lors du refactor de
  scoring. Pas un bug fonctionnel — vérifier par grep avant d'y toucher.

### 5.3 Autres points
- `axiom/session.py:660` — query RAG côté Héros (Companion).
- `axiom/config.py:137` — `rag_chunk_count: int = 5` (le `k`). C'est là qu'iront les flags de mode.
- `HISTORY_TURN_CAP` (arbitrator) — borne basse `max_turn_id` (ne pas re-remonter l'historique conversationnel).
- `workers/vector_worker.py` — wrappers QThread (init/rollback/embed/update hors thread principal).
  **C'est ici que vivra le job de fond de consolidation** (Mode Vivant), sur le modèle existant.
- `axiom/schema.py` — tables structurées : `Entities` (:33), `Lore_Book` (:110), `Event_Log` (:87),
  `Entity_Stats`, `State_Cache`. **Les nouvelles tables (faits, observations) viendront ici**, en
  réutilisant le pattern migrations existant (`ensure_*` / `CREATE TABLE IF NOT EXISTS`).
- `axiom/arbitrator.py` causal / Pilier 5 (Timeline, événements) — à croiser avec les `CausalRelation`
  de Hindsight (§4.1).

---

## 6. Architecture cible : le toggle DEUX MODES

Validé par l'utilisateur. Une préférence (réglage app + flag config moteur) choisit le mode. Modèle
direct de leurs flags `ENABLE_OBSERVATIONS` / `ENABLE_AUTO_CONSOLIDATION` / `llm_provider="none"`.

| | **Mode Léger** (défaut sûr) | **Mode Vivant** (opt-in) |
|---|---|---|
| Recherche | hybride + fusion RRF + rerank + scoring (Phase 1) | idem |
| Faits structurés | ❌ | ✅ extraits par LLM (job de fond) |
| Croyances (observations) | ❌ | ✅ consolidation, évoluent, par perso |
| Modèles mentaux | ❌ | ✅ (option) |
| LLM appelé par la mémoire | **jamais** | oui (cloud, en tâche de fond) |
| Réseau requis | non | oui |
| Déterminisme | total | testé via LLM mocké |
| Coût | nul | bornable (throttle, cap tokens, opt-out) |
| Rollback | trivial (chunks datés) | via `source_memory_ids` (§8) |

**Implémentation du toggle :**
- Un champ de config moteur (ex. `memory_mode: "lite" | "living"` dans `axiom/config.py`) + réglage GUI
  (onglet Paramètres) + i18n (10 langues, cf. `core/localization.py`).
- En `lite`, les chemins LLM (extraction/consolidation) sont **court-circuités** — exactement comme
  Hindsight avec `llm_provider="none"`. La couche recherche tourne dans les deux modes.
- Le mode est **par save** (cohérence d'une partie) ; changer de mode en cours ne doit pas casser une
  partie (en repassant en `lite`, les croyances existantes restent lisibles mais ne s'enrichissent plus).
- Garder le `_disabled` existant : si torch/embeddings indisponibles, même le Mode Léger dégrade en no-op.

---

## 7. Catalogue d'extraction technique (le cœur du handoff)

Pour chaque technique : **où c'est chez eux**, **ce que ça fait**, **verdict**, **cible Axiom**,
**impact rollback/déterminisme/coût/mode**. Légende : ✅ transférable quasi tel quel · ⚠️ à adapter ·
❌ jeter. Étoiles = priorité.

### COUCHE RECHERCHE (Mode Léger — sans LLM)

**7.1 — Fusion RRF ✅ ★★★** · `engine/search/fusion.py`
`reciprocal_rank_fusion(lists, k=60)` : `score(d)=Σ 1/(k+rank)`. + `interleave_fusion` (round-robin,
rescousse les #1 que RRF noierait — utile pour la dédup) + `cap_per_source` (plafonne chaque arme avant
fusion). ~150 lignes, zéro dépendance, déterministe. → `axiom/retrieval/fusion.py`. Aucun impact rollback.

**7.2 — Recherche hybride sémantique + lexicale ⚠️ ★★★** · `engine/search/retrieval.py`
`retrieve_semantic_bm25_combined`, `ParallelRetrievalResult` (4 armes). Leur BM25 est en **SQL Postgres**
(`pg_trgm`/`tsvector`) → **non transférable tel quel**. Reprendre **l'idée** : ajouter une arme lexicale
à ChromaDB. Options : (a) `rank_bm25` (lib pure Python, légère, offline — **recommandée vu l'accord
dépendances**) ; (b) keyword overlap maison ; (c) sémantique+temporel seulement. Sur-fetch HNSW ×5 puis
trim (bonne pratique à copier). Déterministe, zéro LLM. Rollback OK (filtre `save_id`/`turn_id`).

**7.3 — Reranking cross-encoder + scoring combiné ✅ ★★★** · `engine/search/reranking.py`, `cross_encoder.py`
`apply_combined_scoring` (`:20`) : `combined = CE_norm × recency_boost × temporal_boost × proof_count_boost`,
`recency_boost = 1 + α·(recency − 0.5)` (modulation **autour de 0.5**, pas produit brut ; recency =
décroissance linéaire). **Pépite** : fallback « passthrough reranker » — sans CE,
ils **réamorcent le score depuis le rang RRF** (`1 − 0.9·rank/n`) au lieu de laisser la récence
dominer (`reranking.py:87-98`, branche `is_passthrough_reranker`, + la classe dédiée
`cross_encoder.py:838 RRFPassthroughCrossEncoder`). **C'est la situation d'Axiom si on n'ajoute pas de
CE → à prendre tel quel.** Constantes de calibrage : `reranking.py:15-17` (`_RECENCY_ALPHA=0.2`,
`_TEMPORAL_ALPHA=0.2`, `_PROOF_COUNT_ALPHA=0.1`). Deux niveaux :
(a) sans dépendance, remplacer notre `semantic×time` par la **forme multiplicative modulée** + passthrough ;
(b) avec `sentence_transformers.CrossEncoder` (ex. `ms-marco-MiniLM-L-6-v2`, ~90 Mo, même famille que
Chroma, **optionnel + fallback Windows**). **Transposer « récence en jours » → « récence en `turn_id` »**
(on a `current_turn_id`). Le terme `proof_count_boost` ne sert qu'en Mode Vivant (sinon neutre). Déterministe.

**7.4 — Boosts de stratégie de recall ✅ ★★** · `engine/search/recall_boost.py`
`BOOST_LEVELS` (low/medium/high → `BoostWeights(rrf, additive)`), `boosted_rrf_score` (avant cap,
multiplicatif rank-aware), `additive_strategy_boost` (après rerank, bump plat). → privilégier une arme,
ou chez nous **les chunks du lieu courant / du perso en scène**. Mécanique à deux étages à copier.
Déterministe, zéro LLM. Itération de finition.

**7.5 — Extraction temporelle de requête ⚠️ ★** · `engine/search/temporal_extraction.py`, `query_analyzer.py`
`DateparserQueryAnalyzer` (lib `dateparser`) → fenêtre de dates. Peu pertinent tel quel (Axiom raisonne
en **temps de jeu**, pas en dates réelles). À **transposer** seulement pour « avant l'acte X » via
`turn_id`. Basse priorité.

### COUCHE COGNITIVE (Mode Vivant — LLM, via notre `LLMBackend`)

**7.6 — Extraction de faits ⚠️LLM ★★★** · `engine/retain/fact_extraction.py`, `retain/orchestrator.py`
LLM → faits **who/what/when/where/why** + `fact_type` + `entities[]` + **relations causales**. **Lire
surtout les prompts** (le savoir-faire). Brancher *leurs prompts* sur notre `LLMBackend`. **Synergie
Pilier 5** via `CausalRelation` (§4.1). Stocker chaque fait avec `turn_id` (rollback trivial). Tâche de
**fond**, jamais bloquante pour le tour. Non-déterministe → tests via LLM mocké. Coût LLM (Mode Vivant).

**7.7 — Consolidation / observations (croyances) ⚠️LLM ★★★** · `engine/consolidation/consolidator.py` + `prompts.py`
LA feature « PNJ qui se souviennent et révisent ». CREATE/UPDATE/DELETE, `proof_count`,
`source_memory_ids[]`, `history`, dédup sémantique + adjudication LLM (`_dedup_adjudicate`), **mission
personnalisable par perso/univers** (`observations_mission`). **Lire le prompt en entier** — il encode
des règles non triviales (pas d'arithmétique, cascade d'état, une facette par observation, conservatisme
sur DELETE). Stocker en SQLite (nouvelle table), versionné par tour. **Rollback : voir §8** (mécanisme
`_filter_live_source_memories` déjà chez eux). Job de fond. Non-déterministe (LLM mocké en test). Coût LLM.

**7.8 — Modèles mentaux + reflect hiérarchique ⚠️LLM ★★** · `engine/reflect/agent.py` + `prompts.py`, `reflect/observations.py`
Recherche hiérarchique mental_models → observations → recall ; modèles = résumés curés rafraîchis. Pour
Axiom : **fiche de personnage vivante / état du monde résumé** réinjecté au prompt. L'agent tool-calling
complet est probablement trop lourd ; en reprendre **le principe de hiérarchie** pour structurer notre
`query` (du plus synthétique au plus brut). Coût LLM (refresh périodique, pas chaque tour).

**7.9 — Directives ⚠️ ★** · `engine/directives/`, `reflect/prompts.py::build_directives_section`
Règles impératives au LLM (style/ton/persona). À distinguer de nos `Rules` déterministes. Pourrait
nourrir Basic Prompt / persona. Basse priorité.

### TRANSVERSE

**7.10 — Résolution d'entités ⚠️ ★** · `engine/entity_resolver.py`
spaCy + désambiguïsation. Axiom a déjà une table `Entities` canonique → probablement **inutile** (spaCy
= grosse dépendance). À relier seulement si on veut rattacher des mentions floues à nos entités. Étudier,
probable rejet.

**7.11 — Modèle de données / migrations ✅ (référence)** · `engine/alembic/versions/*`, notamment
`p1k2l3m4n5o6_new_knowledge_architecture.py`
Référence des structures (memory_units, observations, links, `source_memory_ids`, `proof_count`,
`history` JSONB). À **transposer en schéma SQLite** (pas en pgvector). Inspirer nos `CREATE TABLE`.

**7.12 — Abstractions providers LLM ✅ (lecture utile)** · `engine/providers/{gemini,fireworks}_llm.py`, `gemini_cache.py`
Pas à porter (on a `LLMBackend`), mais bons patterns (retry, cache, gestion 429) → peut nourrir nos
robustesses (TICKET-050). Noter le **prompt caching Gemini** (`gemini_cache.py`) : pertinent pour réduire
le coût du Mode Vivant (le prompt système de consolidation est cacheable, cf. `build_consolidation_system_prompt`).

---

## 8. Le problème dur : rollback × croyances dérivées (résolu, à implémenter)

Le rewind d'Axiom supprime les chunks `turn_id > N`. Les **faits** (§4.1) sont atomiques+datés → trivial.
Le risque est sur les **observations** (§4.2), dérivées de plusieurs tours.

**La solution vient de leur code** (`consolidation/consolidator.py:407` `_filter_live_source_memories`
+ les colonnes `source_memory_ids[]` / `proof_count`) :
1. Chaque observation stocke la **liste des `turn_id` (ou fact_ids) sources**.
2. Au rollback au tour N : pour chaque observation, **filtrer les sources encore vivantes** (source dont
   `turn_id ≤ N`).
3. Si **plus aucune** source vivante → **supprimer** l'observation. Sinon → **recalculer** son
   `proof_count` et, si la croyance avait absorbé un tour annulé, **la marquer périmée pour
   re-consolidation** (recalcul paresseux : reconstruire à partir des faits survivants à la demande).
4. La colonne `history` (JSONB) permet, à terme, de *revenir* à un état antérieur de l'observation sans
   tout recalculer (amélioration possible).

**Garde-fou :** aucune consolidation ne doit être livrée en prod sans que `rollback` ait été étendu à
ces tables et **testé** (un test « je crée des croyances sur 20 tours, je rembobine au tour 10, les
croyances reflètent uniquement les tours ≤ 10 »). C'est le critère d'acceptation de la Phase 3.

---

## 9. Plan de marche par phases

> Chaque phase = une **étape de code distincte** (`maintenance/<etape>/`, TODO/CHANGELOG), workflow habituel.

**Phase 0 — Cadrage (cette page).** ✅ Reconnaissance + cible + cadrage utilisateur faits.

**Phase 1 — Couche recherche (Mode Léger, sans LLM). Base de tout.**
1. Refondre le scoring `memory.py:query` : forme multiplicative modulée + récence en `turn_id` +
   fallback passthrough (§7.3) ; nettoyer le filtre mort (§5.2).
2. Arme lexicale (`rank_bm25`) + fusion RRF (§7.1, §7.2).
3. Cross-encoder optionnel + fallback (§7.3b).
4. (option) boosts de stratégie (§7.4).
→ Vérifs : rollback intact, **tests déterministes verts**, gain qualitatif en jeu réel. Zéro régression
de déploiement/coût. **Livrable autonome et utile même si on s'arrête là.**

**Phase 2 — Infra deux modes + extraction de faits (Mode Vivant, étage 1).**
1. Toggle `memory_mode` (config + GUI + i18n) et court-circuit LLM en `lite` (§6).
2. Table `Facts` (SQLite) + extraction LLM en **job de fond** (`workers/`), indexée `turn_id` (§7.6).
3. Étendre `rollback` aux faits. Tests via `LLMBackend` mocké.
4. Brancher l'arme « faits » dans la recherche (le `fact_type` / who-what-where enrichit le rappel).
→ Synergie Pilier 5 à explorer (relations causales).

**Phase 3 — Croyances / consolidation (Mode Vivant, étage 2). L'objectif « cool ».**
1. **D'abord** étendre `rollback` aux observations (§8) + son test d'acceptation.
2. Table `Observations` + consolidateur (job de fond) sur le modèle §7.7, mission par perso/univers.
3. Scoring : activer `proof_count_boost` (§7.3) ; hiérarchie de rappel observations → faits (§7.8).
4. (option) Modèles mentaux : fiche perso/monde résumée réinjectée.
→ Critère d'acceptation : croyances qui évoluent ET rewind correct.

**Phase 4 — Raffinements** : directives/persona (§7.9), extraction temporelle (§7.5), prompt caching
Gemini pour le coût (§7.12), modèles mentaux avancés.

---

## 10. Méthode conseillée pour l'agent qui reprend

1. **Lire d'abord** : `memory/` du repo (règles collab, profil **non-codeur**, style d'exécution) +
   `maintenance/README.md`. Expliquer les choix de dépendances/archi en langage accessible **avant** de
   trancher. **Pas de skills superpowers.** Ne rien commiter sans feu vert ; ne supprimer aucun test sans demander.
2. **Revérifier les ancres** de cette page par grep (les deux repos bougent).
3. **Commencer par la Phase 1, item 1** (scoring) — isolé, mesurable, sans dépendance ni LLM.
4. **Méthode d'extraction** : lire le fichier Hindsight cité → comprendre l'algo/le prompt → le
   **réécrire** adapté à Chroma/SQLite/`turn_id`/`LLMBackend` (jamais copier le SQL Postgres) → tester
   déterministe (LLM mocké en Mode Vivant) → **valider le rollback**.
5. **Préserver les deux modes** à chaque étape : le Mode Léger reste déterministe et offline.
6. **Découvertes hors-scope** → `maintenance/PENDING.md`.

---

## 11. Décisions prises (cadrage 2026-06-17) & questions résiduelles

**Prises :** ambition maximale (recherche + faits + croyances) ; dépendances autorisées ; croyances =
priorité ; **deux modes togglables** (Léger sans LLM / Vivant avec LLM).

**Résiduelles, à confirmer en cours de route avec l'utilisateur (lui expliquer les options) :**
- Lib lexicale : `rank_bm25` (recommandé) vs maison ? Cross-encoder : quel modèle, activé par défaut ou opt-in ?
- Mode par défaut à l'install : **Léger** (sûr, offline) recommandé, Vivant proposé à l'onboarding ?
- Granularité de la « mission » des croyances : par univers, par personnage, ou les deux ?
- Fréquence du job de consolidation : chaque tour, tous les N tours, ou à la demande (coût LLM) ?
- Réutiliser les clés Fireworks/Gemini partagées pour le Mode Vivant, ou exiger la clé perso de l'utilisateur (coût) ?

---

## 12. Table d'ancres précises vers le code exemple

Anchors `fichier:ligne` relevés le 2026-06-17 (commit `55f70e1d`). **Vérifiés par grep ; à re-confirmer
avant de coder** (le repo amont bouge). Tous les chemins Hindsight sont relatifs à
`…/hindsight-api-slim/hindsight_api/engine/`.

### COUCHE RECHERCHE (Mode Léger)
| Quoi lire | Fichier:ligne (Hindsight) | Pour faire quoi chez nous |
|---|---|---|
| `reciprocal_rank_fusion(lists, k=60)` | `search/fusion.py:29` | algo RRF → `axiom/retrieval/fusion.py` |
| `interleave_fusion` (round-robin anti-dédup) | `search/fusion.py:99` | variante de fusion |
| `cap_per_source` (plafond par arme) | `search/fusion.py:8` | éviter qu'une arme écrase les autres |
| `apply_combined_scoring` (formule de score) | `search/reranking.py:20` | **refonte du scoring de `memory.py:query`** |
| constantes `_RECENCY/_TEMPORAL/_PROOF_COUNT_ALPHA` | `search/reranking.py:15-17` | valeurs de calibrage |
| fallback passthrough (`is_passthrough_reranker`) | `search/reranking.py:87-98` | **cas Axiom sans cross-encoder** |
| classe `RRFPassthroughCrossEncoder` | `cross_encoder.py:838` | idem, version « objet » |
| classe `CrossEncoderReranker` | `search/reranking.py:139` | brancher un cross-encoder |
| `create_cross_encoder_from_env` / `LocalSTCrossEncoder` | `cross_encoder.py:1614` / `:126` | charger un CE local (sentence-transformers) |
| `BOOST_LEVELS` + `boosted_rrf_score` + `additive_strategy_boost` | `search/recall_boost.py:68` / `:75` / `:101` | privilégier lieu/perso en scène |
| `retrieve_semantic_bm25_combined` + `ParallelRetrievalResult` | `search/retrieval.py:95` / `:43` | structure de la recherche hybride (l'idée, pas le SQL) |
| sur-fetch HNSW ×5 puis trim | `search/retrieval.py:120-160` (commentaires) | bonne pratique ANN |
| sélection à couverture temporelle | `search/retrieval.py:326` `_select_with_temporal_coverage`, `:375` `retrieve_temporal_combined` | arme temporelle (si transposée en `turn_id`) |
| `extract_temporal_constraint` / `DateparserQueryAnalyzer` | `search/temporal_extraction.py:34` / `query_analyzer.py:82` | extraction temporelle de requête (basse priorité) |

### COUCHE COGNITION (Mode Vivant)
| Quoi lire | Fichier:ligne (Hindsight) | Pour faire quoi chez nous |
|---|---|---|
| schéma de fait `class Fact` / `ExtractedFact` | `retain/fact_extraction.py:125` / `:178` | structure who/what/when/where/why + `fact_type` |
| `class CausalRelation` / `FactCausalRelation` | `retain/fact_extraction.py:151` / `:160` | **relations causales → synergie Pilier 5** |
| variante sans causal `ExtractedFactNoCausal` | `retain/fact_extraction.py:327` | schéma allégé si on n'utilise pas le causal |
| construction du prompt d'extraction | `retain/fact_extraction.py:983` `_build_extraction_prompt_and_schema`, `:1102` `_retain_mission_preamble`, `:1122` `_build_user_message` | **le prompt d'extraction (savoir-faire)** |
| pipeline retain | `retain/orchestrator.py:557` `retain_batch`, `:511` `_extract_and_embed`, `:415` `_insert_facts_and_links` | orchestration faits→embed→links |
| **prompt de consolidation** | `consolidation/prompts.py:20` `_PROCESSING_RULES`, `:85` `_DECISION_GUIDE`, `:93` `_OUTPUT_SECTION`, `:145` `build_batch_consolidation_prompt`, `:10` `_DEFAULT_MISSION` | **le cœur du savoir-faire croyances (à lire en entier)** |
| prompt système cacheable | `consolidation/prompts.py:178` `build_consolidation_system_prompt` | réduire le coût (prompt caching) |
| dédup croyances (seuil + LLM) | `consolidation/consolidator.py:143` `_dedup_adjudicate`, `:98` `_DedupDecision` | éviter les doublons d'observations |
| **rollback des croyances** | `consolidation/consolidator.py:407` `_filter_live_source_memories` | **mécanisme clé du §8** |
| actions de consolidation | `consolidation/consolidator.py:440` `_CreateAction` / `:460` `_UpdateAction` / `:479` `_DeleteAction` | modèle des opérations CREATE/UPDATE/DELETE |
| agrégation des sources | `consolidation/consolidator.py:501` `_SourceAggregation`, `:511` `_aggregate_source_fields` | `proof_count` / `source_memory_ids` |
| reflect (hiérarchie + boucle) | `reflect/agent.py:324` `run_reflect_agent` | principe mental_models→observations→facts |
| directives (règles au LLM) | `reflect/prompts.py:34` `build_directives_section` | persona / Basic Prompt |
| résolution d'entités | `entity_resolver.py:95` `EntityResolver` | probable rejet (spaCy) |

### DONNÉES & INFRA (référence)
| Quoi lire | Fichier:ligne (Hindsight) | Pour faire quoi chez nous |
|---|---|---|
| modèle de données « knowledge » | `alembic/versions/p1k2l3m4n5o6_new_knowledge_architecture.py` | transposer en `CREATE TABLE` SQLite |
| flags de mode | `config.py` (`DEFAULT_ENABLE_OBSERVATIONS:886`, `DEFAULT_ENABLE_AUTO_CONSOLIDATION:887`, `llm_provider="none"`) | **patron du toggle deux modes (§6)** |
| providers LLM (patterns retry/429/cache) | `providers/gemini_llm.py`, `providers/fireworks_llm.py`, `providers/gemini_cache.py` | nourrir nos robustesses (TICKET-050) |
| (hors-scope probable) graphe | `search/graph_retrieval.py`, `search/link_expansion_retrieval.py`, `retain/link_creation.py` | arme graphe — étudier seulement si on veut un graphe de relations |

### CÔTÉ AXIOM (points d'intégration)
| Quoi | Fichier:ligne |
|---|---|
| scoring à refondre | `axiom/memory.py:181` (`query`), spéc. `:230-258` |
| rollback à étendre | `axiom/memory.py:260` |
| embed par tour | `axiom/memory.py:155`, appelé `axiom/arbitrator.py:565` |
| RAG dans la boucle | `axiom/arbitrator.py:222` ; côté Héros `axiom/session.py:660` |
| filtre mort à nettoyer | `axiom/arbitrator.py:229`, `axiom/session.py:661` |
| config (toggle + `rag_chunk_count`) | `axiom/config.py:137` |
| nouvelles tables (Facts/Observations) | `axiom/schema.py` (pattern `Entities:33`, `Lore_Book:110`, `Event_Log:87`) |
| modèle de job de fond | `workers/vector_worker.py` |
| synergie causale (Pilier 5) | `axiom/arbitrator.py` (Timeline/événements) |

---

## 13. Décisions tranchées (2026-06-18) — démarrage du code

Les questions résiduelles du §11 ont été tranchées par l'utilisateur :
- **Arme lexicale = `rank_bm25`** (lib Python pure, offline, légère). Dépendance acceptée.
- **Cross-encoder = optionnel, OFF par défaut.** Le passthrough RRF (§7.3) est la base ; le CE est
  activable par l'utilisateur averti (fallback no-op si torch HS, sûr pour Windows/TICKET-070).
- **Mode mémoire par défaut = Léger** (offline, déterministe, zéro coût). Le **Vivant** est proposé
  à l'onboarding.
- **Démarrage = Phase 1 item 1** (refonte du scoring `memory.py:query`) — isolé, sans dépendance,
  sans LLM. Étape de code : `maintenance/hindsight-phase1-recherche/`.

Restent à trancher en chemin (Phases 2-3) : granularité « mission » des croyances (univers/perso),
fréquence du job de consolidation, clés LLM partagées vs perso.

---

## 14. Idées bonus à étudier (faisabilité → réalisation)

> Idées nées de la lecture de Hindsight, **pas dans le plan initial**. À **vérifier en faisabilité
> d'abord** (comment, à quel coût, sans casser rollback/déterminisme/offline), **puis** à planifier.
> Tant qu'une idée n'est pas vérifiée, elle reste ici (ne pas coder à l'aveugle).

**B-1 — Faits causaux → Timeline du Pilier 5 (synergie forte). ★★★**
Leurs `CausalRelation` / `FactCausalRelation` (§4.1, `retain/fact_extraction.py:151/160`) relient un fait
à ses causes (« Kael trahit » ← « la reine a exécuté son frère »). Idée : qu'un fait extrait (Phase 2)
ne soit pas qu'un souvenir mais **un maillon de chaîne causale alimentant la Timeline causale existante**
(`axiom/arbitrator.py`). *À vérifier* : structure de la Timeline actuelle, où injecter les liens, coût
de stockage. *Gain* : un « pourquoi » traçable du monde, cohérent avec le Pilier 5.

**B-2 — Croyances réinjectées dans le RP des PNJ. ★★★**
Une `Observation` du type « le joueur m'a trahi » (proof_count élevé) **injectée dans le prompt de
dialogue du PNJ concerné** → réactions cohérentes des dizaines de tours plus tard. C'est le vrai
« cool factor » des croyances. *À vérifier* : point d'injection (Companion/Héros `session.py:660`),
budget tokens, filtrage par perso en scène. *Dépend de* Phase 3.

**B-3 — « Mission de croyance » = trait de personnalité jouable. ★★**
Leur `observations_mission` (§4.2) est configurable par banque. Idée : l'exposer **par personnage**
comme un trait (rancunier → retient les trahisons ; cupide → les transactions ; loyal → les services
rendus) éditable dans le Creator Studio. *À vérifier* : où stocker (table `Entities` ? nouveau champ),
UI Studio, i18n. *Gain* : des PNJ qui « se souviennent différemment » selon leur nature.

**B-4 — Prompt caching Gemini pour le coût du Mode Vivant. ★★**
Leur `consolidation/prompts.py:178 build_consolidation_system_prompt` est cacheable (`gemini_cache.py`).
Le prompt-système de consolidation/extraction est stable → le **cacher** réduit fortement le coût du
Mode Vivant. *À vérifier* : notre `LLMBackend`/`GeminiClient` supporte-t-il le context caching ? sinon
coût d'ajout. *Gain* : Mode Vivant beaucoup moins cher en tokens.

**B-5 — Lore Book vectoriel (recoupe TICKET-072). ★**
Le scoring refondu (Phase 1) + arme lexicale s'appliquent aussi au `Lore_Book` : vectoriser les entrées
`chunk_type="lore"` et les ranker par similarité (au lieu du match SQL mots-clés actuel), avec repli
mots-clés. *À vérifier* : déjà ticketé (TICKET-072) — **à fusionner avec ce chantier** plutôt que traité
à part. *Gain* : récupération de lore par sens, pas seulement par mot exact.
