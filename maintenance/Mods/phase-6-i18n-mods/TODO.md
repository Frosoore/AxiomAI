# TODO — Phase 6 : Traduction complète des mods & Fallback multilingue

> Référence : `maintenance/Mods/DOC.md` (§5 format `.axmod`, `locales/`).

## 1. Moteur & Noyau (`axiom/kernel/`)
- [x] Mettre à jour `ModManifest` (`axiom/kernel/manifest.py`) pour inclure `locales: dict[str, dict[str, str]]`
- [x] Ajouter les méthodes `manifest.localized_name(lang: str | None = None) -> str` et `manifest.localized_description(lang: str | None = None) -> str`
- [x] Implémenter la chaîne de fallback : Langue demandée → Anglais (`en`) → Première locale disponible du mod → Défaut du manifeste (`mod.toml`)
- [x] Mettre à jour `parse_manifest_file` pour charger automatiquement les fichiers `locales/*.json` (et `*.toml`) du répertoire du mod
- [x] Mettre à jour `load_manifest_from_archive` pour extraire et charger les fichiers `locales/*.json` (et `*.toml`) depuis une archive `.axmod`
- [x] Mettre à jour `axiom/kernel/loader.py` pour enregistrer automatiquement les dictionnaires de `manifest.locales` dans le slot `axiom.kernel:locales`

## 2. Intégration UI & CLI
- [x] Adapter `ui/mods_dialog.py` et `mods/axiom.ui.qt/ui/mods_dialog.py` pour utiliser `localized_name()` et `localized_description()`
- [x] Adapter `main_web.py` pour exposer `localized_name` et `localized_description`
- [x] Adapter `axiom/cli/mods_cmd.py` pour afficher les libellés traduits

## 3. Traduction intégrale des 12 mods officiels (10 langues)
- [x] `mods/axiom.cli/locales/` : 10 fichiers (`en`, `fr`, `es`, `de`, `it`, `pt`, `ru`, `zh`, `ja`, `ko`)
- [x] `mods/axiom.illustrations/locales/` : 10 fichiers
- [x] `mods/axiom.inventory/locales/` : 10 fichiers
- [x] `mods/axiom.living_memory/locales/` : 10 fichiers
- [x] `mods/axiom.providers/locales/` : 10 fichiers
- [x] `mods/axiom.rag/locales/` : 10 fichiers
- [x] `mods/axiom.time/locales/` : 10 fichiers
- [x] `mods/axiom.turn/locales/` : 10 fichiers
- [x] `mods/axiom.ui.qt/locales/` : 10 fichiers
- [x] `mods/axiom.ui.web/locales/` : 10 fichiers
- [x] `mods/axiom.world/locales/` : 10 fichiers
- [x] `mods/core.stat_dynamics/locales/` : 10 fichiers

## 4. Tests et Validation
- [x] Créer `tests/test_mod_localization.py` validant :
  - La présence et la validité des 10 langues pour tous les mods officiels
  - La résolution multilingue exacte via `localized_name()` et `localized_description()`
  - Le fallback gracieux pour les mods communautaires partiels (ex. `community.survival`)
  - L'injection dans le slot `axiom.kernel:locales` et l'accès via `tr()`
  - Le round-trip d'archive `.axmod` avec packaging des locales
- [x] Exécution complète de la suite de tests (1 146 tests verts, zéro régression)
