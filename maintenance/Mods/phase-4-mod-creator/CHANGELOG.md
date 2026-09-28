# CHANGELOG — Phase 4 : Outillage de création & Créateur de mods par LLM

## [Phase 4] - 2026-09-27

### Ajouts

- **Générateur d'Échafaudage (`axiom/kernel/scaffold.py`)** :
  - `scaffold_mod(mod_id, mod_type='hook', target_dir=None, author=..., description=...)` :
    - Génère l'arborescence complète normalisée pour un mod Axiom AI.
    - Trois archétypes disponibles : `hook` (abonnements aux événements de tour), `slot` (fourniture et contribution à des slots), `data` (persistance et tables de stockage).
    - Validation stricte de l'identifiant namespacé (`author.name`) et SemVer (`0.1.0`).
    - Modèles complets de `mod.toml`, `main.py`, `tests/test_<name>.py` et `locales/en.json`.

- **Moteur de Test et de Validation Structurelle (`axiom/kernel/tester.py`)** :
  - `test_mod(mod_path)` et structure `ModTestResult` :
    - Validation du format du manifeste et de la compatibilité API.
    - Validation de la syntaxe des hooks et slots (`namespace:name`).
    - Règle D4 : Analyse AST du code Python pour détecter les imports d'interfaces graphiques interdits (`PyQt6`, `ui`, `main_web`) si le mod ne déclare pas de dépendance explicite d'UI.
    - Chargement et exécution de `init(ctx)` en bac à sable isolé avec nettoyage immédiat `ctx.cleanup()`.
    - Exécution bornée du runner `pytest` en sous-processus si un dossier `tests/` est présent.
    - Support transparent des dossiers ouverts et des archives empaquetées `.axmod`.

- **Mode Développement à Chaud (`axiom/kernel/dev.py`)** :
  - `watch_mod(mod_dir, interval=1.0)` et `poll_mod_once(...)` :
    - Surveillance incrémentale par mtime des fichiers du mod.
    - Dépilage propre de l'ensemble des hooks, slots et patches via `ctx.cleanup()` (Règle D11).
    - Invalidation des caches d'import et ré-instanciation propre du module avec un `ModContext` neuf.

- **Créateur de Mods par LLM & Bac à Sable de Staging (`axiom/kernel/llm_creator.py`)** :
  - `generate_mod(prompt, llm_backend=None, staged_mods_base_dir=None, ...)` :
    - Assemble un prompt système déclaratif contenant la spécification formelle de `mod.toml`, l'API publique de `ModContext`, l'inventaire des hooks/slots officiels et deux exemples de référence (Règle D2).
    - Staging automatique dans un répertoire temporaire sandbox (`~/.cache/AxiomAI/staged_mods/<mod_id>/`).
    - Calcul de diff textuel unifié (pour chaque fichier créé ou modifié par rapport à l'existant).
    - Exécution automatique de `test_mod` dans le bac à sable de staging (Règles §12 & D14).
    - Aucun fichier n'est copié dans `mods/` ni activé sans confirmation explicite.
  - `apply_generated_mod(staged_dir, target_mods_dir="mods", compile_axmod=True, enable_in_config=True)` :
    - Copie du mod validé vers `mods/<mod_id>`, compilation optionnelle de l'archive `.axmod` et activation dans `AppConfig`.

- **Commandes CLI Étendues (`axiom/cli/mods_cmd.py`)** :
  - `axiom mod new <mod_id> [--type {hook,slot,data}] [--dir <path>]`
  - `axiom mod test <path_to_mod_or_axmod>`
  - `axiom mod dev <mod_dir> [--interval <seconds>]`
  - `axiom mod generate "<instruction>" [--yes]` avec affichage des diffs avec coloration syntaxique ANSI et confirmation interactive utilisateur.

- **API Web (`main_web.py`)** :
  - `GET /api/mods` : Liste des mods installés, versions, statuts et compatibilité.
  - `POST /api/mods/generate` : Déclenche le staging sandbox et retourne le diff et le rapport de tests.
  - `POST /api/mods/apply` : Finalise l'installation, le packaging et l'activation du mod sélectionné.

- **Suite de Tests Dédiée (`tests/test_mod_creator.py`)** :
  - 14 tests couvrant la totalité des scénarios d'échafaudage, de validation, de détection d'imports UI, d'exécution de tests, de hot-reload, de staging LLM, du CLI et de l'API Web.
