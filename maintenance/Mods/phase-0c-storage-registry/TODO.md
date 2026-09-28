# TODO — Phase 0c : Registre unique de données de save & Éradication des listes manuelles

- [x] Créer le module `axiom/storage_registry.py`
  - [x] Définir l'énumération `StoragePolicy` (`EVENTS`, `STEP_KEYED`, `VERSIONED_KV`, `CUSTOM`)
  - [x] Définir la dataclass `TableStorageSpec`
  - [x] Déclarer le registre canonique `CORE_STORAGE_REGISTRY`
  - [x] Implémenter les fonctions utilitaires (`get_runtime_tables`, `get_definition_tables`, `execute_rewind`, `execute_fork`, etc.)
- [x] Unifier le Rewind dans `axiom/checkpoint.py`
  - [x] Remplacer les suppressions SQL en dur par l'appel unifié `execute_rewind`
  - [x] Supprimer les `DELETE` éparpillés
- [x] Unifier le Fork dans `axiom/saves.py`
  - [x] Remplacer les copies manuelles par l'appel unifié `execute_fork`
- [x] Purger les listes manuelles dans `axiom/savestore.py` et `axiom/package.py`
  - [x] Remplacer `_RUNTIME_TABLES` dans `axiom/package.py` par `get_runtime_tables()`
  - [x] Dériver `_DEFINITION_COPY` et `_RUNTIME_COPY` dans `axiom/savestore.py` depuis `get_definition_copy_specs()` et `get_runtime_copy_specs()`
- [x] Valider avec `tests/test_golden_step.py`, `tests/test_engine_headless.py`, `tests/test_web_server.py`, `tests/test_saves_editing.py`, `tests/test_savestore.py`
