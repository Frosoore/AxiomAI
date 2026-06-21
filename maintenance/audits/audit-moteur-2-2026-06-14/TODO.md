# TODO — Audit moteur (2ᵉ passe, 2026-06-14)

Suite de `audit-moteur-2026-06-14` (qui couvrait B1-B3 / A1-A3 / M1-M5). Cette passe
traite ce que le 1ᵉʳ audit n'avait pas vu : **index DB manquants** + hygiène des
`except` silencieux. Pas de commit sans feu vert.

## Perf — index base de données (priorité haute) — ✅ FAIT
- [x] `schema.py` : 0 index sur 20 tables → requêtes par-tour en `SCAN` (full scan).
- [x] Ajouter `_DDL_INDEXES` + exécution dans `create_universe_db` (nouvelles DB).
- [x] `migrate_indexes(db_path)` idempotent pour les DB **existantes**.
- [x] Câbler `migrate_indexes` dans `db_helpers.create_new_save` + `load_saves`.

## Hygiène — `except Exception: pass` silencieux — ✅ FAIT
- [x] `logger.debug(..., exc_info=True)` ajouté : `arbitrator.py`, `session.py` ×2,
      `config.py`, `cli/play.py` (repli inchangé, simple trace).
- [x] Laissés justifiés : `memory.py:57`, `backends/universal.py:135`.

## CI — ✅ FAIT (passe précédente)
- [x] `tests.yml` : cache HF + pré-fetch offline-first avec retry → règle les 429.

## Recheck `arbitrator.py` + `prompts.py` (demandé) — ✅ FAIT
- [x] `prompts.py` relu intégralement → RAS (fonctions pures, rien à corriger).
- [x] `arbitrator.py` relu → bug latent corrigé : `_validate_inventory_change`
      coerce `quantity` (JSON LLM) défensivement, rejette non-entier / `<= 0`
      au lieu de crasher le tour (+9 tests, chemin auparavant non testé).
- [x] Doc Sphinx : autodoc régénère depuis docstrings ; aucune page hand-written
      fausse ; `sphinx-build -W` re-vérifié OK (« La compilation a réussi »).

## Validation — ✅ FAIT
- [x] Suite complète verte : **788 passed** (781 + 7), 0 échec.
- [x] `EXPLAIN QUERY PLAN` re-vérifié : SCAN → SEARCH USING INDEX.
- [x] `migrate_indexes` testé idempotent + tolérant table absente.
- [x] Aucune régression (résultats de requêtes inchangés, index = perf pure).
- [x] Segfault batch ambiance = TICKET-067 (teardown Qt), confirmé sans rapport
      (passe en isolation : 7/7).
