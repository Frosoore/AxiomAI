# CHANGELOG — Phase 2 : Extraction de axiom.rag et axiom.living_memory

## Date : 2026-09-27

### Nouveautés
- **Mod officiel `axiom.rag`** (`mods/axiom.rag/`) :
  - Manifeste déclaratif `mod.toml` avec déclaration de stockage personnalisé `[storage] vector_store = { policy = "custom" }`.
  - Service noyau `"rag"` fournissant les méthodes `query`, `embed_chunk`, `rollback` et `get_vector_memory`.
  - Contribution au slot de prompt `axiom.turn:prompt_sections` pour injecter dynamiquement les fragments de mémoire sémantique pertinents.
  - Hook `axiom.step:after_step` enregistrant un callback dans `ctx.write_batch.post_commit_callbacks` pour vectoriser la prose narrative générée post-commit.
  - Enregistrement du rollback custom auprès de `axiom.storage_registry.register_custom_storage`.
  - Archive binaire distribuée `dist/mods/axiom.rag.axmod`.

- **Mod officiel `axiom.living_memory`** (`mods/axiom.living_memory/`) :
  - Manifeste déclaratif `mod.toml` avec déclaration de persistance `[storage]` pour `facts`, `observations`, et `mental_models`.
  - Service noyau `"living_memory"` fournissant `get_facts`, `get_observations`, `get_models`, `extract_now`, `reset` et `record_turn`.
  - Contribution au slot `axiom.turn:prompt_sections` injectant les faits récents et les profils des entités présentes sur scène.
  - Hook `axiom.step:after_step` déclenchant l'accumulation asynchrone post-commit, protégée par l'époque de session (`epoch_checker`).
  - Archive binaire distribuée `dist/mods/axiom.living_memory.axmod`.

- **Découplage architectural & Dégradation gracieuse** :
  - `axiom/session.py` : Suppression des imports statiques `VectorMemory` et `LivingMemoryAccumulator`. Résolution dynamique des services `"rag"` et `"living_memory"` avec dégradation gracieuse complète si absents (`{"disabled": True}`).
  - `axiom/arbitrator.py` : Découplage de `_vector_memory`, requêtes RAG et indexation post-commit déléguées aux hooks et services du registre de mods quand présent.
  - `main_web.py` : Endpoints `/api/session/memory*` délégant au service `"living_memory"`, renvoyant `{"disabled": True}` sans crash serveur si le mod est désactivé.
  - `axiom/storage_registry.py` : Ajout des fonctions d'extension dynamique `register_table_storage` et `register_custom_storage`.

### Tests & Validation
- Ajout de `tests/test_memory_mods.py` (5 tests d'intégration complets) :
  - `test_manifests_and_loading` : validation des manifestes, chargement par dossier et archive `.axmod`.
  - `test_rag_service_and_storage_rollback` : indexation, requêtes et rollback chirurgical.
  - `test_living_memory_service_and_epoch_guard` : requêtes de service et annulation en cas de décalage d'époque.
  - `test_independent_deactivation` : respect strict de la Règle D11 (réversibilité et indépendance des deux mods).
  - `test_full_turn_with_all_mods` : intégration conjointe des 7 mods officiels (`world`, `turn`, `stat_dynamics`, `time`, `inventory`, `rag`, `living_memory`).
- 41/41 tests passants sur l'ensemble des suites du projet.
