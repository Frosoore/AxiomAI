# DOC — Phase 0a : Harnais « Golden Step »

## Objectif
Créer un banc d'essai d'intégration hermétique, reproductible et sans aucune dépendance réseau/GPU/LLM réel, capable de valider le comportement du moteur de jeu à chaque étape de la transition vers les mods.

## Composants
1. `axiom.testing.golden_harness` :
   - `GoldenHarnessExhaustedError` : Levée si le moteur demande plus de tours que prévu.
   - `ScriptedTurnResponse` : Dataclass simulant les réponses du LLM (chunks de texte, tool call JSON, délai par token).
   - `ScriptedLLMBackend` : Sous-classe de `LLMBackend` fournissant un comportement séquentiel déterministe pour `stream_tokens` et `complete`, avec gestion coopérative de `cancel_event`.
   - `SessionStateCanonicalizer` : Sérialiseur déterministe normalisant l'état complet extrait via `axiom.saves.materialize_state` (white-listing, exclusion des UUIDs volatils et timestamps, tri strict par clés) et produisant un Unified Diff via sa méthode `diff`.

2. Utilitaire CLI `axiom.cli.test` :
   - Ébauche de commande CLI `axiom test` pour lancer les validations de harnais ou inspecter un état canonique.

3. Scénario de test `tests/test_golden_step.py` :
   - Exécute une séquence de 10 tours sur Myria compilé, vérifie la parité exacte de l'état étalon $S_8$ après Rewind(8), Fork(8) et Export/Unpack.
