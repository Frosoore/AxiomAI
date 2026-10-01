# CHANGELOG — Vérification, Audit Fonctionnel et Déconnexion Complète des Mods

## 2026-10-01 — Audit et Déconnexion Complète

### Déconnexion Stricte du Core
- `axiom/arbitrator.py` :
  - `step_1_gather_context` : conditionne l'interrogation de la mémoire vivante à `has_living_memory = (self.kernel_registry is None or self.kernel_registry.has_service("living_memory"))`. Si désactivé, `ctx.rag_chunks` reste vierge et la base n'est pas interrogée.
  - `step_4_parse_response` : conditionne la progression temporelle à `has_time_mod = (self.kernel_registry is None or self.kernel_registry.has_service("time"))`. Si désactivé, `ctx.elapsed_minutes = 0` et `ctx.new_time = ctx.total_mins` sans appel au LLM Timekeeper ni calcul de pace defaults. Supporte les champs `elapsed_minutes` et `time_elapsed_minutes`.
  - `step_5_arbitrate_rules` : supprime le fallback de mutation en dur lorsque le kernel registry est présent (`if self.kernel_registry is None:` uniquement). Si `axiom.world` est désactivé, le core n'exécute pas de règles ou d'arbitrage fantôme.
  - Suppression de la méthode morte `_apply_inventory_change` (anciennes lignes 1955-2014).
- `axiom/session.py` :
  - Remplacement de la liste statique des 12 mods par `bootstrap_all_mods(config=cfg)`, permettant le chargement dynamique et ordonné selon le DAG de tous les mods installés (`axiom.sillytavern`, `axiom.help_system`, community mods, etc.).
  - Ajout du paramètre `cfg: Any | None = None` dans `Session.__init__`.
  - Déconnexion stricte de `VectorMemory` : n'instancie plus `VectorMemory` en fallback quand `kernel_registry` est actif mais que le service `rag` est absent.
  - Conditionne l'appel de `ensure_stat_dynamics` à `is_mod_enabled("core.stat_dynamics", cfg)`.
- `axiom/kernel/loader.py` :
  - Support direct de `config.disabled_mods` en complément de `config.mod_settings` dans `is_mod_enabled()`.
- `axiom/kernel/registry.py` :
  - Ajout de la méthode utilitaire `has_service(service_name: str) -> bool`.
- `main_web.py` :
  - Initialisation de tous les mods au démarrage du serveur Web (`bootstrap_all_mods()`).
  - Conditionne le catch-up de la mémoire vivante à `is_mod_enabled("axiom.living_memory", _cfg)`.
  - `reset_living_memory_buffer()` ne retombe plus sur l'accumulateur headless si le mod `axiom.living_memory` est absent.
  - Correction de `/api/store/install` pour respecter le paramètre `dest` et ne plus écraser le répertoire local `mods/`.

### Effectivité Fonctionnelle des Mods
- `community.survival` :
  - Conversion du mod factice/placebo en mod actif et opérant :
    - Déclaration et enregistrement des hooks réels `axiom.step:gather_context` et `axiom.step:after_step`.
    - Contribution au slot `axiom.turn:prompt_sections` avec `build_survival_prompt_section` (guidelines de survie, fatigue, hydratation, faim avec priorité `depth: 35`).
    - Consignation automatique d'un événement de fatigue dans la Timeline (`write_batch.timeline_entries`) lors d'efforts prolongés (`elapsed_minutes >= 120`).
    - Re-packaging de `dist/mods/community.survival-0.1.0.axmod` et mise à jour de son empreinte SHA-256 dans `dist/mods/store_index.json`.
- `axiom.cli` :
  - Déclaration explicite du service `cli_play` dans `mod.toml` sous `[contributes] services = ["cli_play"]` pour correspondre à son implémentation.
- `axiom.turn` :
  - Prise en charge des clés `text` et `content` dans les contributions de sections de prompt.

### Tests Automatisés
- Création de `tests/test_mods_decoupling_and_effectivity.py` couvrant :
  - La déconnexion stricte de `axiom.world` (pas de mutations ni règles appliquées quand désactivé).
  - La déconnexion de `axiom.time` (zéro progression de temps quand désactivé).
  - La déconnexion de `axiom.living_memory` (pas d'injection de faits ni requêtes DB quand désactivé).
  - La déconnexion de `axiom.rag` et `core.stat_dynamics` dans `Session`.
  - L'effectivité réelle de `community.survival` (prompt section et tracking d'effort).
  - L'absence de mods placebo/vides parmi tous les mods installés.
- 157/157 tests mods & kernel validés avec succès.

### Contrôle et Effectivité des Mods d'Interface (axiom.ui.qt, axiom.ui.web, axiom.cli)
- `main.py` :
  - Gating effectif avant lancement : vérifie `is_mod_enabled("axiom.ui.qt", cfg)`. Si désactivé, affiche une erreur claire avec orientation (`axiom mod enable axiom.ui.qt` ou `python main_web.py`), notifie par `QMessageBox.critical` (si display disponible) et quitte proprement avec code 1.
- `ui/mods_dialog.py` & `mods/axiom.ui.qt/ui/mods_dialog.py` :
  - Lors de la désactivation de `axiom.ui.qt` depuis l'interface Qt en cours d'exécution, affiche un dialogue de confirmation explicite (`QMessageBox.question`). En cas d'acceptation, enregistre la configuration et ferme l'application via `QApplication.quit()`.
- `main_web.py` :
  - `run_server()` vérifie `is_mod_enabled("axiom.ui.web", cfg)` avant de démarrer l'écoute HTTP.
- `axiom/cli/play.py` :
  - `run_play()` vérifie `is_mod_enabled("axiom.cli", cfg)` avant de lancer la session interactive textuelle.
- `mods/axiom.ui.qt/ui/constants_sidebar.py` & `settings_dialog.py` :
  - Support de l'instanciation de classes `QWidget` contribuées via les slots `axiom.ui.qt:sidebar_widget` et `axiom.ui.qt:settings_tab` sans créer de doublons avec les onglets built-in existants.
- `core/locales/*.toml` :
  - Ajout des clés `mods_disable_active_ui_title` et `mods_disable_active_ui_prompt` dans les 10 langues supportées avec préservation des placeholders `{mod_name}` et `{mod_id}`.
- `tests/test_ui_mods_and_cli.py` :
  - Ajout de 3 nouveaux tests : refus de démarrage si mod d'interface désactivé, confirmation/fermeture lors de la désactivation in-app dans `ModsDialog`, et instanciation de classes widgets via slots.

### Suppression des Doublons et Shims Résiduels de Mods
- Suppression des shims de compatibilité résiduels devenus obsolètes dans `/ui` :
  - `ui/widgets/inventory_view.py` (remplacé définitivement par `mods/axiom.inventory/ui/inventory_view.py`).
  - `ui/widgets/timeline_view.py` (remplacé définitivement par `mods/axiom.time/ui/timeline_view.py`).
  - `ui/widgets/mental_models_widget.py` (remplacé définitivement par `mods/axiom.living_memory/ui/mental_models_widget.py`).
  - `ui/memory_browser.py` (remplacé définitivement par `mods/axiom.living_memory/ui/memory_browser.py`).
- Suppression du doublon orphelin non maintenu dans `axiom.ui.qt` :
  - `mods/axiom.ui.qt/ui/memory_browser.py` (471 lignes de doublon historique supprimées au profit de `mods.axiom.living_memory.ui.memory_browser`).
- Mise à jour des imports des appelants vers l'emplacement canonique du mod :
  - `mods/axiom.ui.qt/ui/tabletop_view.py` : importation de `MemoryBrowserDialog` depuis `mods.axiom.living_memory.ui.memory_browser`.
  - `tests/test_memory_browser.py` : importation depuis `mods.axiom.living_memory.ui.memory_browser`.
- Nettoyage des caches `__pycache__` associés.
- Suite complète de tests validée : 1 179 tests passés avec succès (0 échec).

### Consolidation Intégrale de l'UI Desktop et Suppression Définitive du Dossier `/ui`
- **Autonomie complète de `axiom.help_system`** :
  - Intégration de la logique de découplage `is_help_system_enabled()` directement dans `mods/axiom.help_system/ui/help_system.py` et `help_dialogs.py`.
  - Quand `axiom.help_system` est désactivé, `doc()` retourne immédiatement le widget d'origine sans attachement de tooltip, `doc_tab()` no-op, les fonctions de recherche/audit retournent des conteneurs vides, et les dialogues (`ExplainPageDialog`, `DocDirectoryDialog`, `QuickTourDialog`) ne s'ouvrent pas.
  - Suppression des doublons orphelins `mods/axiom.ui.qt/ui/help_system.py` et `mods/axiom.ui.qt/ui/help_dialogs.py`.
- **Découplage interne strict de `mods/axiom.ui.qt/ui/`** :
  - Conversion de l'ensemble des imports internes de l'interface bureau vers des imports relatifs (`from .widgets...`, `from .hub_view...`) ou vers les modules canoniques des mods concernés (`from mods.axiom.help_system...`).
  - Zéro import résiduel vers `ui.` dans `mods/axiom.ui.qt/ui/`.
- **Éradication totale du dossier `/ui`** :
  - Tous les composants graphiques natifs (vues, widgets, dialogues, gestionnaire d'ambiance) résident désormais sous `mods/axiom.ui.qt/ui/`.
  - Suppression de l'intégralité des fichiers Python et répertoires sous `/home/frosoore/Projets/AxiomAI/ui` (0 fichier résiduel, dossier supprimé).
- **Redirection des appelants et outillages** :
  - `main.py` : importation de `MainWindow` et `maybe_warn_missing_runtime` depuis `mods.axiom.ui.qt.ui.*`.
  - `debug/startup_check.py` : vérification au démarrage de `mods.axiom.ui.qt.ui.main_window`.
  - `tools/diagnostic.py` & `tools/doc_check.py` : importation depuis `mods.axiom.ui.qt.ui.*` et `mods.axiom.help_system.ui.*`.
  - `mods/__init__.py` : ajout de `spec.has_location = True` dans `_DottedModFinder` pour garantir que l'attribut `__file__` est systématiquement renseigné sur tous les modules chargés dynamiquement depuis `mods/`.
  - 18 fichiers de tests mis à jour (`test_help_system.py`, `test_help_system_mod.py`, `test_settings_dialog.py`, `test_phase6.py`, `test_runtime_check.py`, `test_saves_sorting.py`, `test_scheduled_events_editor.py`, `test_ui_mods_and_cli.py`, `test_mods_dialog_ui.py`, `test_mod_ui_deactivation.py`, `test_sillytavern_mod.py`, `test_ambiance_manager.py`, etc.).
- **Validation** :
  - Suite de tests complète validée : **1 189 tests passés à 100% (0 échec)**.

