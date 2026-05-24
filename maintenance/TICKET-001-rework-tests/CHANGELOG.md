# CHANGELOG — TICKET-001

## Session 2026-05-23

Décision utilisateur : option 1 SANS suppression (cf. TODO.md). Renommage
auto-documentant + docstrings sur `tests/`, migration des `debug/test_*.py`
utiles (copie, pas de suppression ; DEPRECATED.md sur les doublons).
Vérification systématique : tests relancés après chaque fichier, restés verts.

### Lot A — docstrings + noms (tests/)
Les noms de tests étaient déjà en grande majorité auto-documentants (classes par
feature, méthodes descriptives). Le gros du travail = ajout de docstrings
concises (condition → résultat attendu), zéro risque logique, + quelques
modules/classes. Renommages ciblés là où le nom seul était ambigu (fichiers
mono-test : `test_load_full_universe_signals` →
`test_load_full_universe_emits_every_table_signal_with_data`, etc.).

Fichiers traités (tests relancés, verts) :
- test_chat_buffer.py (2) — module docstring + 2 renommés/docstrings
- test_db_worker_atomic.py (1) — renommé + docstrings
- test_lore_persistence.py (1) — renommé + docstrings
- test_persona_global.py (1) — renommé + docstrings (⚠ test pré-existant en échec
  sur arbre vierge, cf. liste TICKET-003 ; non causé par ce ticket)
- test_db_worker_inventory_timeline.py (2) — renommés + docstrings
- test_session.py (7) — docstrings (noms déjà excellents)
- test_schema.py (15) — docstrings
- test_config.py (14) — docstrings
- test_event_sourcing.py (23) — docstrings (inclut TestUpdateStateCache de TICKET-002)
- test_hardcore_worker.py (7) — docstrings
- test_llm_base.py (19) — docstrings
- test_ollama_client.py (20) — docstrings
- test_gemini_client.py (20) — docstrings
- test_rules_engine.py (25→41 avec paramétrage) — docstrings
- test_modifier_processor.py (20) — docstrings
- test_checkpoint.py (13) — docstrings
- test_chronicler.py (18) — docstrings + suppression d'une ligne morte dans
  `test_fires_at_exactly_interval` (assignée puis écrasée immédiatement, vérifiée morte)

### Découverte (déjà notée) → TICKET-006
test_chronicler confirme que le Chronicler émet des events `chronicler_update`
(non matérialisés par `_apply_event`). Cf. PENDING.md TICKET-006.

Fichiers restants traités (suite, tests verts) :
- test_arbitrator.py (22) — docstrings
- test_vector_memory.py (23) — docstrings
- test_prompt_builder.py (48) — docstrings
- test_phase6.py (27) — docstrings ; les 6 tests `_sync_current_form` restent en échec PRÉ-EXISTANT (TICKET-003)

(Note : la ligne morte retirée était dans test_chronicler.py
`test_fires_at_exactly_interval`, assignée puis écrasée immédiatement.)
- test_ambiance_manager.py (5) — déjà docstringé, noms OK ; erreurs pytest-qt PRÉ-EXISTANTES

**Lot A terminé : 22 fichiers tests/ couverts.**

### Lot B — migration debug/ → tests/ (copie, zéro suppression)
Audit des 8 `debug/test_*.py` (cf. `debug/DEPRECATED.md`). Couverture **unique et
testable sur du vrai code** migrée en pytest :
- `debug/test_translations.py` → **`tests/test_localization.py`** (8 tests) —
  comble un trou : la localisation n'avait AUCune couverture tests/.
- `debug/test_db_logic.py` → **`tests/test_universe_meta.py`** (2 tests) —
  round-trip des params LLM dans Universe_Meta, isolé via tmp_path.

Non migrés (doublons / valeur faible / interactifs) : documentés dans
`debug/DEPRECATED.md`. **Rien supprimé** — suppression reportée à TICKET-003.

### Vérification finale
`pytest tests/` : **347 passed**, 7 failed + 5 errors — TOUS pré-existants et connus
(persona_global ; 6× phase6 `_sync_current_form` ; 5× ambiance pytest-qt absent).
Aucune régression introduite par TICKET-001.
</content>
