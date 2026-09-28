# CHANGELOG — Phase 0b : Unification de la fin de tour et assainissement des UIs

## 2026-09-26
- **Living Memory Headless (`axiom/living_memory.py`)** :
  - Création de la classe `LivingMemoryAccumulator` et de la fabrique globale `get_living_memory_accumulator()`.
  - Encapsulation de l'accumulation par session, gestion du compteur d'intervalle, déclenchement du worker de distillation asynchrone headless et extraction synchrone `run_extract_now()`.
- **Tour 0 atomique et universel (`axiom/savestore.py`)** :
  - Mise à jour de `create_save` pour accepter `setup_answers: dict[str, Any] | None = None`.
  - Enregistrement des événements `setup_answer`.
  - Résolution de `first_message` (variantes `---VARIANT---`, regex substitution insensible à la casse des tags `@key`).
  - Insertion atomique de l'événement `narrative_text` du tour 0 dans `Event_Log`.
- **Pipeline post-narration centralisé (`axiom/session.py`)** :
  - Ajout de `_post_turn_pipeline(self, result: ArbitratorResult)` dans `Session` appelé par `resolve_tick()`.
  - Centralisation des métadonnées de tour (`last_updated`, `_last_lore_hits`, `_last_game_state_tag`) et déclenchement de la living memory.
  - Ajout de `get_state_snapshot()`, `get_memory_snapshot()`, `resolve_verbosity()`, `resolve_player_entity_id()`, `run_living_memory_extract_now()`, et `is_player_death_triggered()`.
  - Formatage de temps headless avec `axiom.time_system` garantissant zéro import de `core`/`ui`/`PySide6`.
- **Assainissement de l'API Web (`main_web.py`)** :
  - Suppression des variables globales ad-hoc (`_FACT_PENDING`, `_FACT_TURN_COUNTER`, `_FACT_WORKER_LOCK`, `_FACT_WORKER_BUSY`).
  - Suppression de `_spawn_living_memory_job`.
  - Allègement de `execute_session_turn`, `build_session_snapshot`, `build_memory_snapshot`, `run_living_memory_extract_now`, `reset_living_memory_buffer`, `resolve_player_entity_id`, et `resolve_session_verbosity` en contrôleurs API déléguant directement à `Session`.
  - Suppression du retraitement SQL ad-hoc dans `/api/saves/create` et `/api/session/start`.
- **Assainissement de l'interface Qt (`ui/setup_view.py`, `ui/tabletop_view.py`)** :
  - Passage de `setup_answers` à `create_save` dans `ui/setup_view.py`.
  - Suppression de la double accumulation / distillation de facts dans `ui/tabletop_view.py`.
  - Délégation de `extract_facts_now` vers `LivingMemoryAccumulator.run_extract_now`.
- **Tests & Conformité** :
  - Suite de validation cible : `tests/test_golden_step.py`, `tests/test_engine_headless.py`, `tests/test_web_server.py` : 50/50 passants (100 %).
  - Suite `test_packaging.py` : 15/15 passants (conformité headless validée, 0 import interdit).
