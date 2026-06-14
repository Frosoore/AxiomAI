# CHANGELOG — Audit app GUI + CLI & corrections (2026-06-14)

Constat dans `RAPPORT.md`. Tous les items corrigés (feu vert « corrige tout »).
Suite : **767 verts** (706 hors vector/Qt + 61 vector/Qt), +2 tests. Branche `dev-win-compat`.

## Bugs

### App-B1 — `DbWorker.load_full_universe` dédoublé supprimé (`workers/db_worker.py`)
Suppression de la 1ʳᵉ définition morte (référençait `LoadFullUniverseTask`, **inexistant** → aurait
levé `ImportError`, masquée par la 2ᵉ). La version vivante (inline) a ensuite été extraite proprement
(cf. App-A1). Suppression aussi de l'en-tête « Legacy/Remaining tasks ».

### App-B2 — Label « Regenerate » traduit (`ui/widgets/chat_display.py`)
`reg_text = tr("regenerate") if "regenerate" in tr("ready") else "Regenerate"` (condition absurde →
anglais en dur) → `reg_text = tr("regenerate")`. Le bouton suit désormais les 10 langues.

## Architecture

### App-A1 — Pattern « TempTask inline » extrait vers `workers/db_tasks.py`
Les 9 méthodes qui définissaient une sous-classe anonyme de `LoadStatsTask` recréée à chaque appel
(SQL noyé dans `db_worker`) sont devenues de **vraies tâches nommées** héritant de `BaseDbTask` :
`LoadUniverseMetaTask`, `LoadEntitiesAndRulesTask`, `SaveUniverseMetaTask`, `SaveFullUniverseTask`,
`LoadLibraryTask`, `LoadSavesTask`, `LoadFullUniverseTask`, `LoadGlobalPersonasTask`,
`SaveGlobalPersonasTask`. `db_worker` ne dispatche plus que ces tâches (imports `sqlite3`/`json`/
`closing`/`get_connection`/`migrate_*` retirés du fichier — le SQL vit côté `db_tasks`). Comportement
et signaux **inchangés** (round-trip save→load vérifié en réel + tests existants).

### App-A2 — `take_snapshot_async` / `SnapshotTask` supprimés
Code mort (jamais appelés) ; depuis le fix moteur **A2** (snapshots périodiques dans
`Session.resolve_tick`), la responsabilité vit au bon endroit, partagée GUI + CLI.

## Micro-optimisations

### App-M1 — N+1 stats supprimé (`workers/db_tasks.py`)
`LoadEntitiesAndRulesTask` et `LoadFullUniverseTask` chargent les `Entity_Stats` en **une requête
groupée** (`_read_stats_by_entity`) au lieu d'une requête par entité.

### App-M2 — Migrations idempotentes gatées (`workers/db_tasks.py`)
`ensure_universe_migrations(db_path)` lance les 6 `migrate_*` **une seule fois par (process, db_path)**
(`_MIGRATED_DBS` + lock) au lieu de ~6 connexions à chaque chargement d'univers. +1 test.

### App-M3 — Plus de lecture DB sur le main thread (`axiom/arbitrator.py` + `ui/tabletop_view.py`)
`ArbitratorResult` porte désormais `in_game_time` (temps absolu = valeur écrite au Timeline, calculé
par le moteur). `_on_turn_complete` lit `result.in_game_time` au lieu d'appeler `get_current_time()`
(sqlite) sur le thread UI. +1 assertion de test.

### App-M4 — Langue courante mémorisée (`core/localization.py` + `ui/main_window.py`)
`_current_language()` met la langue en cache (évite un `load_config()` par appel de `tr()`, soit des
centaines de `os.stat` par rendu). Invalidé par `reload_translations()`, appelé par `MainWindow`
au save des réglages (seul endroit où la langue change). Les tests qui patchent `_current_language`
en entier ne sont pas affectés (le patch contourne le cache).

## Tests
- +2 tests : `ensure_universe_migrations` ne migre qu'une fois (M2) ; `ArbitratorResult.in_game_time`
  == temps Timeline (M3).
- Couverture existante préservée : `test_db_worker_atomic`, `test_lore_persistence`,
  `test_persona_global`, `test_phase6`, `test_dev_hotreload` (tous verts) exercent les tâches
  extraites end-to-end via la boucle Qt.
- Suite : **767 passed, 0 échec** (706 + 61).
