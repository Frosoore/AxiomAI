# TICKET-028 — GUI de gestion des saves — DOC

Panneau « Sauvegardes » dans l'écran Setup (onglet existant) : Exporter/Importer `.axiomsave`,
Dupliquer (= save manuelle), Renommer, Éditer (`save_state.toml` dans un dialogue), Supprimer.
Toute la logique vit dans `axiom.savestore` / `axiom.saves` ; le Qt n'est qu'un câblage
(tâches dans `workers/db_tasks.py`, dispatch `workers/db_worker.py`).

L'édition n'applique que le **diff** entre le TOML exporté et le TOML édité, en events
`manual_edit` append-only (rewind préservé). En passant : backups `auto_backups/` en un seul
fichier (checkpoint WAL avant copie) et fix Delete/Rename sur les saves séparées.
