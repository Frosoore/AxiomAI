# TODO — Modèles mentaux (Hindsight §7.8, TICKET-082 partiel)

Port de la **dernière** feature Hindsight retenue : les *modèles mentaux* = une fiche
synthétique vivante par personnage / par monde, au-dessus de la hiérarchie
croyances → faits → chunks. Refresh LLM périodique (mode Vivant), rollback turn-keyed.
Décision user (2026-06-19) : **modèles mentaux SEULS** (7.9 directives et 7.5 temporel
laissés fermés — redondants / peu pertinents).

## Moteur
- [x] `schema.py` : table `Mental_Models` + index + `ensure_mental_models_table` + listes.
- [x] `axiom/mental_models.py` : stockage (`MentalModel`, `upsert_mental_model`,
      `get_mental_models`, `count_mental_models`, `stale_subjects`) + rollback turn-keyed.
- [x] `axiom/reflect.py` : génération LLM d'un résumé par sujet (graceful → "").
- [x] `config.py` : `memory_mental_models_enabled` + `memory_mental_models_active`.
- [x] `checkpoint.py` : rollback des modèles dans la transaction de rewind.
- [x] `savestore.py` : `Mental_Models` dans l'export `.axiomsave`.
- [x] `arbitrator.py` : `_fetch_relevant_mental_models` + injection en tête (`Profile:`).
- [x] `workers/fact_worker.py` : refresh des sujets touchés + stale après consolidation.

## App / doc
- [x] Toggle GUI « Profils vivants » (grisé hors croyances) + i18n ×10 (+ doc intégrée).
- [x] Onglet « Profils » dans le memory browser (+ i18n ×10).
- [x] Doc Sphinx EN + FR (guide mémoire + API autodoc ; builds -W EXIT 0).

## Validation
- [x] tests neufs verts : `test_mental_models.py` (19), `test_reflect.py`,
      `test_fact_worker.py` (+2). Périmètre touché : **244 passed**.
- [x] `i18n_check` 732/732 ×10 OK ; `doc_check` 288 OK.
- [x] Sphinx EN + FR strict (-W) EXIT 0.
- [ ] suite complète (segfault Qt connu = TICKET-067) — sous-périmètre vert.
