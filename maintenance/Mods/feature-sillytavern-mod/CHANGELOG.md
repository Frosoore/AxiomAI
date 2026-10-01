# CHANGELOG — Étape : Feature SillyTavern en Mod

## [2026-09-30] - Implémentation du Mod SillyTavern & Internationalisation

### Ajouté
- **Mod officiel `axiom.sillytavern`** :
  - Création du répertoire `mods/axiom.sillytavern/` avec manifeste `mod.toml` (v1.0.0, API 1, provides `sillytavern_import`, `card_importer`).
  - Implémentation du module `main.py` : export du service public `sillytavern`, de la classe `SillyTavernService`, et de la fonction `parse_st_card(filepath)`.
  - Intégration complète des traductions dans les 10 langues d'Axiom AI (`locales/{en,fr,de,es,it,ja,ko,pt,ru,zh}.json`).
  - Packaging de l'archive officielle `dist/mods/axiom.sillytavern-1.0.0.axmod` avec calcul et vérification d'empreinte SHA-256 (`4d749a175056...`).
  - Enregistrement dans le catalogue distant simulé `dist/mods/store_index.json`.

### Modifié
- **Délégation et rétrocompatibilité `core/st_parser.py`** :
  - `parse_st_card` délègue dynamiquement à `mods.axiom.sillytavern.main.parse_st_card` tout en conservant le fallback autonome.
- **Interface graphique bureau Qt** (`ui/hub_view.py`, `mods/axiom.ui.qt/ui/hub_view.py`, `ui/main_window.py`, `ui/mods_dialog.py`) :
  - Ajout de la méthode `HubView.update_mod_visibility(config=None)` : bascule la visibilité du bouton `_import_st_btn` selon `is_mod_enabled("axiom.sillytavern", cfg)`.
  - Câblage de `MainWindow.update_mod_visibility` pour mettre à jour automatiquement `_hub_view`.
  - Notification automatique de `_hub_view` lors du basculement d'un mod dans le dialogue `ModsDialog`.
  - Guard défensif dans `_on_import_st_clicked` et `ImportExportWorker._run_import_st` pour interdire l'importation si le mod est désactivé.
- **Interface Web SPA** (`main_web.py` et `web/app.js`) :
  - Guard sur la route `POST /api/universes/import-st` (JSON et upload multipart) renvoyant HTTP 403 si `axiom.sillytavern` est inactif.
  - Fonction `refreshHub()` dans `web/app.js` vérifiant l'état du mod via `/api/mods` et masquant le bouton `#hub-import-st-btn` lorsque désactivé.

### Tests
- Création de la suite dédiée `tests/test_sillytavern_mod.py` (7 tests unitaires et d'intégration : manifeste, découverte, 10 langues, service, UI Qt, worker, API Web, intégrité store).
- Exécution de l'ensemble de la suite de tests (1 165 tests au vert à 100 %).
