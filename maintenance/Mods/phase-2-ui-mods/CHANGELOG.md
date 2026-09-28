# CHANGELOG — Phase 2 : Extraction des Interfaces Utilisateurs (axiom.ui.web, axiom.ui.qt, axiom.cli) & Extensions transversales

## [Phase 2 - Fin] - 2026-09-27

### Ajouts

- **Mod officiel d'Interface Web : `axiom.ui.web` (`mods/axiom.ui.web/`)** :
  - `mod.toml` : Manifeste avec `id = "axiom.ui.web"`, version `1.0.0`, slots déclarés `axiom.ui.web:side_panel`, `axiom.ui.web:settings_tab`, `axiom.ui.web:action_button`.
  - `main.py` : Service public `"web_ui"` pour piloter le serveur HTTP et agréger dynamiquement les onglets et composants injectés par d'autres mods.
  - Empaquetage dans `dist/mods/axiom.ui.web.axmod`.

- **Mod officiel d'Interface Desktop Qt : `axiom.ui.qt` (`mods/axiom.ui.qt/`)** :
  - `mod.toml` : Manifeste avec `id = "axiom.ui.qt"`, version `1.0.0`, slots déclarés `axiom.ui.qt:sidebar_widget`, `axiom.ui.qt:settings_tab`.
  - `main.py` : Service public `"qt_ui"` fournissant le point d'entrée `launch_gui` et l'agrégation des widgets de barre latérale et onglets de réglages.
  - Empaquetage dans `dist/mods/axiom.ui.qt.axmod`.

- **Mod officiel d'Interface Terminal CLI : `axiom.cli` (`mods/axiom.cli/`)** :
  - `mod.toml` : Manifeste avec `id = "axiom.cli"`, version `1.0.0`, `provides = ["user_interface"]`.
  - `main.py` : Service public `"cli_play"` exécutant la boucle textuelle de jeu dans le terminal.
  - Empaquetage dans `dist/mods/axiom.cli.axmod`.

- **Slots transversaux dans le Noyau (`axiom/kernel/registry.py`)** :
  - Déclaration native de `axiom.kernel:locales` (`rule = "collect"`) pour l'internationalisation multi-mods.
  - Déclaration native de `axiom.kernel:help_entries` (`rule = "collect"`) pour les fiches d'aide (F1 / tooltips).
  - Gestion automatique du registre actif global (`get_active_registry`, `set_active_registry`).

- **Intégration d'Internationalisation & d'Aide Transversale** :
  - `core/localization.py` : Fusion dynamique des tables de traduction issues de `axiom.kernel:locales` par-dessus les fichiers statiques de `core/locales/`.
  - `ui/help_system.py` : Résolution des tooltips et entrées d'aide documentées depuis `axiom.kernel:help_entries`.

- **Gestion CLI des Mods dans le Noyau (`axiom/cli/mods_cmd.py`, `axiom/cli/main.py`)** :
  - Sous-commandes `axiom mods list`, `axiom mods enable <id>`, `axiom mods disable <id>`, `axiom mods pack <dir>`.
  - Prise en charge du flag global `--safe-mode` sur `axiom`, `main.py` et `main_web.py`.
  - `axiom/kernel/loader.py` : Désactivation automatique de tout mod tiers (`is_official_mod`) en mode sans échec.

- **Suite de tests d'intégration (`tests/test_ui_mods_and_cli.py`)** :
  - `test_manifests_and_loading_ui_mods` : Chargement et services des 3 mods d'UI (dossiers et archives `.axmod`).
  - `test_web_ui_side_panel_extension` : Extension du slot `axiom.ui.web:side_panel` par un mod tiers et enrichissement du snapshot session.
  - `test_locales_slot_injection` : Injection et bascule de langue pour des clés de traduction tierces.
  - `test_help_entries_slot_injection` : Documentation contextuelle et rendu HTML de tooltips injectés par mod.
  - `test_cli_mods_management_and_safe_mode` : Validation des commandes CLI `list`/`enable`/`disable` et isolation du flag `--safe-mode`.

### Modifications & Découplages

- `main_web.py` : Injection automatique des `side_panels` dans `/api/session/start` et gestion du flag `--safe-mode`.
- `main.py` : Prise en charge du flag `--safe-mode` au démarrage.
- `axiom/session.py` : Auto-chargement enrichi avec transmission de `config` et inclusion des mods d'UI.
