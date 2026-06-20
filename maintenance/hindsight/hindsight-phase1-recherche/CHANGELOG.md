# CHANGELOG — Phase 1 (couche recherche)

## 2026-06-18 — Item 1 : refonte du scoring ✅
- Création de l'étape (DOC/TODO/CHANGELOG).
- `axiom/memory.py` : constantes de calibrage `_RECENCY_ALPHA` (0,2), `_RECENCY_TURN_HORIZON` (100),
  `_RECENCY_FLOOR` (0,1). Scoring de `query()` refondu : `final_score = semantic × recency_boost` avec
  `recency_boost = 1 + α·(recency − 0,5)` (modulation ±10 %), récence en **âge de tours** (plus en
  « 1 %/tour qui écrase »), neutre (0,5 → boost 1,0) pour lore / turn 0 / pas de `current_turn_id`.
  → un souvenir ancien mais très pertinent n'est plus rabaissé à 10 % de son score.
- Filtre lore mort **rendu correct** (intention d'origine) : `r.get("metadata", {}).get("type")` →
  `r.get("chunk_type")` dans `arbitrator.py:229` et `session.py:661`. Aucun chunk `lore` n'est
  vectorisé aujourd'hui (équivalent fonctionnel maintenant), mais robuste si on vectorise le lore
  plus tard (B-5 / TICKET-072).
- Tests : +2 dans `test_vector_memory.py` (présence du `score` ; **non-écrasement** d'un chunk ancien
  pertinent : ratio old/recent ≥ 0,9/1,1). Suites vertes : `test_vector_memory` 28 ✅ ;
  arbitrator/session/threading/ticket_fixes 69 ✅.
- Note : le **fallback passthrough** (réamorçage depuis le rang RRF) n'a de sens qu'avec plusieurs armes
  fusionnées → reporté à l'item 2 (RRF). En item 1, la base de score reste le sémantique (informatif).

## 2026-06-18 — Item 2 : arme lexicale BM25 + fusion RRF ✅
- Dépendance **`rank-bm25>=0.2.2`** ajoutée (`pyproject.toml`, `requirements.txt`) et installée.
- Nouveau package **`axiom/retrieval/`** :
  - `fusion.py` : `reciprocal_rank_fusion(ranked_lists, k=60)` (fusion de listes d'ids par rang,
    `score = Σ 1/(k+rang)`, tie-break déterministe par 1ʳᵉ apparition) + `cap_per_source`.
  - `lexical.py` : arme **BM25** (`rank_by_bm25`) + `tokenize` (Unicode, minuscule, garde accents/
    non-latin pour les 10 langues) + `is_available()` (dégradation gracieuse si `rank_bm25` absent).
- `axiom/memory.py::query` refondu en **recherche hybride 2 armes** : sémantique (Chroma ANN) +
  lexicale (BM25 sur le corpus de la save, filtré `max_turn_id`). Fusion RRF → **base = score RRF
  normalisé** (lisse : un doc trouvé par les 2 armes dépasse un doc trouvé par 1 seule ; les échelles
  per-arme incomparables ne fuient pas) × `recency_boost`. **Repli 1 arme** (si `rank_bm25` indispo) :
  on garde la base sémantique lisse de l'item 1. Over-fetch ×3 (plancher 20) avant trim.
- Pourquoi le **score RRF normalisé** plutôt que le « passthrough depuis le rang » de Hindsight : leur
  passthrough (rang→[0,1] linéaire) crée un écart 10× entre deux docs de pertinence identique quand il
  y a peu de candidats — dégénéré chez nous. Le score RRF normalisé reste lisse. (Le vrai cross-encoder
  remplacera cette base à l'item 3.)
- Tests : **`tests/test_retrieval_fusion.py`** (RRF formule/tie-break/2-armes, cap, BM25 nom exact en
  tête, tokenize, dégradation). `test_vector_memory.py` ajusté (seuil de non-écrasement robuste).
  **Suite : 807 ✅** (hors `test_ambiance_manager`, segfault Qt préexistant TICKET-067).

## 2026-06-18 — Item 3 : cross-encoder optionnel (OFF par défaut) ✅
- `axiom/retrieval/reranker.py` : **`CrossEncoderReranker`** — wrapper paresseux autour de
  `sentence_transformers.CrossEncoder` (défaut `cross-encoder/ms-marco-MiniLM-L-6-v2`). Lit la paire
  (requête, document) **conjointement** → signal de pertinence le plus précis, **re-tri final** après
  fusion. Normalisation : sigmoïde stable des logits (passthrough si déjà [0,1]), NaN→0.
  **Dégradation gracieuse** : import torch/ST gardé, repli offline `local_files_only=True` puis
  téléchargement unique, `_disabled` → no-op (jamais de crash, Windows/TICKET-070 OK). Modèle
  **injectable** (`model=`) pour tests déterministes hors-ligne.
- `axiom/memory.py` : `VectorMemory(persist_dir, reranker=None)` ; dans `query()`, si un reranker est
  présent, ses scores **remplacent la base** (RRF/sémantique) puis la modulation de récence s'applique
  par-dessus (design Hindsight : CE = signal primaire, récence module). `None` → base inchangée.
- `axiom/config.py` : flag **`memory_reranker_enabled: bool = False`** (OFF par défaut — modèle ~90 Mo
  + runtime natif fragile). Exposition GUI prévue dans le panneau « mémoire » de la Phase 2.
- `axiom/session.py` : construit un `CrossEncoderReranker` **seulement si** `memory_reranker_enabled`
  (try/except : un échec de config ne casse jamais la session ; le worker d'écriture n'a pas de reranker).
- Tests : `test_retrieval_fusion.py` (+sigmoïde, modèle injecté en [0,1], NaN, dégradation, docs vides) +
  `test_vector_memory.py` (le reranker injecté **domine l'ordre** : le chunk « relic » remonte malgré la
  récence). **Suite : 813 ✅.**
- Reste **item 4 (option)** : boosts de stratégie (lieu courant / perso en scène) — finition, non bloquant.

## 2026-06-18 — Item 4 : boost de focus (scène courante) ✅
- Transposition du **`additive_strategy_boost`** de Hindsight (`search/recall_boost.py`, niveau
  « medium » = 0,2). Chez eux il privilégie une *arme* de recherche ; chez nous le signal utile est le
  **contenu** → on booste les souvenirs qui mentionnent la **scène courante**.
- `axiom/memory.py::query(..., focus_terms=None)` : chaque terme est tokenisé ; un chunk **matche** si
  **tous** les tokens du terme y figurent (« Black Keep » exige *black* ET *keep* ; un nom seul matche).
  Match → `score += _FOCUS_BOOST` (0,2) — bump additif plat (la base est en ~[0,1], donc un souvenir en
  scène remonte sans écraser une pertinence directe forte). Sans `focus_terms` → no-op.
- `axiom/arbitrator.py` : passe le **lieu du joueur** (`all_stats[player]["Location"]`, déjà chargé
  avant la requête → zéro lecture/réordonnancement en plus). Les **noms des persos en scène** exigeraient
  la table id→nom construite plus loin dans la méthode → **laissé en suivi** (cf. PENDING ci-dessous)
  pour ne pas réordonner le hot path.
- Tests : `test_vector_memory.py` (le chunk mentionnant le lieu remonte ; le terme multi-mots exige tous
  ses tokens). **Suite : 815 ✅.**

### Phase 1 terminée (Mode Léger / couche recherche)
Items 1→4 livrés. La recherche mémoire est désormais **hybride** (sémantique + lexicale BM25, fusion RRF,
récence modulée en `turn_id`, cross-encoder optionnel, boost de scène), **100 % offline et déterministe**
par défaut, rollback intact. Prochain gros morceau : **Phase 2** (toggle deux modes + extraction de faits).
</content>
