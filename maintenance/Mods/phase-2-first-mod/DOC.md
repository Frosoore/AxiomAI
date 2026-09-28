# DOC — Phase 2 : Extraction du premier mod officiel (core.stat_dynamics)

## 1. Objectifs & Règles d'Architecture
Cette étape valide l'architecture modulaire en extrayant un sous-système essentiel du moteur sous la forme d'un mod `.axmod` autonome :
- **Règle D1 (Le noyau qui grossit)** : Retirer du noyau ce qui peut être porté par un mod.
- **Règle D2 (Pas de privilège pour les mods officiels)** : Le mod utilise exclusivement `ModContext` (`register_hook`, configuration, slots) sans backdoor ou privilèges cachés.
- **Règle D11 (Réversibilité totale)** : Si le mod est désactivé ou absent, le noyau ne tente plus de faire décroître les modificateurs temporaires et s'exécute sans erreur (comportement passif des jauges).

## 2. Structure du Mod `core.stat_dynamics`
Localisé dans `mods/core.stat_dynamics/` :
- `mod.toml` : Manifeste déclaratif indiquant les métadonnées, hooks (`axiom.turn:arbitrate_stats`, `axiom.step:after_step`), et la politique de persistance des modificateurs.
- `main.py` : Point d'entrée standard `init(ctx: ModContext)` enregistrant les callbacks.
- `tests/test_stat_dynamics_mod.py` : Tests in-tree du mod.

## 3. Découplage Moteur
- **`ArbitratorEngine.step_5_arbitrate_rules`** : Dispatche l'étape d'arbitrage de dynamique via `self.kernel_registry.execute_hook("axiom.turn:arbitrate_stats", ctx)`.
- **`ArbitratorEngine.step_6_stage_mutations`** : Dispatche la fin de pas via `self.kernel_registry.execute_hook("axiom.step:after_step", ctx)`.
- **`ArbitratorEngine.step_2_build_prompt`** : N'injecte les consignes et notes de dynamique temporelle que si un mod a enregistré le hook `axiom.turn:arbitrate_stats` (ou en fallback legacy sans registre).

## 4. Packaging `.axmod`
La commande CLI `axiom mod pack <dir> [-o <dest>]` (implémentée dans `axiom/cli/mods_cmd.py`) permet de packager le mod :
```bash
python -m axiom.cli mod pack mods/core.stat_dynamics
```
Produit l'archive ZIP `dist/mods/core.stat_dynamics-1.0.0.axmod`.

## 5. Exécution des tests
```bash
.venv/bin/python -m pytest tests/test_golden_step.py tests/test_kernel_loader.py tests/test_stat_dynamics_mod.py -q
```
