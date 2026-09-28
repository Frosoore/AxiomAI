# CHANGELOG — Phase 5 : Store, Dépendances, Licence & Distribution

## [Phase 5] - 2026-09-27

### Ajouts

- **Client de Store Distant (`axiom/kernel/store.py`)** :
  - `StoreModEntry` : Modèle de données pour les paquets `.axmod` distribués (id, version, axiom_api, sha256, download_url, python_requires, dependencies, tags).
  - `calculate_sha256(path)` : Calcul sécurisé par blocs de 64 Ko pour tout fichier ou archive `.axmod`.
  - `fetch_store_index(url_or_path)` : Résolution d'index distant (HTTP/HTTPS) ou fichier local avec validation formelle du schéma.
  - `search_store(query, index, tag)` : Moteur de recherche plein-texte sur id, name, description et filtrage par tags.
  - `install_mod_from_store(mod_id, index, target_mods_dir)` : Téléchargement sécurisé, validation cryptographique stricte du hash SHA-256 avec exception dédiée `ModIntegrityError` en cas d'altération, et extraction atomique du mod dans le répertoire cible.
  - `publish_mod_to_store_spec(archive_path, download_url, tags)` : Générateur automatique de spécification de publication pour le catalogue.

- **Vérification des Dépendances Python Légères (`axiom/kernel/dependencies.py` & `axiom/kernel/loader.py`)** :
  - Extension de `ModManifest` avec le champ `python_requires: list[str]` (lu depuis `[python].requires` dans `mod.toml`).
  - `check_python_requirement(requirement_str)` : Vérification statique sans installateur `pip` lourd (Règle D-7) via `importlib.metadata` et `packaging.specifiers`.
  - `check_mod_python_dependencies(manifest)` : Bilan des dépendances manquantes ou incompatibles.
  - Gestion gracieuse dans `load_mod_from_dir` et `load_mod_from_archive` : émission d'un warning détaillé et désactivation propre du mod si des packages Python sont introuvables.

- **Cadre Juridique et Licence des Mods (`docs/licensing_mods.md` & `NOTICE`)** :
  - Définition explicite de la frontière d'extensibilité au titre de la section 7(b) de la licence GNU Affero General Public License v3.0 (AGPLv3).
  - Clarification que les mods tiers créés via l'API publique (`ModContext`, hooks, slots, tables déclaratives, format `.axmod`) sont des œuvres indépendantes libres de choisir leur propre licence (MIT, Apache 2.0, propriétaire, etc.).
  - Notification que les monkeypatches intrusifs modifiant les entrailles privées du noyau restent soumis aux exigences de réciprocité de l'AGPLv3.

- **Packaging PyPI Headless (`axiomai-engine`) & Version 1.0.0** :
  - Incrément de version officiel à `1.0.0` dans `axiom/__init__.py`.
  - Séparation physique hermétique dans `export_engine.py` (Règle D-8) : exclusion des mods (`mods/`), des interfaces graphiques (`ui/`, `web/`, `main_web.py`), des workers et des univers.
  - Extension des règles de contrôle anti-pollution headless (`_FORBIDDEN_IMPORT_RE`) pour interdire toute référence à `mods` et `web`.

- **Commandes CLI Étendues (`axiom/cli/mods_cmd.py`)** :
  - `axiom mods search [query] [--tag <tag>] [--index <url>]` : Recherche dans le catalogue du store.
  - `axiom mods install <mod_id> [--index <url>] [--dir <path>]` : Installation sécurisée d'un mod avec vérification SHA-256.
  - `axiom mods update [--index <url>]` : Mise à jour incrémentale des mods installés.

- **Endpoints API Web (`main_web.py`)** :
  - `GET /api/store/search` : Recherche dans le catalogue du store distant.
  - `POST /api/store/install` : Téléchargement et installation sécurisée via l'interface web.

- **Catalogue Officiel Initial (`dist/mods/store_index.json`)** :
  - Indexation de l'ensemble des 16 archives `.axmod` officielles et communautaires avec leurs condensats SHA-256 authentiques.

- **Suite de Tests Dédiée (`tests/test_mod_store_and_packaging.py`)** :
  - 9 tests complets validant la recherche, le téléchargement, la vérification SHA-256, le rejet sur altération, les dépendances Python, l'export PyPI headless, le CLI et l'API Web.
