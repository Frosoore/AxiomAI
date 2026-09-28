# TODO — Phase 1 : Le Cœur du Chargeur de Mods (axiom/kernel)

- [x] Créer le package `axiom/kernel/`
- [x] Implémenter le parseur de manifeste déclaratif `axiom/kernel/manifest.py`
  - [x] Validation stricte (`id` namespacé `author.name`, `version` SemVer, `axiom_api`, etc.)
  - [x] Extraction en mémoire depuis répertoire ou archive `.axmod` (ZIP) sans exécution de code
- [x] Implémenter la résolution topologique du Load Order `axiom/kernel/resolver.py`
  - [x] Ordonnancement sous contraintes (DAG, `after`, `before`)
  - [x] Détection des dépendances manquantes et désactivation avec rapport
  - [x] Détection des cycles (`CyclicDependencyError`)
  - [x] Détection des conflits déclarés
  - [x] Tri topologique stable pondéré par l'ordre utilisateur
- [x] Implémenter le registre du noyau `axiom/kernel/registry.py`
  - [x] Gestion des hooks et slots (Exclusif, Chaîne, Collecte)
  - [x] Isolation des exceptions lors de l'appel d'un hook défaillant
- [x] Implémenter `ModContext` dans `axiom/kernel/context.py`
  - [x] Inscription via contexte (`register_hook`, `contribute_slot`)
  - [x] Désinscription automatique totale via `cleanup()` (Règle D11)
- [x] Créer la suite de tests unitaires `tests/test_kernel_loader.py`
- [x] Validation complète avec `tests/test_golden_step.py` et pureté headless
