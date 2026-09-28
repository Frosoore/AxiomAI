# Documentation — Phase 0f : Découpage modulaire du Tour (process_turn)

## Objectif
Découper le corps monolithique de `ArbitratorEngine.process_turn` en un pipeline séquentiel d'étapes nommées et testables, s'appuyant sur un `TurnContext` transportant l'état du pas :
1. `step_1_gather_context` : Collecte d'état (stats, mémoire vectorielle, contexte spatial, entités).
2. `step_2_build_prompt` : Construction du prompt modulaire.
3. `step_3_execute_inference` : Exécution LLM (streaming & gestion de l'annulation).
4. `step_4_parse_response` : Extraction du texte narratif et parsing JSON du tool-call.
5. `step_5_arbitrate_rules` : Validation des changements de stats, inventaire, règles dynamiques.
6. `step_6_stage_mutations` : Staging des mutations dans `TurnWriteBatch` (Phase 0d).
