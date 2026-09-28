# TODO — Phase 0f : Découpage modulaire du Tour (process_turn)

- [x] Créer `TurnContext` dans `axiom/arbitrator.py` (ou `axiom/turn_context.py`)
- [x] Découper `ArbitratorEngine.process_turn` en 6 étapes modulaires :
  - [x] `step_1_gather_context(self, ctx: TurnContext) -> None`
  - [x] `step_2_build_prompt(self, ctx: TurnContext) -> None`
  - [x] `step_3_execute_inference(self, ctx: TurnContext, stream_cb=None, cancel_event=None) -> None`
  - [x] `step_4_parse_response(self, ctx: TurnContext) -> None`
  - [x] `step_5_arbitrate_rules(self, ctx: TurnContext) -> None`
  - [x] `step_6_stage_mutations(self, ctx: TurnContext) -> None`
- [x] Orchestrer `process_turn` via le pipeline des 6 étapes
- [x] Vérifier parité stricte avec `tests/test_golden_step.py` et `tests/test_arbitrator.py`
