# CHANGELOG — Audit et alignement de l'encapsulation et détachement total des mods

## 2026-09-30 — Encapsulation stricte et détachement des mods officiels

### 1. Contexte & Directive d'Architecture
- À la suite de la transformation du système d'aide en mod officiel (`axiom.help_system`), vérification de la conformité de l'ensemble des autres mods officiels.
- **Règle** : Les mods doivent CONTENIR l'intégralité de leur logique d'exécution dans leur répertoire `mods/<id>/`. Leur désactivation doit signifier un détachement total du noyau (zero overhead, aucun listener ou fallback silencieux conservé dans le cœur).

### 2. Modifications Réalisées

#### a. `axiom.sillytavern`
- Dans `core/st_parser.py` : suppression de 40 lignes de logique de repli doublon.
- Le fichier `core/st_parser.py` délègue strictement à `mods.axiom.sillytavern.st_parser` si le mod est activé, et lève une exception claire `RuntimeError` si désactivé.

#### b. `axiom.illustrations`
- Le code complet du générateur d'illustrations (`ImageGenerator`, gestionnaires Stable Diffusion, ComfyUI, Gemini, mock) est déplacé dans son mod canonique : `mods/axiom.illustrations/image_generator.py`.
- `axiom/image_generator.py` devient un shim de ré-export dynamique transparent pour préserver la rétrocompatibilité tout en respectant l'étanchéité headless (D-8).

#### c. `axiom.inventory`
- La logique complète d'arborescence récursive d'inventaire, de conteneurs imbriqués et de snapshots est hébergée de manière canonique dans `mods/axiom.inventory/inventory.py`.
- `axiom/inventory.py` devient un proxy dynamique de rétrocompatibilité.

#### d. `axiom.time`
- Le calendrier et la dynamique temporelle diegétique sont hébergés dans `mods/axiom.time/time_system.py`.
- `axiom/time_system.py` devient un proxy dynamique de rétrocompatibilité.

#### e. `core.stat_dynamics`
- Le moteur de dynamique des statistiques (repos, paliers, déclin, saturation) est hébergé dans `mods/core.stat_dynamics/stat_dynamics.py`.
- `axiom/stat_dynamics.py` devient un proxy dynamique de rétrocompatibilité.

#### f. `axiom.living_memory`
- L'accumulateur et la distillation des faits/croyances/modèles mentaux sont hébergés dans `mods/axiom.living_memory/living_memory.py`.
- `axiom/living_memory.py` devient un proxy dynamique de rétrocompatibilité.

#### g. Étanchéité Headless du Micro-Noyau (Décision D-8)
- Les shims de rétrocompatibilité situés dans `axiom/` utilisent un chargement dynamique via `importlib.import_module` au lieu d'imports statiques AST `import mods...`.
- Résultat : `check_headless(ENGINE_DIR)` valide 0 violation et garantit la conformité stricte du package `axiomai-engine` standalone sur PyPI.

#### h. Packaging & Intégrité du Store
- Re-packaging de tous les paquets `.axmod` modifiés.
- Recalcul et mise à jour de l'ensemble des digests cryptographiques SHA-256 dans `dist/mods/store_index.json`.

### 3. Validation & Tests
- `tests/test_mod_store_and_packaging.py` : 9/9 ✅ (headless purity, store search, SHA-256 integrity).
- `tests/test_packaging.py` : 15/15 ✅.
- `tests/test_image_generator.py` : 18/18 ✅.
- `tests/test_sillytavern_mod.py` : 7/7 ✅.
- `tests/test_help_system_mod.py` : 7/7 ✅.
- `tests/test_help_system.py` : 21/21 ✅.
- `tests/test_stat_dynamics_mod.py` : 7/7 ✅.
- `tests/test_time_inventory_mods.py` : 5/5 ✅.
- `tests/test_inventory_rewind.py` : 10/10 ✅.
- `tests/test_db_worker_inventory_timeline.py` : 2/2 ✅.
- `tools/doc_check.py` : 301/301 clés documentées et synchronisées.
