# Documentation — Phase 1 : Le Cœur du Chargeur de Mods (axiom/kernel)

## Objectif
Implémenter le chargeur et ordonnanceur de mods dans `axiom/kernel` :
1. **Manifeste déclaratif (`axiom/kernel/manifest.py`)** : Lecture et validation stricte de `mod.toml` (depuis un dossier ou archive `.axmod` ZIP) sans aucune exécution de code Python.
2. **Résolution topologique (`axiom/kernel/resolver.py`)** : Calcul du Load Order stable pondéré par les préférences utilisateur, gestion des dépendances obligatoires/optionnelles, détection des cycles (`CyclicDependencyError`) et des conflits.
3. **Registre du noyau (`axiom/kernel/registry.py`)** : Gestion des points d'extension officiels (hooks et slots), avec isolation étanche des exceptions pour qu'un mod défaillant ne fasse jamais planter le noyau.
4. **Interface d'isolation (`axiom/kernel/context.py`)** : Fourniture de `ModContext` à `init(ctx)` pour le scoping, l'accès sécurisé à `mod_settings` et le désenregistrement automatique total (`cleanup()`).
