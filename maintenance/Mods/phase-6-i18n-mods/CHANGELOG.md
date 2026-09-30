# CHANGELOG — Phase 6 : Traduction complète des mods & Fallback multilingue

## 2026-09-30
- **Support des traductions dans `ModManifest`** (`axiom/kernel/manifest.py`) :
  - Ajout du champ `locales: dict[str, dict[str, Any]]` dans `ModManifest`.
  - Ajout de `localized_name(lang=None)` et `localized_description(lang=None)`.
  - Implémentation de la chaîne de repli (fallback) demandée :
    1. Langue demandée (ex. `fr`, `ja`, etc.)
    2. Anglais (`en`)
    3. Première langue disponible dans le mod (pour les mods tiers ne proposant qu'une seule langue arbitraire)
    4. Valeurs par défaut du manifeste `mod.toml` (`name` et `description`).
  - Découverte automatique des fichiers `locales/*.json` et `locales/*.toml` dans `parse_manifest_file` (répertoires) et `load_manifest_from_archive` (archives `.axmod`).
  - Zéro import interdit vers `core/` dans le moteur (`axiom/`) : lecture de la langue de fallback via `axiom.config.load_config().language` pour préserver l'étanchéité headless.
- **Injection automatique dans le noyau** (`axiom/kernel/loader.py`) :
  - Dans `load_mod_from_dir` et `load_mod_from_archive`, injection automatique des dictionnaires de `manifest.locales` dans le slot officiel `axiom.kernel:locales` via `mod_ctx.contribute_slot()`.
  - Intégration transparente avec le système de nettoyage de `ModContext.cleanup()` (Règle D11).
- **Mise à jour des interfaces UI, Web et CLI** :
  - `ui/mods_dialog.py` et `mods/axiom.ui.qt/ui/mods_dialog.py` : utilisation de `localized_name()` et `localized_description()` pour le filtrage de recherche et l'affichage.
  - `main_web.py` : exposition des champs localisés dans `/api/mods`.
  - `axiom/cli/mods_cmd.py` : affichage du nom localisé dans `axiom mods list`.
- **Génération des 120 fichiers de traduction pour les 12 mods officiels** :
  - 10 langues complètes (`en`, `fr`, `es`, `de`, `it`, `pt`, `ru`, `zh`, `ja`, `ko`) pour chaque mod dans `mods/<mod_id>/locales/<lang>.json`.
  - Mods traduits : `axiom.cli`, `axiom.illustrations`, `axiom.inventory`, `axiom.living_memory`, `axiom.providers`, `axiom.rag`, `axiom.time`, `axiom.turn`, `axiom.ui.qt`, `axiom.ui.web`, `axiom.world`, `core.stat_dynamics`.
- **Traduction des libellés du gestionnaire de mods (`ui/mods_dialog.py` & `mods/axiom.ui.qt/ui/mods_dialog.py`)** :
  - Ajout de 20 nouvelles clés de traduction dans les 10 fichiers de `core/locales/*.toml` (couverture 853/853 clés vérifiée via `tools/i18n_check.py`).
  - Traduction intégrale des sections : Catégorie fonctionnelle, Systèmes fournis, Événements écoutés, Points d'extension, Dépendances, Type (.axmod / décompressé), Emplacement, Auteur et Compatibilité API.
- **Normalisation de l'auteur des mods officiels** :
  - Mise à jour de tous les `mods/*/mod.toml` avec `author = "Vanilla"`.
  - Mise à jour de l'index du store `dist/mods/store_index.json` avec `"author": "Vanilla"`.
- **Suite de tests & Validation** (`tests/test_mod_localization.py`) :
  - 9 tests unitaires vérifiant l'exhaustivité des 10 langues, la résolution localisée, le fallback communautaire partiel, le fallback sans locales, l'intégration du slot kernel, le packaging `.axmod`, la présence de `author = "Vanilla"` et la traduction des 20 libellés dans les 10 langues.
  - Exécution complète de la suite : 1 148 tests réussis avec succès, zéro régression.
