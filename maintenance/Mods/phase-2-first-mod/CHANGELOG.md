# CHANGELOG — Phase 2 : Extraction du premier mod officiel (core.stat_dynamics)

## 2026-09-27
- Extraction du premier mod officiel `core.stat_dynamics` au format `.axmod` dans `mods/core.stat_dynamics/` :
  - Manifeste `mod.toml` avec déclaration des hooks `axiom.turn:arbitrate_stats`, `axiom.step:after_step` et politique de persistance `storage.modifiers`.
  - Code exécutable `main.py` implémentant le point d'entrée `init(ctx: ModContext)`.
- Implémentation du runtime loader de mod dans `axiom/kernel/loader.py` :
  - `load_mod_from_dir` et `load_mod_from_archive` pour charger un mod depuis un dossier ou une archive `.axmod` (ZIP).
  - Export public dans `axiom/kernel`.
- Découplage du moteur dans `axiom/arbitrator.py` et `axiom/session.py` :
  - `ArbitratorEngine` reçoit `kernel_registry` et dispatche `axiom.turn:arbitrate_stats` dans `step_5_arbitrate_rules`.
  - `ArbitratorEngine` dispatche `axiom.step:after_step` dans `step_6_stage_mutations` pour la gestion des modificateurs.
  - `TurnContext` transporte `db_path` et expose la propriété `in_game_minutes_elapsed`.
  - `GameSession` accepte et propage `kernel_registry`.
  - Absence de tout import statique de `axiom.stat_dynamics` par le noyau.
- Implémentation de la commande CLI `axiom mod pack` dans `axiom/cli/mods_cmd.py` :
  - Validation du manifeste `mod.toml`.
  - Compression ZIP filtrée vers `dist/mods/core.stat_dynamics-1.0.0.axmod`.
- Création de la suite de tests `tests/test_stat_dynamics_mod.py` (7/7 tests passants) :
  - Conformité du manifeste déclaratif.
  - Chargement depuis répertoire et archive `.axmod`.
  - Calcul de guérison / décrément passif via `TurnContext`.
  - Gestion des événements de crash et vidage des modificateurs.
  - Respect de la Règle D11 (réversibilité totale sans plantage à la désactivation).
- Validation globale des suites de tests (`test_golden_step.py`, `test_kernel_loader.py`, `test_arbitrator.py`, `test_packaging.py`).
