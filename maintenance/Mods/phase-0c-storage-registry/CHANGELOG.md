# CHANGELOG — Phase 0c : Registre unique de données de save & Éradication des listes manuelles

## 2026-09-26
- **Registre de persistance canonique (`axiom/storage_registry.py`)** :
  - Définition de `StoragePolicy` (`EVENTS`, `STEP_KEYED`, `VERSIONED_KV`, `CUSTOM`) et de `TableStorageSpec`.
  - Déclaration centralisée de toutes les tables univers et runtime dans `CORE_STORAGE_REGISTRY`.
  - Implémentation des helpers déclaratifs : `get_definition_tables()`, `get_runtime_tables()`, `get_definition_copy_specs()`, `get_runtime_copy_specs()`, `execute_rewind()`, et `execute_fork()`.
- **Rewind unifié (`axiom/checkpoint.py`)** :
  - Remplacement de toutes les requêtes `DELETE` manuelles et des appels disparates par `execute_rewind(conn, save_id, target_turn_id)`.
- **Fork unifié (`axiom/saves.py`)** :
  - Remplacement des requêtes manuelles de copie de tables par `execute_fork(conn, save_id, new_id, turn_id)`.
- **Éradication des listes codées en dur (`axiom/package.py`, `axiom/savestore.py`)** :
  - Remplacement de `_RUNTIME_TABLES` dans `package.py` par l'appel à `get_runtime_tables()`, éliminant le bug historique TICKET-089.
  - Dérivation de `_DEFINITION_COPY` et `_RUNTIME_COPY` dans `savestore.py` à partir des specs du registre de stockage.
- **Validation** :
  - 100 % passants sur `test_golden_step.py`, `test_engine_headless.py`, `test_web_server.py`, `test_savestore.py`, `test_saves_editing.py`, `test_packaging.py`.
