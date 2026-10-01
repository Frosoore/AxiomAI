# TODO — Étape : Feature Aide intégrée & Infobulles en Mod (`axiom.help_system`)

> Référence : `maintenance/Mods/DOC.md`, TICKET-057, Demande utilisateur du 2026-09-30.
> Objectif : Transformer le système complet d'aide intégrée (infobulles au survol, bouton « Information », dialogue d'explication de page, annuaire global, visite guidée, raccourci F1) en un mod officiel activable et désactivable (`axiom.help_system`), avec traductions complètes 10 langues et tests d'intégrité sans régression.

## Tâches

- [x] 1. Documenter l'analyse d'impact initiale et le plan d'architecture (`DOC.md`).
- [x] 2. Créer le mod officiel `axiom.help_system` dans `mods/axiom.help_system/` (`mod.toml`, `main.py`).
- [x] 3. Créer les fichiers de localisation du mod dans les 10 langues d'Axiom AI (`locales/{en,fr,de,es,it,ja,ko,pt,ru,zh}.json`).
- [x] 4. Mettre en place la passerelle d'activation/désactivation dans le moteur d'infobulles (`ui/help_system.py`) :
  - Conditionner `tooltips_enabled()` à `is_mod_enabled("axiom.help_system", config)`.
  - Conditionner `tooltip_html()` et le filtre d'événements `_TooltipGate`.
- [x] 5. Mettre en place le masquage dynamique des boutons « Information » (`make_help_button`) :
  - Dans `HubView`, `SetupView`, `TabletopView`, `CreatorStudioView` via `update_mod_visibility(config)`.
- [x] 6. Câbler la désactivation dans `MainWindow` :
  - Masquer/désactiver les actions du menu Aide (« Expliquer cette page », « Annuaire de la documentation », « Visite guidée ») et le raccourci F1 lorsque le mod est désactivé.
  - Mettre à jour `update_mod_visibility(config)` pour propager à toutes les vues et menus.
- [x] 7. Câbler l'UI Web (`web/app.js` et `main_web.py`) :
  - Masquer ou vider les infobulles `[data-doc]` dans `applyDocTooltips()` si `axiom.help_system` est inactif.
- [x] 8. Enregistrer le mod dans `dist/mods/store_index.json` et packager l'archive officielle `.axmod`.
- [x] 9. Développer une suite de tests automatisés dédiée (`tests/test_help_system_mod.py`).
- [x] 10. Valider la non-régression sur l'ensemble de la suite (1 172+ tests).
