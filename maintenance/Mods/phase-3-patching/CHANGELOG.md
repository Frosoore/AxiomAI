# CHANGELOG — Phase 3 : Le Système de Patches Outillés

## [Phase 3] - 2026-09-27

### Ajouts

- **Moteur de Trampolines & Gestionnaire de Patches (`axiom/kernel/patcher.py`)** :
  - `PatchType` : Modes d'interception `BEFORE` (altération des arguments ou court-circuit), `AFTER` (altération du résultat), `AROUND` (enveloppement en oignon de l'appel).
  - `PatchRecord` : Structure de suivi associant le mod demandeur, la cible qualifiée, le type, le handler et la priorité.
  - `ShortCircuit` : Sentinelle permettant d'interrompre immédiatement la chaîne d'exécution depuis un patch `BEFORE` et de renvoyer une valeur de substitution.
  - `@patchable(target_name)` : Décorateur créant un trampoline stable, routant dynamiquement vers la chaîne de patches actifs sans surcharge à vide.
  - Trampoline de secours par substitution de bytecode (`__code__` swapping) : Pour toute fonction non décorée par `@patchable`, génération d'un code objet sans variables libres et substitution de `func.__code__`, conservant strictement `id(func)` pour les imports statiques (`from module import func`).
  - Gel par Step (§6.2.3) : `step_patch_freeze()` et `PatchingDuringStepError` garantissant qu'aucun patch ne peut être injecté ou retiré au cours d'un tour en vol.

- **Intégration à `ModContext` (`axiom/kernel/context.py`)** :
  - `ctx.patch(target, patch_type, handler, priority=100)` : Enregistrement réversible et tracé de patches.
  - `ctx.cleanup()` : Dépilement automatique de tous les patches du mod et restauration du bytecode original des fonctions non décorées (Règle D11).

- **Outils d'Inspection et de Validation CLI (`axiom/cli/mods_cmd.py`)** :
  - `axiom mods patches` : Inspection visuelle de la pile de patches actifs ou déclarés (Règle D13).
  - `axiom mod validate <path>` : Validation statique d'un manifeste et vérification de la résolubilité des cibles déclarées dans `[contributes.patches]`.

- **Suite de tests dédiée (`tests/test_patching_system.py`)** :
  - 6 tests unitaires et d'intégration validant les 3 modes, le court-circuit, le swapping `__code__`, la réversibilité absolue, la concurrence multi-mod par priorité et le gel d'exécution.

### Modifications & Découplages

- **Mod `axiom.turn` (`mods/axiom.turn/main.py`)** :
  - Enveloppement de `on_execute_step` par `step_patch_freeze()` pour figer la pile de patches durant toute la résolution du tour.
  - Réempaquetage de `dist/mods/axiom.turn.axmod`.
- **Noyau (`axiom/kernel/__init__.py`)** :
  - Export public des primitives de patching (`patchable`, `PatchType`, `PatchRecord`, `ShortCircuit`, `PatchingDuringStepError`, `register_patch`, `remove_patch`, `step_patch_freeze`).
