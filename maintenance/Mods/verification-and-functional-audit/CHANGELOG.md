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
