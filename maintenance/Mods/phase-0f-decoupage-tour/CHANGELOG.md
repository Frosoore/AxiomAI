# CHANGELOG — Phase 0f : Découpage modulaire du Tour (process_turn)

## 2026-09-27
- Initialisation de la phase 0f.
- Définition de la classe `TurnContext` dans `axiom/arbitrator.py` transportant l'état intermédiaire du tour (`save_id`, `step_id`/`turn_id`, `user_input`, `player_entity_id`, `verbosity`, `spatial_context`, `retrieved_memory`, `relevant_stats`, `prompt_messages`, `raw_llm_response`, `parsed_tool_call`, `write_batch`, `rejected_changes`, `triggered_rules`).
- Découpage du monolithe `process_turn` (~660 lignes) en 6 étapes nommées et isolées :
  - `step_1_gather_context(ctx)` : collecte des stats, mémoire vectorielle, contexte spatial, entités.
  - `step_2_build_prompt(ctx)` : construction modulaire du prompt avec lore, persona, règles et consignes.
  - `step_3_execute_inference(ctx, stream_cb, cancel_event)` : exécution LLM en streaming avec gestion de l'annulation.
  - `step_4_parse_response(ctx)` : extraction de la narration et parsing résilient du JSON / calcul temporel.
  - `step_5_arbitrate_rules(ctx)` : validation des changements d'état, dynamique des stats, inventaire et moteur de règles.
  - `step_6_stage_mutations(ctx)` : staging des événements, snapshots, modificateurs et commit atomique via `TurnWriteBatch`.
- Ajout de tests unitaires dédiés `TestTurnContextModularPipeline` dans `tests/test_arbitrator.py`.
- Validation 100% verte sur `tests/test_golden_step.py` (5/5) et `tests/test_arbitrator.py` (50/50).
