# TODO — Phase 0e : Schéma ouvert & Configuration extensible

- [x] Assouplir la table `Saves` dans `axiom/schema.py`
  - [x] Supprimer la contrainte `CHECK(difficulty IN (...))` pour autoriser les modes custom / mods
  - [x] Mettre à jour `migrate_saves_difficulty_constraint` pour migrer les bases existantes vers le schéma sans contrainte
- [x] Créer la table `Mod_Schema_Versions` dans `axiom/schema.py`
  - [x] Déclarer `_DDL_MOD_SCHEMA_VERSIONS`
  - [x] Intégrer la création de la table dans `init_db` / `migrate_schema`
  - [x] Ajouter à `storage_registry.py` (`CORE_STORAGE_REGISTRY`)
- [x] Créer l'exécuteur de migrations générique `apply_mod_migrations` dans `axiom/schema.py`
  - [x] Exécution séquentielle et transactionnelle de version $N$ vers $N+1$
  - [x] Enregistrement automatique de la version installée et de l'horodatage ISO
- [x] Rendre la configuration extensible dans `axiom/config.py`
  - [x] Ajouter `mod_settings: dict[str, dict[str, Any]] = field(default_factory=dict)` à `AppConfig`
  - [x] Préserver `mod_settings` (et alias `mods`) lors du chargement et de la sauvegarde dans `settings.json`
- [x] Tests unitaires et validation de non-régression
