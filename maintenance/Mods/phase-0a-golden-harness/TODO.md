# TODO — Phase 0a : Harnais « Golden Step »

- [x] Créer `axiom/testing/golden_harness.py`
  - [x] `GoldenHarnessExhaustedError`
  - [x] `ScriptedTurnResponse`
  - [x] `ScriptedLLMBackend` (hérite de `LLMBackend`, streaming, complete, cancel_event, exhausted check)
  - [x] `SessionStateCanonicalizer` (extraction via `materialize_state`, normalisation déterministe, `diff` format Unified Diff)
- [x] Créer ébauche CLI `axiom/cli/test.py` et câbler la sous-commande `test` dans `axiom/cli/main.py`
- [x] Implémenter le scénario canonique `tests/test_golden_step.py` (T1→T10 sur univers Myria temporaire)
  - [x] T1-T3 : Mouvements spatiaux et stats
  - [x] T4-T6 : Inventaire et imbrication (`container_id`)
  - [x] T7-T8 : Modificateurs temporaires et tick du temps
  - [x] Capture état étalon $S_8$
  - [x] T9-T10 : Écriture Session_Lore
  - [x] Rewind(8) et assertion `diff == []`
  - [x] Fork(8) et assertion `diff == []`
  - [x] Pack / Unpack et assertion `diff == []`
- [x] Valider avec pytest (tests/test_golden_step.py : 100% pass)
