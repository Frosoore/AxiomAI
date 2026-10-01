# DOC — Mod SillyTavern & Internationalisation Exhaustive

## 1. Objectif
- Extraire la fonctionnalité d'importation de fiches SillyTavern (PNG avec métadonnées base64 `chara` et JSON) de la logique monolithique pour en faire un mod officiel modulaire et découplable : `axiom.sillytavern`.
- Permettre d'activer ou désactiver ce mod à la demande (via le gestionnaire de mods GUI Qt `ModsDialog`, l'UI Web ou la CLI `axiom mod disable axiom.sillytavern`).
- Quand le mod est actif : le bouton d'importation apparaît dans le Hub (Qt et Web), et les requêtes d'importation sont traitées normalement.
- Quand le mod est inactif : le bouton d'importation est masqué dans le Hub (Qt et Web), et toute tentative d'import via l'API ou worker renvoie une erreur explicite signalant que le mod est désactivé.
- Fournir les traductions complètes du mod dans les 10 langues supportées par Axiom AI (`en`, `fr`, `de`, `es`, `it`, `ja`, `ko`, `pt`, `ru`, `zh`), et s'assurer que tous les mods existants dans `mods/` disposent des 10 langues.

## 2. Architecture Technique
- **Emplacement du mod :** `mods/axiom.sillytavern/`
  - `mod.toml` : ID `axiom.sillytavern`, version 1.0.0, API 1, provides `["sillytavern_import", "card_importer"]`.
  - `main.py` : exporte le service `sillytavern`, fournit la fonction `parse_st_card(filepath)`, expose les types supportés.
  - `locales/*.json` : traductions 10 langues.
- **Délégation `core/st_parser.py` :** conserve la rétrocompatibilité tout en se reposant sur l'implémentation du mod.
- **Intégration UI Qt :**
  - `HubView.update_mod_visibility(config=None)` : contrôle `self._import_st_btn.setVisible(is_mod_enabled("axiom.sillytavern", config))`.
  - Câblé sur `MainWindow.update_mod_visibility(config=None)`.
- **Intégration UI Web :**
  - `/api/universes/import-st` : valide `is_mod_enabled("axiom.sillytavern", cfg)` et rejette la requête si inactif (HTTP 403).
  - `/api/mods` / `refreshHub()` : contrôle la visibilité de `hub-import-st-btn`.
