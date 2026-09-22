# CHANGELOG — Tickets 092→098 (2026-09-22)

Travail réparti : 093+098 (`web/`), 094 (`main_web.py`), 095 (`axiom/saves.py`, `axiom/modifiers.py`)
par des sous-agents Sonnet, relus et intégrés ; 092, 096, 097 + compléments faits directement.

- **092** `debug/startup_check.py` : `_uses_xcb()` (QT_QPA_PLATFORM explicite, sinon Wayland →
  plugin wayland) ; lib absente sous Wayland = WARNING + lancement autorisé, FAIL seulement si xcb.
  `tools/diagnostic.py` : même logique (WARN au lieu de FAIL sous Wayland).
- **093** `web/app.js` : `escapeHtml` échappe aussi `'` ; ~25 gabarits `innerHTML` échappés (Hub,
  personas, setup, lore hits, recherche, Creator Studio entités/stats/carte/règles/events/setup/lore,
  canonize, éditeur de save, lobby multijoueur) ; `statSelectHtml`, `saveInvHolderLabel`,
  `creatorAppliesToCell` échappent leurs données ; `formatMarkdown` échappe avant formatage ;
  nouveau `safeUrl` (liens/images : http(s), chemins `/…`, `data:image/…` ; sinon `#`) — vérifié
  (`javascript:`, casse mixte, `//evil.com` neutralisés ; liens légitimes intacts).
- **094** `main_web.py` : `send_cors_headers` sans ACAO ; `_security_guard()` en tête de
  `do_GET`/`do_POST`/`do_OPTIONS` ; `is_relative_to` sur `/assets/`, `/audio/`, `/api/creator/file`
  (GET+POST). 8 tests dans `tests/test_web_server.py`.
- **095** `axiom/saves.py::materialize_state` : lore filtré par `origin_turn`, modificateurs lus en
  direct au tour présent et via `axiom/modifiers.py::modifiers_at` (snapshots) au passé, champ
  `historical` ; `_snapshot_modifiers_now` après `import_save_state`/`apply_correction`.
  6 tests dans `tests/test_saves_editing.py`. Vérifié : `origin_turn` est `NOT NULL DEFAULT 0`
  (pas de lore legacy masqué).
- **096** `balanced` : `axiom/prompts.py`, `axiom/config.py` (défaut + repli), `axiom/cli/play.py`,
  `axiom/arbitrator.py`, `axiom/session.py` (×4), `axiom/multiplayer.py`, `workers/narrative_worker.py`,
  `workers/regenerate_worker.py`, `ui/settings_dialog.py`, `ui/tabletop_view.py` (index de repli 2→1),
  `web/app.js`. `core/localization.py::canonical_verbosity(value, default=None)` pure ; appelants
  `ui/tabletop_view.py`, `ui/creator_studio_view.py`, `main_web.py` passent le défaut config.
  Test ajouté dans `tests/test_localization.py`.
- **097** docstring `axiom/multiplayer.py` réécrite ; note dans `ARCHITECTURE.md`.
- **098** `web/index.html` : `data-tr="temporary"`, `data-tr="dyn_timescale"`.

## Vérifications
- `pytest tests/ --ignore=tests/test_ambiance_manager.py` : **1032 passed** ; ambiance seul : 7 passed.
- `debug/startup_check.py` OK ; `tools/i18n_check.py` OK ; `node --check web/app.js` OK.
- Lancement GUI réel : fenêtre visible.
- Non testé : web UI dans un vrai navigateur (seulement tests serveur + test Node des helpers).

## Suite (même jour, après retour utilisateur)
- **092** clos sans test X11 (pas de machine X11 ; on corrigera si un utilisateur X11 remonte un souci).
- **098** : solution retenue = rendre traduisible **tout** le bloc « Temporary » de l'éditeur de stat web
  (pas seulement 2 libellés). `dyn_kind` → « How it moves », `dyn_crash` → « Reset when (crash
  events) » (textes alignés sur les libellés réels, traductions refaites) ; 24 clés créées
  (`dyn_temporary_check`, `dyn_lasting_hint`, `dyn_kind_{heal,buildup,duration}`, `dyn_pace{,_fast,
  _medium,_slow}`, `dyn_resting{,_ph,_hint}`, `dyn_override`, `dyn_unit_{minutes,hours,days}`,
  `dyn_crash_{ph,hint}`, `dyn_extend{,_ph,_hint}`, `dyn_hint_{heal,buildup,duration}`) ×10 langues.
  `web/index.html` : `data-tr`/`data-tr-placeholder` (texte de la case enveloppé dans un `<span>` pour
  ne pas écraser l'`<input>`) ; `web/app.js::syncCreatorStatEditorChrome` : aides par type via `tr()`.
  `i18n_check` 804/804 ; `doc_check` OK ; tests web + i18n : 62 passed.
- **095 requalifié** : en creusant, le vrai problème est le rewind de jeu (inventaire jamais restauré,
  bug antérieur à `cb9e56d`) ; fiche PENDING réécrite avec la piste `Inventory_Snapshots`.

## TICKET-095 — inventaire restauré au rewind (feu vert utilisateur, même jour)
- `axiom/schema.py` : table additive `Inventory_Snapshots(save_id, turn_id, state_json)` (DDL +
  `EXPECTED_TABLES` + `ensure_inventory_snapshots_table`). Aucune migration de données.
- `axiom/inventory.py` : `snapshot_inventory` (écrit **toujours**, même vide), `snapshot_present_inventory`,
  `inventory_at` (None = tour non capturé), `rollback_inventory` (purge des snapshots futurs, restaure
  `Item_Instances` en gardant les `instance_id`, recrée une définition d'objet disparue).
- `axiom/arbitrator.py` : étape 7.5, capture du tour N-1 s'il manque (= état courant avant les
  changements du tour → couvre le tour 0 et les saves existantes) ; étape 9, capture de fin de tour.
- `axiom/checkpoint.py::rewind` : `rollback_inventory` dans la même transaction (docstring à jour).
- `axiom/saves.py` : `materialize_state` lit le snapshot pour un tour passé (repli legacy
  `Items_Inventory` préservé : drapeaux `inventory_historical`/`from_snapshot` séparés) ;
  `import_save_state` capture le tour 0 ; `apply_correction` re-capture le tour présent ;
  `fork_save` → `_fork_item_instances` : inventaire au tour du fork + snapshots copiés, avec **un seul**
  remappage d'ids (bug préexistant corrigé : ids régénérés sans remapper `holder_id` → contenu des
  sacs orphelin dans la copie).
- `main_web.py` `/api/session/inventory/move` : re-capture du tour présent.
- `axiom/savestore.py::_RUNTIME_COPY` et `axiom/package.py::_RUNTIME_TABLES` : table ajoutée.
- Tests : `tests/test_inventory_rewind.py` (10) + `TestInventoryRewindEndToEnd` dans
  `tests/test_arbitrator.py` (vrai tour avec `inventory_changes` puis rewind au tour 0) ;
  `test_materialize_inventory_is_not_historical` adapté (tours sans snapshot : inchangé ; tour
  présent : historique).
- Doc utilisateur : `docs/guides/saves.md` (section Rewind).
- Suite complète : **1043 passed** ; ambiance 7 passed ; startup_check OK.

## Ménage PENDING → DONE
- 086 (commité `c5afb31`), 091 (commité `1f48c82`), 087 (cache Myria plus suivi par git) étaient finis
  mais toujours listés → passés dans `DONE.md`. TICKET-088 mis à jour (inventaire du fork réglé).
