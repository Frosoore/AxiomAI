# Lot B2 — le tour de jeu et ses régressions : rapport (2026-10-03, ARRÊTÉ en cours)

Le propriétaire a demandé l'arrêt pendant le travail. Le code est laissé cohérent (tous les fichiers
modifiés compilent). Rien n'a été commité, indexé ni supprimé.

## 1. Corrigé

### K6 / 3-MODS B4 / 2-PHASE0 I-6 — erreurs du tour et isolation des mods
- `axiom/session.py` `resolve_tick` : appel par `invoke_hook_unguarded("axiom.kernel:execute_step")`,
  l'exception d'origine (ex. `LLMConnectionError`) remonte telle quelle jusqu'à
  `workers/narrative_worker.py` et `axiom/cli/play.py` (message « LLM unreachable » rétabli).
  L'ancien `RuntimeError("Turn pipeline mod returned no result")` est remplacé par un message explicite.
- `mods/axiom.turn/main.py` (réécrit) : chaque section de prompt et chaque handler `output_fields`
  est appelé un par un ; en cas d'exception, le mod fautif est désactivé (`ctx.report_fault`) et le
  tour continue. Filtres (chaînes) et hooks `axiom.step:*` : isolés par le noyau. Nouveau champ
  `ArbitratorResult.faulted_mods` (mods désactivés pendant ce tour).
- Tests : `tests/test_turn_pipeline_b2.py` : `test_faulty_mod_contribution_is_disabled_and_turn_goes_on`,
  `test_llm_connection_error_reaches_the_caller_unchanged`, `test_qt_worker_shows_llm_unreachable_message`,
  `test_cli_play_shows_llm_unreachable_message`.

### M4 / 3-MODS B3 / 2-PHASE0 I-1 / TICKET-105 — boucle de correction
- `axiom/arbitrator.py` : `TurnContext.queue_correction()` + `correction_hints` ; l'indice est
  écrit comme event `correction_hint` du tour dans l'Event_Log (`step_6`), relu au tour suivant
  (`_load_pending_correction`, tour N-1 uniquement) → rembobiné automatiquement. Plus de
  `_pending_correction` sur l'objet.
- `mods/axiom.world/main.py` : transmet ses rejets (`ctx.queue_correction`), rétablit
  `rule_chain_warning` + event `rule_engine_warning`. La validation complète de `main` y est portée
  (ressource sous zéro, stat non liée au type, alias d'entité par nom/« player », armure scénaristique
  du héros Companion, distance de voyage) : c'était une **régression non signalée par la revue**
  (le chemin mod ne faisait qu'une validation partielle). Règles custom via `ctx.get_slot`.
- Tests : `test_correction_hint_reaches_next_turn_and_is_rewound` (scénario `ghost_zz`, rewind),
  `test_rule_chain_warning_is_reported`, et `tests/test_arbitrator.py::TestCorrectionLoop` réécrit.

### 0f / R2-m-5 / R3-I2 — orchestration unique
- `ArbitratorEngine.process_turn` ne duplique plus le tour : il dispatche vers le hook du mod
  `axiom.turn` (moteur passé via `KernelStepContext.extras`). `axiom/multiplayer.py` passe donc par le
  chemin réel (docstring mise à jour).
- `gather_context` déclenché une seule fois (dans `step_1`, retiré de l'orchestrateur).
- Branches `if self.kernel_registry is None` supprimées, ainsi que le code mort devenu inutile :
  `_validate_change`, `_stat_allowed_for_entity`, `_get_travel_distance`, `_validate_inventory_change`
  (→ **R2-I-7 côté arbitre : l'écriture hors batch disparaît avec ce code mort**),
  `_resolve_inventory_holder`, `_tick_stat_dynamics`, `_mark_event_as_fired`, `_apply_local_change`.
- `_ENGINE_CACHE` supprimé ; moteur mis en cache par Session (`WeakKeyDictionary`), sans état de jeu.
- `tests/test_arbitrator.py` : 50 tests conservés, tous sur le chemin réel (règles écrites en base,
  indexation vérifiée dans le store du mod `axiom.rag`, validation d'inventaire via le mod
  `axiom.inventory`, test « 6 étapes » avec le registre réel). Tests : `test_gather_context_hook_runs_once_per_turn`,
  `test_process_turn_uses_the_turn_mod_pipeline`.

### K7 — un seul bootstrap
- `Session` : `get_kernel_registry()` (bootstrap dédié seulement si `cfg=` explicite, cas tests/embarqueurs).
  `main.py` et `main_web.py` : `get_kernel_registry(cfg)`. Qt (Session par tour) en profite.
  Test : `test_sessions_share_the_process_modpack`.

### K11 — API publique
- `ctx._registry` retiré de `axiom.turn`, `axiom.providers`, `axiom.ui.qt/main.py`, `axiom.ui.web/main.py`.
  `spawn_job` : `axiom.ui.web` (serveur + arrêt au cleanup), `axiom.illustrations` (repli sans batch).
  `axiom.providers` : un service par `init` (plus de service global au contexte périmé).

### Autres
- R2-m-6 : `Session.fork()` n'incrémente plus l'époque source (test `test_fork_does_not_bump_the_source_epoch`,
  et assertion adaptée dans `tests/test_golden_step.py`). `Session.rewind` ne bumpe plus lui-même
  (le lot B1 a mis le bump dans `CheckpointManager.rewind` ; sinon double incrément).
- 0b (partiel) : auto-canonize en post-commit unique dans `Session._maybe_auto_canonize` (thread,
  un seul job par save, ignoré si mort Hardcore ou époque changée). Réglage :
  `mod_settings["axiom.turn"]["auto_canonize"]` (`get_auto_canonize`/`set_auto_canonize`), car
  `axiom/config.py` est hors périmètre. Test `test_auto_canonize_is_a_session_post_commit_step`.
- R3-I5 `main_web.py` : rattrapage mémoire living → `Session.start_living_memory_catchup()` ;
  repli d'inventaire écrivant en base supprimé (409 si le mod est absent).
- M8 : `axiom.session.resolve_llm_backend()` (slot `axiom.turn:llm_backend`, service `providers` pour
  les modèles auxiliaires, repli `build_llm_from_config` sans le mod). Utilisé par Session
  (narration, Timekeeper, héros) et partout dans `main_web.py`. Test `test_llm_backend_comes_from_the_providers_slot`.
- M9 : `community.survival` désactivé par défaut (`[mod] enabled_by_default = false`, nouveau champ
  lu par `loader.is_mod_enabled/plan_modpack`) et dépendance `axiom.turn` déclarée ;
  `axiom.ui.qt` déclare `axiom.help_system` en dépendance **optionnelle** (l'UI gère le mod désactivé,
  mais importe ses fichiers : le désinstaller casse toujours l'UI). Test `test_community_survival_is_off_by_default_and_can_be_enabled`.
- `TurnContext` porte `llm`, `epoch`, `epoch_checker` (mémoire living et Chronicler) ; `axiom.time`
  passe le vrai LLM au Chronicler (il recevait `None` : Chronicler inopérant).

### Ajouts minimaux au noyau (documentés)
- `KernelStepContext` : `history`, `system_prompt`, `extras`.
- `KernelRegistry.get_slot_entries`, `report_fault` ; `ModContext.get_slot_entries`, `report_fault`, `get_faulted_mods`.
- `loader` : `is_enabled_by_default`, paramètre `manifest` de `is_mod_enabled`.

## 2. Non fait / partiel (arrêt demandé)
- **Qt `tabletop_view.py`** : pas touché. Restent : appel `_maybe_auto_canonize` (l.~870, 1179) →
  **double canonisation si le réglage est activé ET la case Qt cochée** (case non reliée au réglage) ;
  code mort `_run_fact_extraction` / `_fact_*` ; `build_llm_from_config` (l.438, 572) à remplacer par
  `resolve_llm_backend`. `workers/fact_worker.py` : suppression proposée une fois ce code retiré.
- **`web/app.js`** : `maybeAutoCanonize` (l.1410, 1436, 4310) non retiré ; endpoint web pour le
  réglage non créé.
- **`mods_dialog.py`** (`disable_mod_hot` + « au prochain lancement ») : non fait.
- **`axiom/cli/play.py`** : construit encore le LLM avec `build_llm_from_config` (passer à `resolve_llm_backend`).
- **Point 10** `tests/test_ui_mods_and_cli.py::test_cli_mods_management_and_safe_mode` : non adapté (échoue toujours, cf. C-NOYAU).
- `main_web.py` `/api/creator/infer-stats` : utilise encore le proxy `axiom.stat_dynamics` (outil
  créateur, pas logique de tour) — à passer par un service de `core.stat_dynamics`.
- Hors périmètre (à faire par B1) : `axiom.inventory` doit appeler `ctx.queue_correction(...)` sur
  rejet (aujourd'hui `logger.debug`) et ne plus écrire/commit `ensure_item_definition` pendant la
  validation (R2-I-7 côté mod) ; `axiom.rag` indexe dans son propre store, pas dans le
  `vector_memory` de la session. `axiom.living_memory/living_memory.py:577` → `spawn_job`.
  `mods/axiom.ui.qt/ui/main_window.py:80` appelle encore `bootstrap_all_mods` (sans effet si le registre existe).
- Le tick des modificateurs n'est fait que par `core.stat_dynamics` (désactivé → modificateurs qui
  n'expirent plus) : à déplacer dans le noyau du tour (lot E).
- Clés de traduction à ajouter dans `core/locales` pour les messages de l'écran des mods.

## 3. Tests exécutés (avec `AXIOM_CONFIG_DIR`/`AXIOM_DATA_DIR` temporaires)
- `test_session, test_golden_step, test_engine_headless, test_cli_play` : 36 passed.
- `test_arbitrator` : 50 passed.
- `test_turn_pipeline_b2` (nouveau) : 13 passed.
- **Non relancés après les dernières modifications** (mods `providers/ui.web/ui.qt/illustrations`,
  `main.py`, `main_web.py`, loader) : `test_world_turn_mods, test_time_inventory_mods,
  test_stat_dynamics_mod, test_providers_illustrations_mods, test_mods_decoupling_and_effectivity,
  test_ui_mods_and_cli, test_web_server, test_web_server_startup, test_generation_cancel`, les tests Qt,
  `test_kernel_*`. Risque connu : `test_mods_decoupling_and_effectivity` et tests attendant
  `community.survival` actif par défaut ; golden si les fixtures dépendaient du Chronicler inopérant.

## 4. Questions
1. Réglage « Canon auto » : OK dans `mod_settings["axiom.turn"]`, ou ajouter un champ à `AppConfig` ?
2. `axiom.help_system` optionnel pour l'UI Qt : OK, ou rendre les imports gardés ?
