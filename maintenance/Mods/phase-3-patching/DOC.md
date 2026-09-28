# DOC — Phase 3 : Le Système de Patches Outillés

## 1. Objectifs & Dérives ciblées

Ce jalon implémente le système officiel de patches de fonctions Python du projet Axiom AI :

* **D8 (Interdiction des mods superficiels) & §1.3 (Exigence de profondeur) :** Tout code Python interne peut être ciblé par la communauté pour altérer la logique du jeu en profondeur.
* **D9 (Les patches ne sont pas le chemin normal) :** Bien que non utilisés par les mods officiels du socle (qui privilégient hooks et slots), les patches sont dotés d'un outillage de premier ordre dans le moteur.
* **D11 (Réversibilité structurelle) :** Tout patch s'enregistre via `ctx.patch(...)` et se retire automatiquement lors de `ctx.cleanup()`, restaurant la fonction d'origine sans fuite de mémoire.
* **D13 (Visibilité totale) :** La commande `axiom mods patches` permet d'inspecter l'arbre complet des patches appliqués ou déclarés sans exécuter de code obscur.
* **Règle de concurrence (§6.2.3) :** La pile de patches est strictement figée pendant l'exécution d'un step (interdiction formelle de mutation dynamique au milieu d'un tour).

---

## 2. Architecture & Fonctionnement

### A. Décorateur `@patchable(target_name)`
Appliqué sur les fonctions internes officielles destinées à être personnalisables :
* Installe un trampoline immuable et léger.
* Si aucun patch n'est actif, délègue directement à la fonction native avec une surcharge quasi-nulle.
* Si des patches sont actifs, consulte le registre et exécute les couches ordonnées par priorité.

### B. Mécanisme de Secours par Substitution de Bytecode (`__code__` swapping)
Lorsqu'un mod tiers cible une fonction qui n'a pas été préalablement décorée avec `@patchable` :
1. Le moteur résout le module et la fonction via son chemin qualifié (`module:func` ou `module.func`).
2. Il clone la fonction originale en mémoire pour conserver sa logique d'origine.
3. Il compile un code objet sans variables libres (`co_freevars == ()`) déléguant à `patcher.dispatch_patch(target_name)`.
4. Il remplace `func.__code__` par ce nouveau code.
5. **Conséquence capitale :** L'identité mémoire de l'objet fonction (`id(func)`) reste rigoureusement inchangée. Tout module ayant importé la fonction via `from module import func` avant l'activation du patch exécutera automatiquement le trampoline sans ré-importation.
6. Émet un log explicite : `Target '{target_name}' is not marked @patchable. Applied bytecode trampoline fallback.`
7. Lors du déchargement du mod (`ctx.cleanup()`), le bytecode original est réassigné à `func.__code__`.

### C. Types d'Interception & Ordonnancement
* **`BEFORE`** : Exécuté avant la fonction cible.
  - Peut modifier les arguments en renvoyant `((new_args), {new_kwargs})`.
  - Peut court-circuiter l'exécution via `ShortCircuit(value)`, annulant l'appel à la fonction cible et aux patches suivants.
* **`AROUND`** : Enveloppe l'appel avec la signature `handler(next_func, *args, **kwargs)`.
  - S'empile en oignon déterministe selon la priorité : la plus petite valeur de priorité enveloppe les couches plus profondes.
* **`AFTER`** : Exécuté après l'appel cible et les `AROUND`. Reçoit `(result, *args, **kwargs)` et peut substituer le résultat retourné.

### D. Gel par Step (Step-level Freeze)
* Context manager `step_patch_freeze()` activé durant `on_execute_step` dans `mods/axiom.turn`.
* Toute tentative d'appel à `register_patch()`, `remove_patch()` ou `ctx.cleanup()` pendant qu'un tour est en cours lève immédiatement `PatchingDuringStepError`.

### E. Outils CLI
* `axiom mods patches` : Tableau récapitulatif des patches actifs (fonction cible, type, mod ID, priorité).
* `axiom mod validate <path>` : Analyse statique du manifeste `mod.toml` et vérification de la résolubilité dynamique de toutes les cibles listées dans `[contributes.patches]`.

---

## 3. Validation

La suite `tests/test_patching_system.py` et la suite globale de non-régression (57 tests à 100 % au vert) valident :
1. Les 3 modes d'interception avec court-circuit.
2. La préservation de l'identité d'objet lors du swapping de bytecode.
3. La réversibilité absolue après `ctx.cleanup()`.
4. L'ordonnancement déterministe multi-mods par priorité.
5. La protection contre les mutations de fonction en cours de tour.
6. L'inspection et la validation CLI.
