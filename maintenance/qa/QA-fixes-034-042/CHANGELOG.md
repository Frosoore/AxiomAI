# QA-fixes-034-042 — CHANGELOG

## 2026-06-10 — correction en lot des tickets QA (034→042)

**Moteur (`axiom/`) :**
- `saves.py::fork_save` — copie désormais `Active_Modifiers` (modifier_id régénéré) et
  `Fired_Scheduled_Events` (TICKET-034). Test : `test_fork_copies_modifiers_and_fired_events`.
- `populate.py` — `populate_events` saute les `event_id` déjà présents (PK) au lieu de crasher
  en IntegrityError ; `populate_stats` désambiguïse une collision de `stat_id` entre noms
  différents (TICKET-035). Nouveau helper `entity_id_for(name)` : id déterministe
  (`ent_<sha1[:12]>`) pour les noms 100 % non-latins, au lieu d'un saut silencieux
  (TICKET-041) — utilisé par `populate_entities` ET `workers/db_tasks._insert_canon`
  (déduplication au passage). Tests : `test_populate_events_collision_id_sautee`,
  `test_populate_stats_collision_id_desambiguisee`, `test_populate_entities_nom_non_latin`.
- `savestore.py::unpack_save` — réécrit `Save_Meta` (`universe_key`/`universe_db`/
  `universe_source`, `definition_hash` vidé) sur l'univers de **destination** : une save
  importée se resynchronise désormais avec la source locale, et la canonisation la retrouve
  (TICKET-036). Manifest `.axiomsave` : échappement TOML des valeurs (042.8).
  Test : `test_unpack_relie_la_save_a_l_univers_local`.
- `library.py::convert_flat_db_to_folder` — marque `origin='runtime'` les entités joueur
  (hors héros compagnon) AVANT extraction/décompilation, et purge les entités runtime de
  l'arbo décompilée (helpers `_mark_legacy_runtime_entities` + `_strip_runtime_entity_files`,
  ce dernier partagé avec `sync_source_from_db`) — le joueur ne pollue plus la définition de
  l'univers converti (TICKET-037). Test : `test_conversion_n_exporte_pas_le_joueur`.
- TICKET-038 — toutes les connexions `with sqlite3.connect(...)` du périmètre récent passent
  en `with closing(...)` (le context-manager sqlite3 ne ferme pas) : `savestore.py`,
  `library.py`, `db_tasks.py` (`_stage_source_change`, `_resolve_universe_db`). Bloquant
  Windows levé sur `delete_save` (unlink avec connexion ouverte).
- `package.py::pack_universe` — l'archive `.axiom` ne publie que la définition : `.git/` et
  sidecars `-wal`/`-shm` exclus, cache embarqué remplacé par une copie **purgée des 8 tables
  runtime** (+ VACUUM) — les saves embarquées ne fuient plus dans les exports (TICKET-039).
  Test : `test_pack_definition_seule`.
- `decompile.py` — allocateur `_UniqueNames` : deux ids donnant le même `_safe_filename`
  n'écrasent plus le même fichier (suffixe `_2`, …) ; la purge runtime lit l'id DANS le
  fichier (042.7).
- `config.py::load_config` — cache invalidé par mtime de `settings.json` + `create_global_db`
  une seule fois par chemin : `tr()` ne refait plus une lecture disque + un connect sqlite à
  chaque chaîne traduite (042.1).
- `localization.py` — fr `short`→« Court » ; es `univ_params`/`chronicler_interval_label`/
  `multijugador`/`eliminada` ; de `chronicler_interval_label` (042.4).

**App (UI/workers) :**
- `tabletop_view.py` — garde `isinstance(payload, dict)` dans `_recent_narrative` (payloads
  legacy en chaîne brute : « Canoniser… » ne crashe plus, TICKET-040) ; flag `_canon_busy` :
  une seule canonisation à la fois (le « Canon auto » par tour n'écrase plus un worker en
  vol) (042.2).
- `creator_studio_view.py` — refresh de définition et conversion passent par le `DbWorker`
  de la vue (plus d'instances jetables écrasées en plein vol) (042.2).
- `db_tasks.py::BaseDbTask` — les tâches annulables s'inscrivent au registre dès la
  construction et `run()` court-circuite si déjà annulée : « Annuler » couvre les tâches
  encore en file QThreadPool (042.3). Test existant adapté + nouveau
  `test_tache_annulee_en_cours_emet_cancelled_pas_error`.
- `populate_tab.py` — suppression du court-circuit `'populate_warning' in tr('ready')`
  (toujours faux : anglais codé en dur) (042.4).
- `hub_view.py` — suppression d'univers : sidecars `-wal`/`-shm` du `.db` plat et dossiers
  `vector/<save_id>` des saves supprimés avec l'univers (042.5).
- `setup_view.py` + `db_worker.py`/`db_tasks.py` — `PrepareSaveTask` + signal `save_prepared` :
  la resync de définition au lancement d'une partie quitte le main thread (042.6) ; gestion
  d'erreur du lancement réarmée proprement.
- Hygiène repo : sidecars orphelins `debug_*.db-wal/-shm` supprimés de la racine (042.9).

**Tests :** suites complètes re-passées par sous-ensembles (cf. TODO).
