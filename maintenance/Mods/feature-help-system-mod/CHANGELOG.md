# CHANGELOG — Étape : Feature Aide intégrée & Infobulles en Mod (`axiom.help_system`)

## [1.0.0] - 2026-09-30

### Ajouté
- **Mod officiel `axiom.help_system`** dans `mods/axiom.help_system/` :
  - Manifeste `mod.toml` avec `provides = ["help_system", "tooltips", "inapp_documentation"]`.
  - Service `HelpSystemService` enregistré dans `KernelRegistry` sous la clé `help_system` (`main.py`).
  - Implémentation canonique complète dans `mods/axiom.help_system/ui/help_system.py` (registres statiques `PAGES`, `STUDIO_TAB_PAGES`, `SETTINGS_TAB_PAGES`, `TOUR_STEPS`, `DETAILS`, moteur `tooltip_html`, filtre d'événements `_TooltipGate`, rechargement de langue, outil `audit_undocumented`).
  - Implémentation canonique des 3 dialogues et du bouton d'aide dans `mods/axiom.help_system/ui/help_dialogs.py` (`ExplainPageDialog`, `DocDirectoryDialog`, `QuickTourDialog`, `make_help_button`).
  - Traduction du mod dans les 10 langues officielles d'Axiom AI dans `mods/axiom.help_system/locales/` (`en.json`, `fr.json`, `de.json`, `es.json`, `it.json`, `ja.json`, `ko.json`, `pt.json`, `ru.json`, `zh.json`).
  - Archive officielle `dist/mods/axiom.help_system-1.0.0.axmod` packagée et indexée avec son hash SHA-256 dans `dist/mods/store_index.json`.

### Modifié
- **Détachement total du noyau (`ui/help_system.py` et `ui/help_dialogs.py`)** :
  - `ui/help_system.py` et `ui/help_dialogs.py` allégés en adaptateurs inertes (*zero-overhead shims*) :
    - Si le mod est actif : délégation transparente vers `mods.axiom.help_system`.
    - Si le mod est inactif : détachement total, `doc()` et `doc_tab()` renvoient immédiatement le composant sans lui assigner d'infobulle ni retenir de référence, `tooltips_enabled()` renvoie `False`, `install_tooltip_gate()` n'installe aucun filtre sur `QApplication`.
    - `make_help_button()` renvoie un bouton masqué et inerte.
- **Intégration dynamique Qt (`MainWindow`, `HubView`, `SetupView`, `TabletopView`, `CreatorStudioView`)** :
  - Bascule dynamique de la visibilité des boutons « Information » (`self._help_btn`) lors de l'appel à `update_mod_visibility(config)`.
  - Masquage / désactivation des actions d'aide (`_explain_action` F1, `_directory_action`, `_tour_action`) dans `MainWindow`.
  - Court-circuitage de la visite guidée au premier démarrage si le mod est coupé.
- **Interface Web SPA (`web/app.js`)** :
  - Conditionnement de `applyDocTooltips()` à l'état actif du mod `axiom.help_system`.
  - Masquage des actions d'aide du menu Web (`btn-menu-explain`, `btn-menu-help-directory`, `btn-menu-tour`) si le mod est désactivé.

### Tests
- Création de la suite de tests automatisés dédiée `tests/test_help_system_mod.py` (7 tests couvrant manifeste, 10 langues, service, détachement total, masquage vues Qt, actions menu MainWindow, intégrité archive et store).
- Validation complète de non-régression : 1 172 tests pytest exécutés et validés (100% au vert).
