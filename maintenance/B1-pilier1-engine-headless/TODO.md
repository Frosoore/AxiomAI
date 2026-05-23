# TODO — B1 Pilier 1 : Extraction `axiom-engine` headless (§5)

Objectif : isoler le moteur (Arbitrator, Chronicler, EventSourcing, RulesEngine,
ModifierProcessor, VectorMemory, prompts, time) dans un package `axiom/`
sans aucune dépendance Qt.

Constat vérifié (grep, 2026-05-23) :
- Modules engine déjà quasi sans Qt (seul `core/multiplayer_queue.py` importe PySide6 — HORS migration).
- `core/paths.py` et `core/logger.py` sont du pur stdlib (le doc se trompe sur « paths Qt-friendly »).
- Seule vraie fuite : `core/arbitrator.py` importe `get_current_time` / `get_time_of_day_context` depuis `workers/db_helpers.py`.
- 22 fichiers de `ui/` + `workers/` importent l'engine (périmètre Étape 2).

## Étape 1 — Créer le package `axiom/` (COPIE, app intacte) ✅
- [x] `axiom/__init__.py`
- [x] `axiom/schema.py` ← `database/schema.py`
- [x] `axiom/paths.py` ← `core/paths.py`
- [x] `axiom/logger.py` ← `core/logger.py`
- [x] `axiom/events.py` ← `database/event_sourcing.py`
- [x] `axiom/checkpoint.py` ← `database/checkpoint.py`
- [x] `axiom/modifiers.py` ← `database/modifier_processor.py`
- [x] `axiom/rules.py` ← `core/rules_engine.py`
- [x] `axiom/time_system.py` ← `core/time_system.py`
- [x] `axiom/db_helpers.py` ← `workers/db_helpers.py` (résout la fuite arbitrator)
- [x] `axiom/localization.py` ← `core/localization.py` (dép découverte : tr/fmt_num)
- [x] `axiom/presets.py` ← `database/presets.py` (dép découverte : db_helpers/config)
- [x] `axiom/backends/base.py` ← `llm_engine/base.py`
- [x] `axiom/backends/universal.py` ← `llm_engine/universal_client.py`
- [x] `axiom/backends/gemini.py` ← `llm_engine/gemini_client.py`
- [x] `axiom/backends/ollama.py` ← `llm_engine/ollama_client.py`
- [x] `axiom/backends/__init__.py`
- [x] `axiom/memory.py` ← `llm_engine/vector_memory.py`
- [x] `axiom/prompts.py` ← `llm_engine/prompt_builder.py` (split en sous-modules : étape ultérieure)
- [x] `axiom/config.py` ← `core/config.py`
- [x] `axiom/arbitrator.py` ← `core/arbitrator.py`
- [x] `axiom/chronicler.py` ← `core/chronicler.py`
- [x] Réécrire les imports internes (top-level + lazy/indentés) → `axiom.*`
- [~] `pyproject.toml` du package — REPORTÉ à l'étape de split physique (dir racine dédié)
- [x] Vérif : 19/19 modules importent sans Qt (`PySide6 chargé: False`)
- [x] Vérif : aucun `from core|database|workers|llm_engine` résiduel dans `axiom/`

## Étape 2 — Réécrire les imports de l'app (ui/ + workers/) vers `axiom.*`
- [x] Réécriture des imports dans ui/, workers/, main.py, core/multiplayer_queue.py
- [x] `core/__init__.py` vidé de ses ré-exports morts (supprime aussi le cycle d'import du hotfix A5)
- [x] Validation : 25/25 modules applicatifs importent via axiom.*, 115 tests engine passent
- [x] Réécriture des imports de tests/ et debug/ vers axiom.* (from-imports + cibles patch/string)
- [x] Tests engine relancés contre axiom.* : **314 passés** / 6 échecs pré-existants (test_phase6 `_sync_current_form`)
- [x] Suppression NON faite (choix utilisateur) → README `DEPRECATED.md` dans core/, database/, llm_engine/ + TICKET-003
- [ ] (différé) Suppression effective des anciens modules : voir TICKET-003 (conditions de validation)

Note env : pytest-qt absent → tests Qt (qtbot) en erreur de setup ; segfault torch+Qt sur run
complet ; échec test_persona_global. Tous PRÉ-EXISTANTS (tests tournent contre les anciens modules
non modifiés), sans rapport avec la bascule.

## Étape 3 — Abstraction des fuites Qt / paths — REPORTÉE / ABSORBÉE PAR L'ÉTAPE 4
- Constat : doc erroné (paths déjà headless) ; split config = risque persistance. Voir TICKET-004.
- Décision (validée) : ne bloque pas l'Étape 4 ; l'injection des chemins passera par `Session(data_dir=...)`.
- [~] Split EngineConfig/AppConfig : abandonné sauf besoin avéré (settings.json inchangé).

## Étape 4 — API publique `Session`
- [x] `axiom/session.py` : `Session.take_turn / rewind / list_checkpoints / current_stats / turn_id`
- [x] `axiom/universe.py` : `Universe.load`, `list_saves`
- [x] Exposition paresseuse `from axiom import Session, Universe` (`__getattr__`, import léger)
- [x] `tests/test_session.py` : 5 tests (Universe.load, construction, état neuf, mapping historique, variante active) — verts
- [x] Smoke test headless hors-pytest : Session/Universe OK contre vraie base, `PySide6 chargé: False`
- [ ] (suite, refacto app à part) `NarrativeWorker` réécrit en wrapper threading autour de `Session` — voir note
- [ ] (optionnel/plus tard) `axiom/cli/` : `play`, `compile`, `test_runner`

Note : l'app pilote encore l'engine en direct (ArbitratorEngine + NarrativeWorker), ce qui marche.
Faire adopter `Session` par le worker est une refacto applicative à risque de régression → reportée
(hors « no refacto hors scope »), à traiter en étape dédiée quand on voudra le mode CLI.
