# TICKET-028 — GUI de gestion des saves — TODO

Demande utilisateur 2026-06-09 (cf. `maintenance/PENDING.md` § TICKET-028).
Le moteur existe (`axiom/savestore.py`, `axiom/saves.py`) : il manque le Qt.

- [x] Moteur : `axiom.savestore.duplicate_save` (« save manuelle » : copie ré-identifiée
      pour une save séparée — garde le modèle 1 save = 1 fichier ; fork legacy pour une embarquée)
- [x] Moteur : `axiom.saves.diff_save_states` (état édité − état d'origine → patch de correction,
      pour n'apposer que les changements réels en `manual_edit`)
- [x] Fix latent : `DeleteSaveTask` / `RenameSaveTask` tapaient la base UNIVERS → no-op silencieux
      sur les saves séparées (la ligne `Saves` vit dans le fichier de save) — résolution savestore
- [x] Tâches Qt : Pack (.axiomsave), Unpack (+ relance force si cross-univers), Duplicate,
      ExportSaveState (texte TOML), EditSaveState (diff + correction en place)
- [x] `DbWorker` : signaux + méthodes de dispatch correspondants
- [x] `ui/setup_view.py` : barre de boutons sous la liste des saves
      (Importer… / Exporter… / Dupliquer / Renommer / Éditer… / Supprimer),
      menu contextuel enrichi, dialogue d'édition du `save_state.toml`,
      note « sauvegarde continue » (pas de bouton Sauvegarder : rien à sauver)
- [x] `database/backup_manager.py` : checkpoint WAL avant copie → backup en UN fichier ;
      absorption des sidecars `-wal`/`-shm` historiques dans `auto_backups/`
- [x] Localisation : nouvelles clés EN + FR (fallback EN pour les autres langues)
- [x] Tests : duplicate_save, diff_save_states, backup sans sidecars
- [ ] Validation GUI réelle par l'utilisateur (hors périmètre agent)
