# DOC — Mod Aide intégrée & Infobulles (`axiom.help_system`)

## 1. Périmètre & Analyse d'Impact

Cette étape transforme la documentation intégrée et le système d'infobulles au survol en un mod officiel activable / désactivable (`axiom.help_system`).

### Éléments constitutifs du système existant :
1. **Infobulles enrichies au survol (pop-ups)** :
   - Fonction `doc(widget, ref)` et `doc_tab(tab_widget, index, ref)` dans `ui/help_system.py`.
   - Registre statique `PAGES`, `STUDIO_TAB_PAGES`, `SETTINGS_TAB_PAGES`, `SETTINGS_GENERAL_PAGE`.
   - Filtre d'événements `_TooltipGate` (`install_tooltip_gate`) interceptant `QEvent.ToolTip`.
   - `retranslate_tooltips()` assurant le rafraîchissement au changement de langue.
   - Clés `doc_*` dans `core/locales/*.toml` (10 langues).
2. **Bouton « Information »** :
   - `make_help_button(page, parent=None)` dans `ui/help_dialogs.py` créant le bouton libellé `tr("information")` avec l'infobulle `tr("explain_page_btn")`.
   - Utilisé dans `HubView`, `SetupView`, `TabletopView`, et `CreatorStudioView` (où il suit dynamiquement l'onglet actif).
3. **Dialogues d'aide** :
   - `ExplainPageDialog` : explication complète de la page courante et de ses éléments.
   - `DocDirectoryDialog` : annuaire de documentation global avec barre de recherche et arborescence.
   - `QuickTourDialog` : visite guidée en 5 étapes.
4. **Menus et raccourcis clavier (`MainWindow`)** :
   - Menu Aide : « Expliquer cette page » (raccourci F1), « Annuaire de la documentation », « Visite guidée ».
   - Lancement automatique de la visite guidée au premier démarrage (`_check_first_launch`).
5. **Interface Web SPA** :
   - Attributs `data-doc` dans `web/index.html`.
   - Fonction `applyDocTooltips()` dans `web/app.js` appliquant les titres au survol.

---

## 2. Comportement Cible (Actif vs Inactif)

| Composant | Mod Actif (`enabled: true`) | Mod Inactif (`enabled: false`) |
|---|---|---|
| **Infobulles au survol** | Affichées normalement au survol de chaque bouton/champ documenté. | Entièrement masquées/silenciées par `_TooltipGate` (aucun pop-up au survol). |
| **Bouton « Information »** | Visible et fonctionnel dans chaque vue (Hub, Setup, Tabletop, Studio). | Masqué (`setVisible(False)`) sur toutes les vues. |
| **Menu Aide & Raccourci F1** | Actions d'explication de page (F1), d'annuaire et de visite guidée visibles et actives. | Actions masquées / désactivées, raccourci F1 inopérant. |
| **Visite guidée 1er lancement** | Proposée si premier lancement. | Ignorée au démarrage. |
| **Interface Web** | Infobulles `data-doc` actives. | Infobulles `data-doc` supprimées / désactivées. |
| **Rétrocompatibilité code** | Les appels `doc()` et `doc_tab()` restent valides et sans effet néfaste même si le mod est coupé. | Aucun crash ; l'audit de couverture `audit_undocumented` reste fonctionnel. |

---

## 3. Plan d'Architecture & Stratégie de Test

1. **Encapsulation complète dans le mod officiel** : `mods/axiom.help_system/`
   - Le mod contient **tout le code** de la fonctionnalité :
     - `mod.toml` avec `provides = ["help_system", "tooltips", "inapp_documentation"]`.
     - `main.py` déclarant et enregistrant le service `help_system` dans le registre de noyau via `ctx.register_service`.
     - `ui/help_system.py` : implémentation canonique complète (registres `PAGES`, `STUDIO_TAB_PAGES`, `SETTINGS_TAB_PAGES`, `TOUR_STEPS`, `DETAILS`, moteur `tooltip_html`, filtre `_TooltipGate`, rechargement de langue, outil `audit_undocumented`).
     - `ui/help_dialogs.py` : implémentation canonique des 3 dialogues (`ExplainPageDialog`, `DocDirectoryDialog`, `QuickTourDialog`) et de la fabrique de bouton `make_help_button`.
     - `locales/` : 10 fichiers de traduction JSON officiels (`en.json`, `fr.json`, `de.json`, `es.json`, `it.json`, `ja.json`, `ko.json`, `pt.json`, `ru.json`, `zh.json`).
2. **Détachement total du noyau (`ui/help_system.py` et `ui/help_dialogs.py`)** :
   - Le noyau ne contient plus aucune implémentation en dur ni dictionnaire de pages.
   - Les fichiers `ui/help_system.py` et `ui/help_dialogs.py` servent d'adaptateur découplé (*zero overhead*) :
     - Si le mod est **activé** : délégation directe à l'implémentation située dans `mods.axiom.help_system`.
     - Si le mod est **désactivé** : détachement total.
       - `doc(widget, ref)` et `doc_tab(tabs, idx, ref)` sont des no-ops stricts retournant immédiatement le widget sans `setToolTip` ni rétention en mémoire.
       - `install_tooltip_gate(app)` n'installe aucun filtre d'événements Qt sur l'application.
       - `make_help_button` renvoie un bouton inerte masqué.
       - `MainWindow` désactive/masque les actions F1, Annuaire et Tour.
3. **Suite de tests dédiée** (`tests/test_help_system_mod.py`) :
   - Validation du chargement du mod, du registre de service et des 10 langues.
   - Test du détachement total quand inactif (`doc()` n'associe pas d'infobulle, aucun filtre d'événement sur l'application, aucun pop-up au survol).
   - Test du masquage/affichage des boutons « Information » sur les 4 vues principales.
   - Test de désactivation des actions du menu Aide dans `MainWindow`.
   - Test de conservation de l'intégrité de la suite existante `tests/test_help_system.py` quand le mod est actif.

