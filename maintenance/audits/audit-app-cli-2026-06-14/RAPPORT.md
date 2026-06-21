# Audit app GUI + CLI — 2026-06-14

Même démarche que l'audit moteur : revue qualité/optimisation/bugs/archi de la couche
**application** (`ui/`, `workers/`, `core/`, `main.py`) et du **CLI** (`axiom/cli/`).
**Constat global : la couche app est saine et bien découpée** (workers = coquilles fines,
threading discipliné, `main_window` sans backend). Les points ci-dessous sont surtout de la
**dette préexistante**, pas des régressions récentes. Rien modifié — rapport seul.

---

## 🐞 BUGS

### App-B1 — `DbWorker.load_full_universe` défini DEUX fois (`workers/db_worker.py:325` et `:514`)
La 1ʳᵉ définition dispatche un `LoadFullUniverseTask`… **qui n'existe pas dans `db_tasks.py`**
(import lazy ligne 326 → lèverait `ImportError`). Elle est **silencieusement écrasée** par la 2ᵉ
(gros SQL inline « TempTask »), donc l'`ImportError` ne se déclenche jamais et personne ne voit le
problème. Symptôme d'un refactor (extraire le SQL inline en tâche propre) **commencé puis
abandonné** sans supprimer l'ancienne méthode — et comme la morte est définie *avant*, c'est elle
qui aurait dû gagner mais Python prend la dernière. **Code mort cassé, masqué par le shadowing.**
→ Supprimer la 1ʳᵉ définition (lignes 325-329) et son helper si inutilisé.

### App-B2 — Le label « Regenerate » n'est jamais traduit (`ui/widgets/chat_display.py:404`)
```python
reg_text = tr("regenerate") if "regenerate" in tr("ready") else "Regenerate"
```
La condition `"regenerate" in tr("ready")` est absurde (cherche la sous-chaîne « regenerate » dans
la traduction de la clé `ready` → quasi toujours `False`) → on tombe **toujours** sur l'anglais en
dur `"Regenerate"`, l'i18n est contournée pour ce bouton. → `reg_text = tr("regenerate")`.

---

## 🏛️ ARCHITECTURE

### App-A1 — Pattern « TempTask inline » dans `db_worker.py` (dette de maintenabilité)
≥ 8 méthodes (`load_universe_meta`, `load_entities_and_rules`, `save_universe_meta`,
`save_full_universe`, `load_library`, `load_saves_async`, `load_full_universe`,
`load_global_personas`, `save_global_personas`) définissent une **sous-classe anonyme de
`LoadStatsTask`** recréée à chaque appel, juste pour réécrire `execute()` — en **ignorant** le
`save_id` de la base. Le SQL vit donc dans `db_worker` au lieu de `db_tasks.py` (le fichier l'admet :
« *Legacy/Remaining tasks (to be refactored into db_tasks.py later)* »), et certaines requêtes
dupliquent celles du moteur (`load_active_entities`, `load_full_universe` côté GUI). Pas un bug —
mais c'est l'endroit le plus fragile/illisible de la couche app. → Extraire en vraies tâches
nommées dans `db_tasks.py` (et idéalement réutiliser les lectures du moteur).

### App-A2 — `take_snapshot_async` / `SnapshotTask` orphelins (`db_worker.py:276`)
Jamais appelés (déjà relevé à l'audit moteur). Depuis le fix moteur **A2** (snapshots périodiques
dans `Session.resolve_tick`), cette voie app est définitivement morte. → Supprimer le code mort
(`take_snapshot_async` + `SnapshotTask`) ou, si on veut garder le snapshot côté app, le câbler —
mais le moteur le fait déjà, donc **suppression recommandée**.

---

## ⚡ MICRO-OPTIMISATIONS

### App-M1 — N+1 stats (`db_worker.py:359` et `:530`)
`load_entities_and_rules` et `load_full_universe` font **une requête `Entity_Stats WHERE
entity_id=?` par entité**. Remplaçable par une seule requête globale (`SELECT entity_id, stat_key,
stat_value FROM Entity_Stats`) regroupée en mémoire. (Même classe que le N+1 du moteur
`load_active_entities`.)

### App-M2 — Migrations idempotentes relancées à CHAQUE chargement
`load_full_universe` / `load_entities_and_rules` / `save_full_universe` appellent 5-6 `migrate_*`
**à chaque appel**, chacune ouvrant **sa propre connexion** (CREATE TABLE IF NOT EXISTS / ALTER…).
Après le 1ᵉʳ run elles ne font rien mais coûtent ~6 connexions/clic. → Gater par un marqueur
« migrations faites » par `db_path` (un `set` process-wide), ou migrer une seule fois à l'ouverture
de l'univers.

### App-M3 — Lecture DB sur le main thread (`ui/tabletop_view.py:610-611`)
`_on_turn_complete` appelle `get_current_time()` (sqlite) **sur le thread UI**, alors que
`main_window` proclame « ZERO backend calls » sur le main thread. Lecture minuscule (`MAX(in_game_time)`)
donc impact négligeable, mais la discipline voudrait que le worker porte le nouveau temps dans son
résultat (`ArbitratorResult` a déjà `elapsed_minutes`) ou que la `Session` l'expose.

### App-M4 — `tr()` résout la config à chaque appel
`tr()` → `_current_language()` → `load_config()` (un `os.stat` de cache mtime) **à chaque
traduction**, et l'UI appelle `tr()` des centaines de fois par rendu. Acceptable grâce au cache
mtime (stat ≈ µs), mais la langue courante pourrait être mémorisée dans `core/localization` avec
invalidation à la sauvegarde des settings. **Très mineur.**

---

## ⚠ Latent / à surveiller
- **`VectorMemory` partagé entre threads sans verrou** : embed pendant un tour (NarrativeWorker) vs
  rollback/embed sur changement de variante (VectorWorker/VectorEmbedWorker), avec init paresseuse
  non protégée. L'UI **sérialise** ces opérations (envoi désactivé pendant tour/variante/rewind),
  donc aucun bug observé — mais l'accès Chroma multi-thread n'est pas explicitement thread-safe. À
  garder en tête si un jour une opération vectorielle tourne en parallèle d'un tour.

## Ce qui est BON (pour cadrer)
- `workers/` = coquilles fines propres (`narrative`/`vector`/`regenerate`/`mini_dico`), QThreadPool +
  **registre d'annulation verrouillé** (`_ACTIVE_LOCK`), signaux cross-thread corrects (TaskSignals
  créés sur le main thread → auto-queued), anti-GC des tâches (`_active_tasks`).
- `main_window` respecte « zéro backend » (sauf le `get_current_time` noté en M3), navigation claire,
  garde anti double-tour (`set_send_enabled(False)` pendant le tour, réactivé même sur erreur).
- CLI `play.py` : propre, testable (read/out/err injectables), résolution d'univers robuste.
- `chat_display` : formats pré-cachés, `setMaximumBlockCount(1000)`, filtre de fences JSON solide
  (gère `~~~json` ET ```` ```json ````), images HTTP en cache async.
- La classe « connexion sqlite non fermée » est **déjà corrigée** (TICKET-071, branche Windows).
