# TICKET-029 — Creator Studio : onglet « Fichiers » — TODO

Demande utilisateur 2026-06-09 (cf. `maintenance/PENDING.md` § TICKET-029).
Base en place : source = vérité (TICKET-027), `refresh_definition` in-place, `axiom dev`.

- [x] Moteur : `axiom.library.convert_flat_db_to_folder` — .db plat → univers-dossier
      (décompile la définition, extrait les saves embarquées vers `saves/<clé>/` en les
      reliant à la nouvelle source, compile le cache, original conservé en `.db.bak`)
- [x] Tâches Qt : `RefreshDefinitionTask` (source → db in-place), `ConvertFlatDbTask`
- [x] `DbWorker` : signaux `definition_refreshed` / `universe_converted` + dispatch
- [x] Widget `ui/widgets/universe_files_tab.py` : arbo des fichiers texte (TOML/MD…),
      éditeur monospace, Enregistrer → écrit le fichier + `refresh_definition` →
      la vue Studio classique se recharge ; cas .db plat → proposition de conversion
- [x] `ui/creator_studio_view.py` : onglet « Fichiers » (dernier onglet), refresh à
      l'activation de l'onglet (la source bouge après chaque save Studio, TICKET-027)
- [x] Localisation EN + FR
- [x] Tests : conversion .db plat (saves embarquées migrées + reliées), smoke widget
- [ ] Validation GUI réelle par l'utilisateur (hors périmètre agent)
