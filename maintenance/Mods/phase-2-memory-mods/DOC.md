# DOC — Phase 2 : Sous-système Cognitif & Mémoire (axiom.rag & axiom.living_memory)

## 1. Contexte & Découpage

Le sous-système de mémoire du moteur Axiom AI a été scindé en deux mods officiels autonomes :
- **`axiom.rag`** : Mémoire sémantique / vectorielle via ChromaDB et embeddings hors-ligne (sentence-transformers).
- **`axiom.living_memory`** : Mémoire vivante et symbolique (distillation des faits, croyances et modèles mentaux).

Ce découplage permet d'utiliser l'un, l'autre, les deux ou aucun (remplacement par un mod tiers, ex: RAG distant, base graphe, etc.), respectant les règles **D1** (noyau minimal), **D2** (pas de privilèges), **D7** (rewind unifié) et **D11** (réversibilité totale).

---

## 2. Mod `axiom.rag`

### Manifeste (`mods/axiom.rag/mod.toml`)
- **ID** : `axiom.rag` (v1.0.0, API 1)
- **Dépendances** : `axiom.turn >= 1.0.0`
- **Hooks** : `axiom.step:after_step`
- **Slots** : contribue à `axiom.turn:prompt_sections` (priorité 20, position `system`)
- **Storage** : `vector_store = { policy = "custom" }`

### Fonctionnement
- **Service `"rag"`** : `query`, `embed_chunk`, `rollback`, `get_vector_memory`.
- **Injection Prompt** : Lors de la génération du tour, injecte les souvenirs vectoriels pertinents sous l'en-tête `RELEVANT MEMORIES (RAG)`.
- **Indexation Post-Commit** : Le hook `after_step` enregistre un callback dans `ctx.write_batch.post_commit_callbacks` pour indexer la prose narrative uniquement après le commit réussi de la transaction SQLite.
- **Rollback** : Enregistre son callback custom auprès de `axiom.storage_registry.register_custom_storage`, garantissant le rollback chirurgical lors d'un rewind de checkpoint.

---

## 3. Mod `axiom.living_memory`

### Manifeste (`mods/axiom.living_memory/mod.toml`)
- **ID** : `axiom.living_memory` (v1.0.0, API 1)
- **Dépendances** : `axiom.world >= 1.0.0`, `axiom.turn >= 1.0.0`
- **Hooks** : `axiom.step:after_step`
- **Slots** : contribue à `axiom.turn:prompt_sections` (priorité 45, depth 7)
- **Storage** : `facts`, `observations`, `mental_models` (politique `step_keyed_table`)

### Fonctionnement
- **Service `"living_memory"`** : `get_facts`, `get_observations`, `get_models`, `extract_now`, `reset`, `record_turn`.
- **Injection Prompt** : Injecte les 5 faits les plus récents et les profils mentaux des entités sur scène sous `LIVING MEMORY (Recent Facts & Entity Models)`.
- **Garde d'Époque (`epoch_checker`)** : L'accumulation asynchrone vérifie que l'époque de session n'a pas été incrémentée (via un rewind, load ou fork). Si l'époque a changé, l'écriture est rejetée silencieusement afin de prévenir toute corruption temporelle.

---

## 4. Intégration & Dégradation Gracieuse

- En l'absence des mods :
  - `Session.get_memory_snapshot()` retourne `{ "disabled": true, "turn_id": N, "facts": [], "beliefs": [], "mental_models": [] }`.
  - `Session.run_living_memory_extract_now()` retourne `{ "status": "disabled", "disabled": true, "facts_stored": 0, ... }`.
  - Les endpoints Web `/api/session/memory*` répondent sans planter le serveur.
  - Le tour de jeu s'exécute normalement sans RAG ni accumulation de faits.
