# DOC — Phase 2 : Extraction des Interfaces Utilisateurs (axiom.ui.web, axiom.ui.qt, axiom.cli) & Extensions transversales

## 1. Objectifs & Dérives ciblées

Ce jalon clôture la **Phase 2 (Extraction des features en mods officiels)** du grand chantier de modularisation d'Axiom AI :

* **D4 (Aucune interface privilégiée) :** Ni Qt, ni le Web, ni la CLI ne détiennent de logique métier non accessible aux autres. Toutes les interfaces sont devenues des mods officiels (`axiom.ui.web`, `axiom.ui.qt`, `axiom.cli`) fournissant le slot virtuel `provides = ["user_interface"]`.
* **§9 (Les interfaces sont des mods) :** Les frontends exposent des slots d'extension dédiés (`axiom.ui.web:side_panel`, `axiom.ui.qt:sidebar_widget`, `axiom.ui.web:settings_tab`, etc.) consommés par les mods de jeu (inventaire, dynamiques de personnage, etc.) sans modification des fichiers du noyau.
* **§4.1 & §4.5 (Mode sans échec & gestion CLI du noyau) :** Le noyau implémente ses propres commandes d'administration de mods (`axiom mods list/enable/disable/pack`) de manière totalement autonome (zéro dépendance à une UI). Le flag global `--safe-mode` garantit qu'en cas de crash causé par un mod tiers, le moteur redémarre avec les seuls modules officiels de confiance (`axiom.*`, `core.*`).

---

## 2. Architecture & Composants

### A. Mod d'Interface Web : `mods/axiom.ui.web/`
* **Manifeste** : Déclare les slots d'extension `"axiom.ui.web:side_panel"`, `"axiom.ui.web:settings_tab"` et `"axiom.ui.web:action_button"`.
* **Service `web_ui`** :
  - `start_server(port, background)` / `stop_server()` : Pilote le cycle de vie du serveur HTTP embarqué.
  - `get_side_panels()`, `get_settings_tabs()`, `get_action_buttons()` : Récupère les contributions des autres mods.
  - `enrich_session_snapshot(snapshot)` : Injecte les panneaux latéraux et boutons d'action dans le dictionnaire d'état de session retourné aux clients web.

### B. Mod d'Interface Bureau Qt : `mods/axiom.ui.qt/`
* **Manifeste** : Déclare les slots d'extension `"axiom.ui.qt:sidebar_widget"` et `"axiom.ui.qt:settings_tab"`.
* **Service `qt_ui`** :
  - `launch_gui(argv)` : Démarre l'application native PySide6.
  - `get_sidebar_widgets()` : Agrège les widgets de barre latérale contribués par les mods.

### C. Mod d'Interface Terminal : `mods/axiom.cli/`
* **Manifeste** : Fournit le rôle `user_interface`.
* **Service `cli_play`** :
  - `run_play(args)` et `play_loop(session, ...)` : Exécute l'aventure textuelle interactive directement dans le terminal.

### D. Slots Transversaux dans le Noyau & Intégration
* **`axiom.kernel:locales`** (`rule = "collect"`) :
  - Déclaré à l'initialisation de tout `KernelRegistry`.
  - Consommé par `core/localization.py::_load_translations()` : tout mod peut contribuer des clés de traduction pour n'importe quelle langue (`en`, `fr`, etc.), automatiquement fusionnées au dictionnaire de l'application.
* **`axiom.kernel:help_entries`** (`rule = "collect"`) :
  - Consommé par `ui/help_system.py` : permet aux mods de déclarer des entrées documentaires contextuelles consultables via F1 ou survol tooltip.

### E. Commandes CLI du Noyau & Mode Sans Échec
* **`axiom mods list`** : Scanne `mods/` et `dist/mods/`, affiche les identifiants, versions, compatibilités d'API (`v1 (OK)`) et l'état activé/désactivé.
* **`axiom mods enable <mod_id>` / `disable <mod_id>`** : Modifie de façon persistante la section `mod_settings` dans `settings.json`.
* **`--safe-mode`** :
  - Disponible sur `axiom [cmd]`, `python main.py` et `python main_web.py`.
  - Dans `axiom/kernel/loader.py`, `is_mod_enabled` vérifie `is_safe_mode()`. Si activé, tout mod ne commençant pas par `axiom.` ou `core.` est automatiquement écarté du chargement.

---

## 3. Validation

La robustesse de ce découpage est attestée par `tests/test_ui_mods_and_cli.py` et la suite de régression globale (51 tests passants à 100 %) :
1. Découverte, intégrité des manifestes et initialisation des services des 3 mods d'UI.
2. Extension dynamique du panneau latéral Web via le slot `axiom.ui.web:side_panel`.
3. Résolution multi-langue via `axiom.kernel:locales` avec bascule de langue à chaud.
4. Intégration transparente d'entrées d'aide dans le système de documentation.
5. Commandes CLI de liste/activation/désactivation et comportement du mode sans échec.
