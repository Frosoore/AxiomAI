# TICKET-028 — GUI de gestion des saves — CHANGELOG

## 2026-06-09 — implémentation complète (session Claude)

**Moteur (zéro Qt) :**
- `axiom/savestore.py` : + `duplicate_save(universe_db, save_id, player_name=None)` —
  « save manuelle ». Save séparée : copie du fichier ré-identifiée (nouvel uuid, un seul
  `Saves` par fichier, `last_updated` rafraîchi) ; embarquée : `fork_save` legacy en place.
- `axiom/saves.py` : + `diff_save_states(before, after)` — patch de correction entre deux
  `save_state.toml` parsés (stats modifiées seulement ; inventaire modifié/ajouté/retiré
  via quantité 0 ; modifiers nouveaux uniquement). Sert au flux GUI « Éditer ».

**Workers Qt (coquilles fines) :**
- `workers/db_tasks.py` : fix **latent** — `DeleteSaveTask`/`RenameSaveTask` opéraient sur la
  base UNIVERS → no-op silencieux pour les saves séparées (§7.6). Résolution via savestore
  (delete supprime aussi le fichier quand il se vide). + 5 tâches : `PackSaveTask`,
  `UnpackSaveTask` (renvoie `{"needs_force": True}` au lieu d'une erreur si archive
  cross-univers), `DuplicateSaveTask`, `ExportSaveStateTask` (état → texte TOML),
  `EditSaveStateTask` (diff → `apply_correction`, -1 si rien à appliquer).
- `workers/db_worker.py` : signaux `save_packed/save_unpacked/save_duplicated/
  save_state_exported/save_edited` + méthodes de dispatch.

**GUI :**
- `ui/setup_view.py` : onglet Saves — note « sauvegarde continue » + barre de boutons
  Importer (.axiomsave) / Exporter / Dupliquer / Renommer / Éditer / Supprimer
  (activation selon sélection), menu contextuel enrichi, `SaveStateEditDialog`
  (éditeur monospace du save_state.toml ; seules les différences sont appliquées,
  en events `manual_edit` append-only — rewind préservé), import force après confirmation.
- `axiom/localization.py` : clés EN + FR (autres langues → fallback EN).

**Cosmétique demandée :**
- `database/backup_manager.py` : `PRAGMA wal_checkpoint(TRUNCATE)` avant copie → un backup
  = UN fichier (sidecars copiés seulement si la base est verrouillée, ancien comportement
  en secours) ; absorption des sidecars `-wal`/`-shm` des backups historiques (WAL rejoué
  dans le fichier principal, sidecars orphelins supprimés).

**Tests :** `tests/test_savestore.py` (+4 duplicate), `tests/test_saves_editing.py`
(+5 diff), `tests/test_backup_manager.py` (nouveau, 3). Suites affectées vertes :
savestore/saves_editing/backup (51), db_worker_atomic+phase6+inventory (30),
checkpoint/hardcore/ticket_fixes/universe_as_code/event_sourcing (78),
garde-fous collab (engine_headless + cli_play + startup_check). Smokes offscreen :
instanciation SetupView + chaîne complète des 5 tâches.

**Reste :** validation GUI réelle par l'utilisateur.
