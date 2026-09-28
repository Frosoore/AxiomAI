# CHANGELOG — Phase 1 : Le Cœur du Chargeur de Mods (axiom/kernel)

## 2026-09-27
- Création du package `axiom/kernel/` constituant le noyau modulaire d'Axiom AI.
- Implémentation du parseur de manifeste déclaratif `axiom/kernel/manifest.py` :
  - Support de `mod.toml` (fichiers locaux ou archives `.axmod` ZIP) sans exécution de code.
  - Validation stricte des identifiants `author.name`, versions SemVer, compatibilité `axiom_api`.
  - Modèles déclaratifs : `ModManifest`, `ModDependency`, `ModOrdering`, `ModContributes`.
- Implémentation du résolveur de dépendances et de load order `axiom/kernel/resolver.py` :
  - Construction du DAG et tri topologique stable (Kahn) pondéré par l'ordre utilisateur (analogie Skyrim).
  - Détection et élagage des dépendances manquantes (marquage propre dans `ResolutionReport.disabled_mods`).
  - Détection rigoureuse des cycles de dépendances (`CyclicDependencyError`).
  - Détection des conflits déclarés entre mods (`ConflictError`).
- Implémentation du registre de noyau `axiom/kernel/registry.py` :
  - Gestion des slots avec politiques d'exécution : `EXCLUSIVE`, `CHAIN`, `COLLECT`.
  - Isolation des exceptions sur l'appel des hooks : toute exception d'un mod défaillant est interceptée et loguée sans interrompre le moteur.
- Implémentation du gestionnaire de cycle de vie `axiom/kernel/context.py` :
  - Objet `ModContext` fournissant l'API sécurisée au mod (`register_hook`, `contribute_slot`, configuration isolée).
  - Nettoyage systématique et désinscription totale lors de `cleanup()` (Règle D11).
- Création de la suite de tests complète `tests/test_kernel_loader.py` (13/13 tests passants).
- Vérification de la compatibilité ascendante avec les suites de tests existantes (`test_golden_step.py`, `test_arbitrator.py`, `test_schema.py`, `test_config.py`, `test_packaging.py`).

