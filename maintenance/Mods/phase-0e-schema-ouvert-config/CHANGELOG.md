# CHANGELOG — Phase 0e : Schéma ouvert & Configuration extensible

## 2026-09-27
- Initialisation de la phase 0e.
- Assouplissement du schéma `Saves` dans `axiom/schema.py` : suppression de la contrainte SQL `CHECK` sur `difficulty` pour supporter les modes de jeu extensibles apportés par les mods.
- Création de la table `Mod_Schema_Versions` dans `axiom/schema.py` (`_DDL_MOD_SCHEMA_VERSIONS`) et enregistrement dans `_ALL_DDL`, `EXPECTED_TABLES` et `storage_registry.py`.
- Implémentation de `apply_mod_migrations(db_path, mod_id, target_version, migrations)` pour exécuter les migrations séquentielles et transactionnelles de mods avec horodatage ISO.
- Ajout de `mod_settings: dict[str, dict[str, Any]]` dans `AppConfig` (`axiom/config.py`), garantissant la préservation intégrale des configurations de mods dans `settings.json` (avec alias rétrocompatible `mods`).
- Ajout de tests unitaires dédiés dans `tests/test_schema.py` (`TestModMigrations`) et `tests/test_config.py` (`test_mod_settings_round_trip_and_preservation`, `test_legacy_mods_alias_mapped_to_mod_settings`).
- Validation réussie du harnais `tests/test_golden_step.py`.
