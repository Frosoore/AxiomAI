# TICKET-001 — Rework tests : lisibilité, couverture, organisation

Décision session 2026-05-23 (option 1 SANS suppression) :
- Renommage auto-documentant + docstrings sur `tests/`.
- Migration des `debug/test_*.py` **utiles** vers `tests/` (copie, pas de suppression).
- Aucune suppression : marquer les doublons avec `DEPRECATED.md` (cf. règles TICKET-003).
- Vérifier chaque fichier, zéro supposition sur le fonctionnement du code.
- Lancer les tests après chaque fichier, garder vert.

## Lot A — docstrings + noms (tests/) — ✅ TERMINÉ
- [x] test_chat_buffer.py
- [x] test_db_worker_atomic.py
- [x] test_db_worker_inventory_timeline.py
- [x] test_lore_persistence.py
- [x] test_persona_global.py
- [x] test_session.py
- [x] test_schema.py
- [x] test_config.py
- [x] test_event_sourcing.py
- [x] test_hardcore_worker.py
- [x] test_llm_base.py
- [x] test_ollama_client.py
- [x] test_gemini_client.py
- [x] test_rules_engine.py
- [x] test_modifier_processor.py
- [x] test_checkpoint.py
- [x] test_chronicler.py
- [x] test_arbitrator.py
- [x] test_vector_memory.py
- [x] test_prompt_builder.py
- [x] test_phase6.py
- [x] test_ambiance_manager.py (déjà docstringé, vérifié)

## Lot B — migration debug/ → tests/ — ✅ TERMINÉ (zéro suppression)
- [x] Audit des 8 debug/test_*.py (→ `debug/DEPRECATED.md`)
- [x] `tests/test_localization.py` (migré de debug/test_translations.py)
- [x] `tests/test_universe_meta.py` (migré de debug/test_db_logic.py)
- [x] DEPRECATED.md sur debug/ (doublons + outils manuels, rien supprimé)

## Vérif finale
- [x] `pytest tests/` : 347 passed, échecs/erreurs uniquement pré-existants connus
- [ ] Feu vert utilisateur avant commit
</content>
