# Lot A — Hygiène des tests et CI (corrections 2026-10)

Aucun commit, aucun stage, aucun fichier supprimé. Fichiers modifiés :
`tests/conftest.py`, `tests/test_config.py`, `tests/test_help_system_mod.py`,
`tests/test_sillytavern_mod.py`, `tests/test_providers_illustrations_mods.py`,
`tests/test_ui_mods_and_cli.py`, `tests/test_mods_dialog_ui.py`, `.github/workflows/tests.yml`,
`test.sh`, `main_web.py` (une seule ligne, l.2859).
Fichiers créés : `tests/test_test_isolation.py`, `tests/test_web_server_startup.py`.

## 1. Corrigé

### 0-SYNTHESE « Points urgents » 1, 2-PHASE0 I-5 (partie hermétisme) : isolation de la config
- `tests/conftest.py:130` `isolated_axiom_data_dir` (autouse, même nom qu'avant, donc les tests qui
  la demandent explicitement marchent toujours). Pour **chaque** test, la fixture :
  - pointe `AXIOM_CONFIG_DIR` et `AXIOM_DATA_DIR` vers `tmp_path` ;
  - redirige `Path.home()` vers `tmp_path/home` (le store `~/.cache/AxiomAI/store_cache.json` et
    `staged_mods` du créateur passent par là) ;
  - redirige vers `tmp_path` les chemins **figés à l'import** des modules du projet
    (`paths.CONFIG_DIR/SETTINGS_FILE/GLOBAL_DB_FILE/UNIVERSES_DIR…`, `config.GLOBAL_DB_FILE`,
    `hub_view.UNIVERSES_DIR`, `HubView._LIBRARY_DIR`, `settings_dialog.GLOBAL_DB_FILE`, et les
    **valeurs par défaut de fonctions** comme `install_bundled_universes(library_dir=UNIVERSES_DIR,
    marker_file=CONFIG_DIR/…)`) : sans ça, un test qui retire la variable d'env, ou un code qui
    utilise une constante, retombait sur le vrai dossier (`_redirect_frozen_constants`, l.102) ;
  - fait `paths.reset()` avant et après le test (les fixtures qui faisaient `paths.configure()` sans
    `reset()` — `test_providers_illustrations_mods`, `test_memory_mods`, … — ne fuient plus), et vide
    le cache `axiom.config._CONFIG_CACHE`.
- **Garde-fou** (même fixture, fin de test) : empreinte (mtime, taille) du vrai `~/.config/AxiomAI`
  et du vrai `~/AxiomAI`, et liste des entrées de `mods/` et `dist/mods/` du dépôt, avant/après chaque
  test. Si ça change, le test échoue (« Test non hermétique : il a modifié … »). Coût mesuré
  négligeable (< 10 ms).
  - Il a déjà servi : au premier passage complet il a attrapé
    `test_ui_mods_and_cli.py::test_entrypoints_disabled_mods`, dont `main.main()` écrivait dans le vrai
    `~/AxiomAI/universes` et `~/.config/AxiomAI/installed_bundles.txt` via les valeurs par défaut figées
    de `install_bundled_universes`. Corrigé par la redirection des valeurs par défaut.
- `tests/test_test_isolation.py` (nouveau, 7 tests) : tous les chemins résolus (dynamiques et figés,
  dont `Path.home()`) sont dans `tmp_path` ; ça reste vrai après `delenv` + `paths.reset()` ;
  `save_config` écrit dans le dossier isolé ; l'empreinte du garde-fou détecte une modification, une
  création et l'apparition du dossier ; les valeurs par défaut figées sont redirigées.
- `tests/test_config.py:30` (fixture `config_dir`) et `:136` (`test_creates_directory`) : ils
  patchaient seulement `_CONFIG_FILE`, que `AXIOM_CONFIG_DIR` court-circuite. Ils positionnent
  maintenant aussi `AXIOM_CONFIG_DIR`. Ils passent dans les deux cas (31/31 avec et sans la variable dans
  le shell). Avant la correction, 3 échouaient sous la nouvelle isolation (6 selon la revue avec la variable
  positionnée dans le shell).
- `test_mod_store_and_packaging.py` (install `enable=True`), `test_mods_dialog_ui.py` (toggle) et
  `test_golden_step.py` (`configure(data_dir=…)` sans `config_dir`) n'ont pas eu besoin d'être modifiés :
  l'isolation automatique les couvre (verts, garde-fou muet).

### 4-DOC-ET-RUNTIME B2(b), 3-MODS I9(a) : aucun test ne lit `dist/`
Les `.axmod` et l'index sont générés dans `tmp_path` avec `pack_mod` / `publish_mod_to_store_spec` :
- `test_help_system_mod.py:216` `test_7_store_index_integrity_and_sha256` ;
- `test_sillytavern_mod.py:151` `test_7_store_index_integrity` (ajout de la vérification du sha256) ;
- `test_providers_illustrations_mods.py:75` `test_manifests_and_loading` ;
- `test_ui_mods_and_cli.py:42` `test_manifests_and_loading_ui_mods`.
Grep de tous les autres tests (hors lot C) : plus aucune lecture ni écriture dans `dist/` ou `mods/` du dépôt
(tous les autres `pack_mod` écrivent déjà dans `tmp_path`). Le garde-fou surveille aussi `mods/` et `dist/mods/`.

### 3-MODS I9(b) / B4 : test qui appelait un vrai Ollama
- `test_providers_illustrations_mods.py:143` et `:312` : le test modifiait `cfg.llm_backend` sur
  l'objet renvoyé par `load_config()`. Sans `settings.json`, cet objet est neuf et la modification est
  perdue, donc la `Session` retombait sur le backend par défaut (Ollama `localhost:11434`). Avec un
  `settings.json`, la modification passait par le cache et polluait la config en mémoire. Le choix est
  maintenant enregistré par `save_config` dans la config isolée. Le tour est servi par le faux LLM
  scripté (le test vérifie le texte « determination »).

### 4-DOC-ET-RUNTIME B2(c) : `test_6` bloqué sur le Quick Tour modal
- `tests/conftest.py:177` : nouvelle fixture partagée `no_first_launch`, qui neutralise
  `MainWindow._check_first_launch`. Elle est utilisée par `test_help_system_mod.py:181` (`test_6`) et
  `test_mods_dialog_ui.py:183`, qui avait son propre patch : celui-ci est remplacé par la fixture.
  `test_settings_dialog.py::test_main_window_wallpaper_styling` écrit une config avant de construire la
  fenêtre et ne bloque donc pas. Je ne l'ai pas modifié.

### 4-DOC-ET-RUNTIME B2(a)(d), 0-SYNTHESE point 4 : CI
- `.github/workflows/tests.yml` : 3 lots, chacun dans son propre processus pytest, avec `always()` sur
  les lots 2 et 3. La matrice Python 3.11 / 3.12 est inchangée.
  1. lot principal : `tests/` sans les tests Qt multimédia ;
  2. lot « Qt multimédia » (variable `QT_MULTIMEDIA_TESTS`) : `test_ambiance_manager.py`,
     `test_help_system_mod.py`, `test_mods_dialog_ui.py`, `test_settings_dialog.py` (il construit
     aussi `MainWindow`, et `main_window.py` importe QtMultimedia au niveau du module) et
     `test_sillytavern_mod.py` ;
  3. lot mods : `pytest mods/*/tests -p tests.conftest` (les fixtures d'isolation sont chargées comme
     plugin, parce que `tests/conftest.py` ne s'applique pas hors de `tests/`).
  Une étape ajoute aussi `AXIOM_CONFIG_DIR` / `AXIOM_DATA_DIR` dans `$RUNNER_TEMP`.
- `test.sh` : avec des arguments, le comportement est inchangé. Sans argument, il lance les 3 mêmes lots
  et renvoie 1 si l'un d'eux échoue. Syntaxe vérifiée (`bash -n`). Je ne l'ai pas exécuté, parce qu'il
  réinstalle les dépendances.

### 4-DOC-ET-RUNTIME I3 : `main_web.py`
- `main_web.py:2859` : `from axiom.kernel.loader import bootstrap_all_mods`.
- `tests/test_web_server_startup.py` (nouveau) : lance le vrai `run_server` dans un thread, sur un port
  libre (port 0), avec `webbrowser.open` neutralisé. Le test vérifie qu'aucune erreur de bootstrap n'est
  journalisée, que le registre actif contient le service `web_ui` et le hook `axiom.kernel:execute_step`,
  et que `GET /` répond 200. Ensuite il arrête le serveur. **Je l'ai vérifié en rouge** : en remettant
  temporairement l'ancien import, il échoue avec `['Failed to bootstrap mods at web server startup']`.

## 2. Non corrigé / partiel
- `discover_installed_mods` (`axiom/cli/mods_cmd.py:63`) cherche toujours dans `Path("mods")` et
  `Path("dist/mods")`, relatifs au dossier courant. Les tests qui font un bootstrap chargent donc
  **tout `.axmod` qui traîne dans `dist/mods/` du dépôt**. En ce moment, il y a
  `dist/mods/community.fatigue-0.1.0.axmod` : il n'a pas été créé par mes passages (le garde-fou serait
  tombé), il vient probablement d'un test du créateur lancé par un autre lot. C'est hors de mon
  périmètre (noyau / CLI) : il faudrait un dossier de découverte injectable, ou retirer `dist/mods` de la
  découverte (question 8 de la revue 3-MODS).
- `pack_mod` sans `output_path` écrit toujours dans `dist/mods` (CLI, hors périmètre). Aucun test hors
  lot C ne l'appelle sans `output_path`. Le garde-fou repérera les tests du lot C qui le feraient.
- `tests/test_vector_threading.py` fait `importorskip("PySide6.QtMultimedia")` dans le processus
  principal, après `import torch`. Cet ordre est sans danger et le test était déjà dans le lot principal
  sur `main`. Je l'y ai laissé.
- `test_golden_step.py` : je n'ai rien changé, l'isolation automatique suffit. Le reste de 2-PHASE0 I-5
  (canonicaliseur incomplet, fork au tour 8, test d'époque vide de sens) n'est pas dans ce lot.

## 3. Résultats des tests
Validation complète **exactement par lots CI**, avec `HOME` temporaire (sans aucun `settings.json`),
`AXIOM_CONFIG_DIR` / `AXIOM_DATA_DIR` temporaires et `QT_QPA_PLATFORM=offscreen`. `HF_HOME` pointait sur le
cache réel du modèle d'embedding, l'équivalent du cache CI. Script :
`/tmp/claude-1000/axiom-fix/run_ci.sh`.

| Lot | Commande | Résultat |
|---|---|---|
| 1 principal | `pytest tests/ --ignore=<5 fichiers Qt>` | **1139 passés, 3 échoués** |
| 2 Qt multimédia | `pytest <5 fichiers Qt>` | **45 passés**, rc=0, pas de segfault ni de blocage |
| 3 mods | `pytest mods/*/tests -p tests.conftest` | **8 passés** |
| **Total** | | **1192 passés, 3 échoués** |

- Les 3 échecs sont tous dans `tests/test_kernel_loader.py` (lot C) :
  `test_cyclic_dependency_raises_explicit_error`, `test_direct_conflict_raises_error` (« DID NOT RAISE »
  pour `CyclicDependencyError` / `ConflictError`) et `test_exclusive_slot_rule` (« DID NOT RAISE
  RegistryError »). Ils viennent des modifications en cours de `axiom/kernel/resolver.py` et
  `registry.py` par un lot parallèle (le chargeur ne désactive plus tout sur un conflit). Je les signale
  sans les corriger.
- Au premier passage, le garde-fou avait fait échouer `test_entrypoints_disabled_mods` (écriture réelle,
  voir plus haut). Après correction, aucun test n'a modifié le vrai dossier de config ou de données.
  Dans le `HOME` temporaire, après la suite, il ne reste que `.config/pulse` et `.cache/mesa_shader_cache`
  (Qt/son), aucun `AxiomAI`. Le `settings.json` réel du propriétaire n'a pas bougé (mtime
  `2026-10-03 00:12:24`, celle de la pollution constatée par la revue).
- Lancés aussi un par un, avec config isolée : `test_test_isolation` 7/7, `test_config` 31/31 (avec et
  sans `AXIOM_CONFIG_DIR` dans le shell), `test_session`, `test_providers_illustrations_mods` 5/5,
  `test_ui_mods_and_cli` 8/8, `test_golden_step` 5/5, `test_mod_store_and_packaging` 9/9,
  `test_help_system_mod` 7/7, `test_sillytavern_mod` 7/7, `test_mods_dialog_ui` 5/5,
  `test_web_server_startup` 1/1.

## 4. Suppressions proposées, hors périmètre, questions
- **Suppression proposée** : `dist/mods/community.fatigue-0.1.0.axmod`, un artefact de test dans un
  dossier de découverte (non versionné). Je ne l'ai pas supprimé.
- **Hors périmètre, à faire par le lot noyau / CLI** : rendre injectable le dossier de découverte de
  `discover_installed_mods`, et faire que `pack_mod` n'écrive plus par défaut dans `dist/mods` en test.
  Accessoirement : remplacer les constantes figées (`from axiom.paths import CONFIG_DIR, UNIVERSES_DIR`
  dans `core/bundled_universes.py`, `hub_view.py`, `main_window.py`, `runtime_check.py`, les
  `GLOBAL_DB_FILE` de `settings_dialog.py` / `setup_view.py`, `main_web.ASSETS_BASE_DIR`) par les
  getters de `axiom.paths`. La fixture les redirige, mais ce sont de vrais bugs d'injection de chemins
  pour un moteur embarqué.
- **Suggestion** : un `conftest.py` à la racine du dépôt, qui importerait celui de `tests/`, éviterait le
  `-p tests.conftest` quand quelqu'un lance `pytest mods/x/tests` à la main. Je ne l'ai pas créé, il est
  hors de mon périmètre.
- **Pour le propriétaire** : votre `~/.config/AxiomAI/settings.json` contient encore la pollution
  d'avant (`mod_settings` : `community.herbalism`, `community.lockpicking`, `community.testpack`).
  Vérifiez aussi vos réglages backend et vos clés. Je n'y ai pas touché.
