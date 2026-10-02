# Lot C — le noyau : rapport de corrections (2026-10-03)

Périmètre touché : `axiom/kernel/*` (dont 2 nouveaux fichiers : `api.py`, `importer.py`),
`axiom/cli/mods_cmd.py`, `axiom/cli/test.py`, `mods/__init__.py`, `axiom/paths.py` (ajout de
`get_mods_dir()` seulement), tests `tests/test_kernel_loader.py`, `tests/test_mod_creator.py`
(adaptés) et 4 nouveaux fichiers `tests/test_kernel_*.py`. Rien n'a été commité, indexé ni supprimé.

## 1. Corrigé

### 1-NOYAU B1 + 3-MODS B5 — un conflit ou un cycle ne vide plus le registre ; statut réel affiché
- `axiom/kernel/resolver.py` (réécrit) : `resolve_load_order` ne lève plus d'exception.
  - Un mod avec un `axiom_api` incompatible, une dépendance absente ou dans une mauvaise version,
    un conflit déclaré ou un cycle est **écarté** avec une raison dans `report.disabled_mods`.
    Ses dépendants sont écartés en cascade, avec la cause complète (ex. « Required dependency
    'axiom.turn' is not loaded: Required dependency 'axiom.world' is not loaded: Disabled by the user. »).
  - Nouveaux champs du rapport : `report.conflicts` et `report.cycles`.
  - Lignes : l.84 (API), l.138 (conflits), l.164 (cycles).
  - `ConflictError` et `CyclicDependencyError` restent exportées, pour ne pas casser les imports.
- `axiom/kernel/loader.py` :
  - `plan_modpack()` (l.221) calcule le statut de chaque mod **depuis les manifestes seuls**,
    sans exécuter de code (D13). Il prend en compte : le choix utilisateur, le mode sans échec, les
    paquets pip, l'API, les dépendances, les conflits et les cycles.
  - `ModStatus` / `ModLoadState` (l.200, l.466) portent ce statut.
  - `bootstrap_all_mods` (l.537) l'enregistre dans `registry.load_state`. Les erreurs d'`init()`
    et les pannes à l'exécution sont fusionnées dans ce même statut.
- `axiom/cli/mods_cmd.py` `run_mod_list` (l.317) : nouvelles colonnes STATUS et ORDER, et une ligne
  `-> état: raison` pour chaque mod non chargé. Plus de « enabled » mensonger.
  - Vérifié à la main : `axiom mods disable axiom.world` puis `mods list` affiche les 10 dépendants
    en « disabled » avec la cause.
- Tests (nouveau fichier `tests/test_kernel_resilience.py`) :
  - `test_conflict_and_cycle_do_not_empty_registry` ;
  - `test_cascade_of_user_disabled_dependency_is_visible_in_mods_list`.
- Tests adaptés dans `tests/test_kernel_loader.py` :
  - `test_cyclic_dependency_sets_cycle_aside_with_reason` ;
  - `test_direct_conflict_sets_loser_aside`.

### 1-NOYAU I4 — `init()` qui échoue, hook qui lève, hooks critiques
- `loader._load_mod_root` (l.281) : en cas d'exception (dans le code du mod ou dans `init()`),
  `ctx.cleanup()` est appelé, les modules sont purgés de `sys.modules`, et `ModLoadError` est levée.
  Le bootstrap marque alors le mod `failed`. Ses dépendants ne sont pas chargés (`failed`, avec la cause).
- `axiom/kernel/registry.py` (réécrit) : un hook ou un maillon de chaîne qui lève entraîne
  `disable_mod()` (l.145). Ce qui se passe alors :
  - `cleanup()` du contexte, purge de tout ce que le mod a enregistré (hooks, emplacements, services) ;
  - le mod passe en `get_faulted_mods()` et les écouteurs sont notifiés ;
  - le loader écarte en cascade les dépendants (`ModLoadState._on_fault`) ;
  - le step continue. Un callback désactivé pendant l'appel même n'est pas exécuté.
- API sans filet :
  - `registry.invoke_hook_unguarded()` (l.223) et `ctx.invoke_hook_unguarded()` ;
  - `registry.declare_critical_hook()`.
- `GenerationCancelled` remonte toujours : depuis un hook, une chaîne, ou un patch (via
  `patcher.add_passthrough_exception`).
- ⚠ **Choix à valider** : `axiom.kernel:execute_step` est déclaré **critique par défaut**
  (`DEFAULT_CRITICAL_HOOKS`, registry.py l.40).
  - Pourquoi : sans cela, la nouvelle politique aurait **désactivé `axiom.turn` à la première erreur
    LLM**.
  - Effet : `session.py` (non modifié) reçoit maintenant la vraie exception (LLM injoignable…) au lieu
    de « Turn pipeline mod returned no result ». C'est l'effet voulu par 1-NOYAU I2 / 3-MODS B4.
  - Le lot suivant peut appeler explicitement `invoke_hook_unguarded` dans `Session` ; le résultat
    est le même.
- Tests :
  - `test_init_failure_cleans_up_and_skips_dependents` ;
  - `test_faulty_hook_disables_its_mod_and_dependents` ;
  - `test_critical_hook_and_unguarded_call_propagate` ;
  - `test_cancellation_is_never_swallowed`.

### 1-NOYAU I5 — version d'API et versions de dépendances
- `axiom/kernel/api.py` (nouveau) :
  - `KERNEL_API = 1` ;
  - `validate_version_spec` / `version_satisfies` : utilisent `packaging.specifiers` (présent dans
    le venv, 26.2), sinon une implémentation minimale (`>= <= == != ~= > <`, listes séparées par
    des virgules).
- `manifest.py` (l.196-212) : une spec invalide, ou une dépendance qui n'est ni une chaîne ni une
  table, donne une `ManifestError`.
- `resolver.py` : un mod dont `axiom_api != KERNEL_API` est écarté ; une version de dépendance non
  satisfaite aussi. `loader._precheck` refuse aussi le chargement direct d'un mod d'une autre API.
- Le store compare désormais `axiom_api` à `KERNEL_API` (il n'est plus codé en dur à 1).
- `mods list` affiche l'API par rapport à `KERNEL_API`.
- Tests :
  - `test_api_and_dependency_versions_are_checked` ;
  - `test_invalid_dependency_spec_is_a_manifest_error` ;
  - `test_version_fallback_without_packaging`.

### 1-NOYAU I6 — ordre utilisateur, exclusifs, conflits visibles
- Ordre utilisateur : `mod_settings["axiom.kernel"]["mod_order"]` (une liste `mod_settings["mod_order"]`
  est aussi acceptée).
  - Fonctions : `loader.get_user_mod_order` / `set_user_mod_order` (l.71-88).
  - Utilisé par le résolveur, sous les contraintes de dépendances et de `before/after`. Il décide
    aussi qui gagne un conflit déclaré.
  - J'ai choisi la section `axiom.kernel` (une table, comme les autres entrées de `mod_settings`)
    pour qu'aucun code qui lit `mod_settings[id]` ne tombe sur une liste. **À valider.**
- Emplacements exclusifs (`registry.add_to_slot`, l.261) : plus de `RegistryError`. Tous les
  candidats sont gardés.
  - `registry.set_mod_order()` (posé par le bootstrap) ordonne les contributions (collecte, chaîne)
    et désigne le gagnant d'un exclusif.
  - `get_slot_conflicts()` et `get_slot_contributors()` exposent les candidats.
- Nouvelles commandes :
  - `axiom mods conflicts` (`mods_cmd.py` l.233) : conflits déclarés, cycles, exclusifs (calculés
    depuis les manifestes par `resolver.compute_exclusive_conflicts`, plus le registre s'il est chargé),
    sous la forme « A, B provide it; 'A' wins » ;
  - `axiom mods order [ids…]` (l.261) : affiche ou enregistre l'ordre.
- Tests :
  - `test_user_order_from_config_picks_exclusive_winner` ;
  - `test_exclusive_slot_rule` (adapté).

### 1-NOYAU I3 (partie noyau) — contextes, désactivation à chaud, bootstrap unique, API publique
- `ModLoadState.contexts` : `{mod_id: ModContext}`.
- `disable_mod_hot(mod_id)` (loader l.675) retourne une de ces valeurs :
  - `"now"` : `cleanup()`, purge, cascade sur les dépendants ;
  - `"next_launch"` : le mod a des patches (enregistrés ou déclarés) ou du code brut déclaré, D-5.
    Le code brut se déclare dans `[contributes] raw_code = true`, nouveau champ `ModContributes.raw_code` ;
  - `"not_loaded"`.
- `ctx.cleanup()` retire aussi les emplacements déclarés par le mod (`registry.undeclare_slot`,
  propriétaire suivi). Le loader déclare `[provides_slots]` **via** le contexte.
- `get_kernel_registry()` (loader l.632) : un seul bootstrap par processus, D-4.
  `reset_kernel_registry()` existe pour les tests.
- API publique ajoutée sur `ModContext` (`context.py`), fin du besoin de `ctx._registry`
  (1-NOYAU m6) :
  - `get_slot`, `get_slot_contributions`, `apply_slot_chain`, `invoke_hook`, `invoke_hook_unguarded`,
    `has_hook` ;
  - `ctx._registry` reste disponible, pour la rétrocompatibilité.
- `ctx.spawn_job()` : thread daemon rattaché au contexte, avec `ctx.stop_event` / `ctx.should_stop()`.
  Au cleanup, l'événement est posé et le thread attendu `JOB_STOP_TIMEOUT` (2 s), puis abandonné
  avec un avertissement.
- `ctx.cleanup()` ne retire plus que **ses propres** patches. Avant, il retirait tous ceux du même
  `mod_id`, y compris ceux d'un mod déjà chargé pendant un `axiom mod test` : c'est la remarque de I9.
- Tests :
  - `test_hot_disable_now_or_next_launch` ;
  - `test_context_public_api_and_jobs_stopped_on_cleanup` ;
  - `test_single_bootstrap_per_process`.

### 1-NOYAU I11 / 4 I4 — mode sans échec = aucun mod
- `loader.is_mod_enabled` renvoie `False` pour **tout** mod en mode sans échec. `plan_modpack` marque
  chaque mod `safe_mode`.
- `is_official_mod` ne sert plus à rien dans le noyau. Il est gardé, marqué « Deprecated », pour ne
  pas casser les imports existants.
- Test : `test_safe_mode_loads_no_mod_even_axiom_prefixed` (un mod tiers nommé `axiom.evil` n'est pas
  chargé).
- Manque connu, non contourné : avec `--safe-mode`, **`main.py` refuse de démarrer**, car
  `axiom.ui.qt` est un mod (`main.py:418`). `main_web.py` fait de même, et `axiom play` aussi
  (`axiom.cli`). Seule la CLI du noyau (`axiom --safe-mode mods list/enable/disable`) fonctionne. Il
  n'existe pas encore de mod « chat minimal ». Je n'ai réintroduit aucun privilège.

### 1-NOYAU I8 — découverte indépendante du dossier courant
- `loader.discover_mods` (l.139) cherche dans deux dossiers :
  - les mods officiels : `get_official_mods_dir()`, relatif au paquet (`<repo>/mods`, surchargeable
    par `AXIOM_OFFICIAL_MODS_DIR`) ;
  - les mods utilisateur : `get_user_mods_dir()` = `axiom.paths.get_mods_dir()`, ajouté dans
    `paths.py` : `<data_dir>/mods`, qui respecte `AXIOM_DATA_DIR`.
- Comportement de la découverte :
  - `dist/mods` n'est plus scanné ;
  - un lien symbolique vers un dossier déjà vu est ignoré (`mods/axiom_ui_qt`) ;
  - en cas de doublon d'id, le premier dossier gagne (officiel avant utilisateur) et c'est journalisé.
- `mods_cmd.discover_installed_mods` délègue à `discover_mods`.
- Chemins par défaut :
  - scaffold : `<mods utilisateur>/<id>` ;
  - créateur : `target_mods_dir=None` → mods utilisateur ;
  - store : `dest_dir=None` → mods utilisateur, et `--dest` CLI par défaut à `None`. Le store ne
    copie plus d'archive dans `dist/mods`, et son index local par défaut est résolu en absolu ;
  - `pack_mod` par défaut : `<cwd>/dist/mods` en absolu (sortie de build, plus jamais découverte).
- Tests :
  - `test_discovery_is_independent_of_cwd_and_ignores_dist` (exécuté avec `chdir` vers un autre
    dossier) ;
  - `test_scaffold_and_store_default_to_user_mods_dir`.

### 1-NOYAU I7 — `.axmod` multi-fichiers
- `loader._extract_archive` (l.386) : l'archive est extraite une seule fois dans
  `<mods utilisateur>/.axmod-cache/<id>-<version>-<sha256[:16]>`.
  - Un membre de l'archive dont le chemin sortirait du dossier fait refuser l'archive entière.
  - `main.py` est exécuté **comme un paquet** (`submodule_search_locations`), donc `from . import x`
    fonctionne. C'est aussi vrai pour les dossiers.
- Nouveau `axiom/kernel/importer.py` : chaque mod chargé enregistre sa racine, et `mods.<id>.<module>`
  se résout vers elle.
  - Cela marche sans les sources dans le repo, et sans le paquet `mods` (installation pip).
  - Le noyau n'importe plus `mods` : `axiom/kernel/__init__.py` et `loader.py` ne font plus
    `importlib.import_module("mods")`. Vérifié : `import axiom.kernel` → `'mods' in sys.modules == False`.
- `mods/__init__.py` : le finder renvoie `None` (donc `ImportError`) quand le dossier du mod existe
  mais pas le module demandé, ou quand aucun dossier ne correspond. Les espaces de noms intermédiaires
  (`mods.axiom`) n'existent que si un dossier `axiom.*` existe.
- Tests :
  - `test_multi_file_axmod_loads_without_sources` (import relatif, plus `mods.multi.pack.deep.engine`,
    sources supprimées) ;
  - `test_axmod_with_unsafe_member_is_refused` ;
  - `test_mods_finder_raises_import_error_for_unknown_names`.

### 1-NOYAU B2 + 4 I1(3) + 3-MODS mineur, m2, m3, m4 — patches
- `patcher.resolve_target` accepte trois formes : `module:func`, `module:Classe.methode` (chaîne de
  `getattr`) et `module.a.b` (le plus long préfixe importable).
  - Pour les méthodes, le `__code__` de la fonction sous-jacente est remplacé. Cela couvre
    staticmethod, classmethod, et les méthodes liées capturées avant le patch.
  - **Closures prises en charge** : le trampoline est généré avec les mêmes variables libres. Cela
    inclut les méthodes qui utilisent `super()`.
- Refus bruyant : `PatchTargetError` est levée, et **rien** n'est ajouté à la pile. Cela couvre : une
  cible introuvable, un module introuvable, une classe, un attribut non appelable, une fonction C,
  un format invalide.
  - `ctx.patch` laisse remonter l'erreur, donc l'`init()` du mod échoue et le mod est écarté.
- `get_active_patches()` ignore les patches suspendus.
- `axiom mods patches` :
  - ne liste que la pile réelle du processus ;
  - `--load` charge d'abord le modpack (`get_kernel_registry`) pour montrer les vrais patches (m10) ;
  - sinon, il montre les patches **déclarés** dans une liste séparée, étiquetée « NOT active here ».
- m2 : l'ordre est `priority`, puis l'ordre de chargement (`set_patch_mod_order`, posé par le
  bootstrap), puis l'ordre d'enregistrement. À priorité égale (100 par défaut), l'ordre utilisateur
  s'applique.
- m3 : un handler qui lève suspend tous les patches de son mod. Le bootstrap notifie le registre,
  qui désactive le mod. L'appel continue sans ce handler :
  - pour un AROUND, avec le résultat interne s'il a déjà été calculé ;
  - une exception de la fonction patchée elle-même n'est jamais imputée au patch.
- m4 : le gel est un compteur réentrant. Un `cleanup()` pendant un step gelé suspend les patches
  tout de suite, puis les retire au dégel (plus de `PatchingDuringStepError` dans ce cas).
- Convention `@patchable` documentée dans `api.py` et dans le docstring de `patcher.py` : nommer
  `"<module>:<qualname>"`. **Je n'ai marqué aucune fonction du moteur.**
- Tests (`tests/test_kernel_patch_targets.py`) :
  - `test_method_targets_and_restore` ;
  - `test_dotted_method_target_and_closure` ;
  - `test_unpatchable_targets_are_refused_loudly` (8 cas, dont l'exemple du DOC
    `axiom.world:calculate_stamina`) ;
  - `test_mods_patches_never_lists_inactive` ;
  - `test_faulty_handler_disables_mod_patches_and_call_goes_on` ;
  - `test_freeze_is_reentrant` ;
  - `test_cleanup_during_frozen_step_deactivates_then_removes` ;
  - `test_equal_priority_follows_load_order`.
- `tests/test_patching_system.py` passe sans modification.

### 1-NOYAU I9 + I10 + 4 I5 — créateur LLM, scaffold, tester
- `llm_creator.generate_mod` (l.233) **n'exécute plus rien**. Il :
  - valide chaque chemin **avant d'écrire** (`_safe_relative_path` : refus des chemins absolus, des
    `..`, des lettres de lecteur, plus une vérification de résolution dans le dossier de préparation) ;
  - fait une validation statique (`tester.validate_mod_static`, sans exécution) : manifeste, API,
    AST de chaque `.py`, noms de hooks et d'emplacements déclarés dans `mod.toml` **et** utilisés
    littéralement dans `register_hook(...)` / `contribute_slot(...)`, imports d'UI ;
  - vérifie que `mod_id` correspond à l'id du manifeste ;
  - produit un diff, qui inclut les fichiers supprimés.
- `ModGenerationResult.validation_passed`. `tests_passed` est gardé comme alias en lecture seule,
  car `main_web.py` le lit.
- `apply_generated_mod` (l.347), appelé après le « oui » :
  - lance `test_mod`, ce qui est la **première exécution** du code ;
  - en cas d'échec, lève `ModTestsFailedError` et **n'installe rien** ;
  - remplace le dossier proprement (copie dans un dossier temporaire voisin, `rmtree` de l'ancien,
    renommage) ;
  - écrit le `.axmod` à côté du dossier de préparation, plus jamais dans `dist/mods` du repo
    (corrige aussi m14).
- `mods_cmd.run_mod_generate` affiche « Static validation (no code executed) », précise que les
  tests tournent après confirmation, et attrape `ModTestsFailedError`.
- Le mot « sandbox » a été remplacé par « dossier de préparation » / « preparation folder » dans le
  code et les messages du noyau et de la CLI des mods.
- Liste unique : `axiom/kernel/api.py`.
  - `PUBLIC_HOOKS` (8, établie par grep `invoke_hook|execute_hook`) :
    - `axiom.kernel:execute_step` ;
    - `axiom.step:gather_context`, `axiom.step:arbitrate_mutations`, `axiom.step:after_step` ;
    - `axiom.turn:arbitrate_stats` ;
    - `axiom.universe:compile`, `axiom.universe:decompile`, `axiom.universe:refresh_definition`.
  - `PUBLIC_SLOTS` (14, établie par grep `get_slot|get_slot_contributions|apply_slot_chain`) :
    - `axiom.kernel:locales`, `axiom.kernel:help_entries` ;
    - `axiom.turn:prompt_sections`, `axiom.turn:output_fields`, `axiom.turn:stream_filter`,
      `axiom.turn:final_text_filter`, `axiom.turn:llm_backend` ;
    - `axiom.providers:drivers`, `axiom.world:custom_rules` ;
    - `axiom.ui.qt:sidebar_widget`, `axiom.ui.qt:settings_tab` ;
    - `axiom.ui.web:side_panel`, `axiom.ui.web:settings_tab`, `axiom.ui.web:action_button`.
  - Règle `check_extension_point` : un nom `axiom.*` absent de la liste et non déclaré par le mod
    lui-même est refusé. Les autres espaces de noms restent libres (D10).
  - Les emplacements déclarés mais jamais lus (`axiom.world:entity_types`, `axiom.inventory:actions`,
    `axiom.help_system:contributions`, `axiom.sillytavern:importers`) ne sont volontairement pas dans
    la liste.
- Qui utilise cette liste :
  - le prompt (`build_system_prompt()`). Il ne contient plus `first_win`, `axiom.turn:after_step`,
    `axiom.time:tick` ni `axiom.world:rules`, et ses exemples utilisent les formats réellement acceptés
    par `axiom.turn` (`{"position","text","depth"}`, `(champ, handler)`) ;
  - le tester (`validate_mod_static`, appelé aussi par `test_mod`) ;
  - le scaffold : ses modèles utilisent maintenant `axiom.step:gather_context` / `axiom.step:after_step`,
    et le modèle « slot » contribue un champ de sortie routé et une section de prompt au bon format.
- Tests :
  - `tests/test_kernel_creator_safety.py` : `test_generate_executes_nothing_before_confirmation`
    (un marqueur écrit par `main.py` et par le test généré n'existe pas avant `apply`) ;
  - `test_paths_leaving_preparation_folder_are_refused` (4 cas) ;
  - `test_unknown_hook_is_flagged_statically` ;
  - `test_failing_tests_install_nothing_and_replacement_is_clean` ;
  - `test_single_catalogue_drives_prompt_scaffold_and_tester` ;
  - `tests/test_mod_creator.py` adapté (hooks `axiom.step:*`, `validation_passed`).

### Mineurs
- **m7** : `tester.py` utilise `os.pathsep`. Test : `test_tester_pythonpath_uses_os_pathsep`.
- **m8** : `PySide6` et `PySide2` ajoutés aux imports UI interdits. Seule une dépendance `axiom.ui.*`
  les autorise : plus de « l'id contient ui ». Test : `test_pyside6_import_is_forbidden_without_ui_dependency`.
- **m9** : un paquet pip manquant donne le statut `missing_python_deps` avec le message. Il est
  visible dans `mods list`, et les dépendants sont écartés. Test :
  `test_missing_python_dependency_visible_in_mods_list`.
- **m10** : voir B2 (`axiom mods patches`, `--load`).
- **m13** (`axiom/cli/test.py`) : `--golden` utilise un chemin absolu vers `tests/test_golden_step.py`
  et un `cwd` à la racine, avec un message clair si la suite est absente (installation sans sources).
  Ce n'est toujours pas un `axiom mod test` basé sur le harnais golden : voir §2.
- `dev.py` : les emplacements sont déclarés via le contexte. Le module est rechargé comme un paquet
  (les sous-modules périmés sont purgés). Une édition cassée appelle `cleanup()`, pour ne pas laisser
  un demi-mod.
- **Store** (point 12) :
  - `install_mod_from_store` refuse une archive dont l'id du manifeste diffère de l'id du catalogue ;
  - installation dans les mods utilisateur ;
  - comparaison d'API via `KERNEL_API`.
  - Rien d'autre n'a changé.

## 2. Non corrigé / partiel
- **m12** (`export_engine.py`, hors périmètre). Correctif proposé : ajouter à la liste des motifs
  interdits (l.49) un second motif qui détecte les imports dynamiques, par exemple
  `r"""(?:import_module|__import__)\(\s*['"]mods(?:\.|['"])"""`.
  - Le noyau n'utilise plus ce contournement.
  - Les proxys `axiom/inventory.py`, `time_system.py`, `living_memory.py`, `stat_dynamics.py` et
    `image_generator.py` l'utilisent encore : ce sont eux que le motif fera échouer, ce qui est voulu
    (lot « vraie phase 2 »).
- **I3, adoption** : `Session` (`session.py:157`), `main.py:436`, `main_web.py:2859`,
  `mods_dialog.py:520-534` et `main_window.py:80` appellent encore `bootstrap_all_mods`. Il faut :
  - les passer à `get_kernel_registry()` ;
  - utiliser `disable_mod_hot()` dans le dialogue des mods, et afficher « au prochain lancement »
    quand il renvoie `"next_launch"` ;
  - utiliser `is_mod_active()` / `get_mod_status()` au lieu de `is_mod_enabled()` dans les UI.

  Ce n'est pas fait ici (hors périmètre). Tant que ce n'est pas fait, chaque bootstrap ré-exécute
  les `main.py`, réenregistre les patches globaux, et ajoute un écouteur de panne de patch.
- **Mods officiels à adapter** (rétrocompatible, rien n'est cassé aujourd'hui) :
  - remplacer `ctx._registry.get_slot_contributions(...)` par `ctx.get_slot_contributions(...)`, dans
    `mods/axiom.providers/main.py:64-79`, `mods/axiom.ui.qt/main.py:32-39` et `mods/axiom.ui.web/main.py:27-40` ;
  - dans `mods/axiom.turn/main.py:175`, remplacer `reg = ctx._registry` par les méthodes du contexte ;
  - lancer les threads via `ctx.spawn_job` dans `axiom.illustrations/main.py:133`,
    `axiom.living_memory/living_memory.py:577` et `axiom.ui.web/main.py:62` ;
  - optionnel : les handlers `output_fields` / `prompt_sections` appelés dans `axiom.turn` devraient
    être isolés un par un (3-MODS B4), ou passer par une méthode du registre.
- **`ctx.store`, époques des jobs (§10.4), `ctx.config` propre (m11)** : non traités (lot stockage).
  `spawn_job` n'a pas de capture d'époque, car le noyau ne connaît pas l'époque de session.
- **`axiom mod test` sur le harnais golden (m13, §12)** : non fait.
- **Réserver `axiom.*` aux mods livrés** (suggestion de I11) : non fait, ce n'était pas demandé.
  Seule protection : en cas de doublon d'id, le dossier officiel gagne sur le dossier utilisateur.
- **Mode sans échec** : voir plus haut, l'app graphique ne démarre pas sans mod d'UI.
- **m1, m5 (récursion), m11** : non traités.

## 3. Tests exécutés
Toutes les commandes ont été lancées avec
`AXIOM_CONFIG_DIR=$(mktemp -d) AXIOM_DATA_DIR=$(mktemp -d) .venv/bin/python -m pytest <fichier> -q`,
un fichier par processus.

| Fichier | Résultat |
|---|---|
| `test_kernel_loader.py` | 13 passed |
| `test_patching_system.py` | 6 passed |
| `test_mod_creator.py` | 14 passed (n'écrit plus dans `dist/mods`) |
| `test_kernel_resilience.py` (nouveau) | 14 passed |
| `test_kernel_patch_targets.py` (nouveau) | 15 passed |
| `test_kernel_discovery_and_archives.py` (nouveau) | 6 passed |
| `test_kernel_creator_safety.py` (nouveau) | 10 passed |
| `test_mod_store_and_packaging.py` | 9 passed |
| `test_mods_decoupling_and_effectivity.py` | 7 passed |
| `test_mod_localization.py` | 9 passed |
| `test_world_turn_mods.py` | 6 passed |
| `test_time_inventory_mods.py` | 5 passed |
| `test_memory_mods.py` | 5 passed |
| `test_golden_step.py` | 5 passed |
| `test_engine_headless.py` | 1 passed |
| `test_cli_play.py` | 14 passed |
| `test_ui_mods_and_cli.py` | **7 passed, 1 failed** : `test_cli_mods_management_and_safe_mode`, l.215-217, affirme « Official mods stay enabled » en mode sans échec, ce qui est l'ancien privilège retiré par le point 6. **À adapter par le lot qui possède ce fichier** : en safe mode, `is_mod_enabled(...)` doit être `False` pour `axiom.world` et `core.stat_dynamics` ; supprimer les assertions sur `is_official_mod` ou les garder comme fonction dépréciée. |

Tests supplémentaires (hors liste) :

| Fichier | Résultat |
|---|---|
| `test_providers_illustrations_mods.py` | 5 passed |
| `test_sillytavern_mod.py` | 7 passed |
| `test_stat_dynamics_mod.py` | 7 passed |
| `test_mod_ui_deactivation.py` | 6 passed |
| `test_test_isolation.py` | 7 passed |
| `test_session.py` | 16 passed |
| `test_help_system_mod.py` | 7 passed |
| `mods/community.survival/tests` | 1 passed |
| `mods/core.stat_dynamics/tests` | 7 passed |
| `test_mods_dialog_ui.py` | 5 passed, mais 1 exécution sur 5 s'est terminée par une segmentation fault **après** les tests |

Sur cette segmentation fault : 3 relances en `-q` et 1 en `-v` sont propres. C'est le problème connu
TICKET-067 (Qt multimédia + torch/chromadb), pas une régression du noyau.

Contrôle manuel : `axiom mods list/conflicts/order/patches` et `axiom --safe-mode mods list`, lancés
depuis `/tmp`, trouvent les 15 mods officiels et affichent les statuts et raisons attendus.

## 4. Suppressions proposées, hors périmètre, questions
- **Suppressions proposées** (je n'ai rien supprimé) :
  - `mods/axiom_ui_qt` (lien symbolique inutile ; la découverte l'ignore maintenant) ;
  - `dist/mods/community.fatigue-0.1.0.axmod` (artefact ignoré par git, recréé par ma première
    exécution de référence de `test_mod_creator.py`, avant correction ; il n'est plus découvert ni
    recréé).
- **Hors périmètre à toucher** :
  - `export_engine.py:49` (m12, voir §2) ;
  - `tests/test_ui_mods_and_cli.py:213-217` (voir §3) ;
  - `axiom/cli/main.py:61` et `main.py:387` : le texte d'aide dit encore « third-party mods
    disabled » ; il doit dire « no mod is loaded » ;
  - `session.py`, `main.py`, `main_web.py`, `mods_dialog.py`, `main_window.py` : adoption de
    `get_kernel_registry` / `disable_mod_hot` / `is_mod_active` (voir §2) ;
  - `main_web.py:2365` lit `result.tests_passed` (alias conservé). L'UI web devrait afficher « validation
    statique » et gérer l'erreur `ModTestsFailedError` de `/api/mods/apply` ;
  - mods officiels (voir §2).
- **Questions pour le propriétaire** :
  1. Valides-tu que `axiom.kernel:execute_step` soit un hook « critique » par défaut (les erreurs du tour
     remontent telles quelles, sans désactiver `axiom.turn`) ?
  2. Emplacement de l'ordre utilisateur : `mod_settings["axiom.kernel"]["mod_order"]` te convient-il ?
  3. Doublon d'id entre le dossier officiel et le dossier utilisateur : faut-il que l'officiel gagne (choix
     actuel, prudent), ou l'utilisateur (permettrait des mises à jour d'un mod officiel via le store) ?
  4. Mode sans échec : faut-il prioriser un mod « chat minimal » (B5) pour que l'app démarre
     avec `--safe-mode` ?
