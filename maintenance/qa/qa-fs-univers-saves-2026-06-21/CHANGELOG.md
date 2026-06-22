# CHANGELOG — QA système fichiers / univers / saves (2026-06-21)

## Vérification
- Suites ciblées vertes : `test_universe_as_code`, `test_universe_meta`, `test_savestore`,
  `test_saves_editing`, `test_packaging`, `test_dev_hotreload`, `test_bundled_universes`,
  `test_checkpoint` → **160 verts** (avec les 3 nouveaux tests).
- E2E réel sur l'univers vitrine **Myria** (data dir isolé) : `compile_universe` → `pack_universe`
  (`.axiom` v2) → `unpack_universe` → `create_save` → `list_saves` → `duplicate_save` → `pack_save`
  (`.axiomsave`) → `unpack_save` (ré-identification). **Tout fonctionnel de bout en bout.**

## Bugs corrigés (TICKET-086) — `fired_turn_id` perdu
Cause racine : TICKET-075 a ajouté la colonne `fired_turn_id` à `Fired_Scheduled_Events` mais deux
chemins de copie ne l'ont pas suivie → colonne retombée à `0` (défaut) → le rewind ne « dé-tire »
plus les events (`DELETE … WHERE fired_turn_id > target` ne matche jamais `0`).
- `axiom/savestore.py` : `_RUNTIME_COPY` → ajout de `fired_turn_id` (impacte `extract_save`,
  donc `pack_save`/`.axiomsave` d'une save **embarquée legacy**). Confirmé par repro (7 → 0).
- `axiom/saves.py::fork_save` : `SELECT`/`INSERT` étendus à `fired_turn_id` + `ensure_fired_event_turn_column`
  préalable (save embarquée ancienne pouvant précéder la colonne). Impacte `duplicate_save` d'une save
  embarquée.

## Test de garde anti-dérive
`tests/test_savestore.py::TestCopyListSchemaCoherence` :
- `_DEFINITION_COPY` et `_RUNTIME_COPY` doivent matcher **exactement** le schéma vivant
  (`create_universe_db`) — attrape tout futur ajout de colonne non répercuté.
- régression dédiée : `fired_turn_id` survit à `extract_save`.

## QC CI rouge (2026-06-22) — `created_at` perdu (même classe que TICKET-086)
La feature « Last Updated and Creation Date » (commit `93acf65`) a ajouté la colonne `created_at`
à la table `Saves` (`schema.py`), mais sans répercuter sur les chemins de copie → CI 3.11/3.12 rouge
sur `TestCopyListSchemaCoherence::test_runtime_copy_matches_schema` (le garde anti-dérive a fait son
job). Deux corrections :
- `axiom/savestore.py` : `_RUNTIME_COPY` table `Saves` → ajout de `created_at` (impacte `extract_save`,
  donc l'export `.axiomsave` d'une save embarquée legacy, qui sinon perdait silencieusement la date
  de création).
- `axiom/schema.py::migrate_saves_difficulty_constraint` : le rebuild `Saves_Temp` recopiait 5 colonnes
  et **écrasait `created_at` à `''`** juste après que `migrate_saves_table` l'ait backfillé
  (`created_at = last_updated`). Copie étendue à `created_at`, avec garde `PRAGMA table_info` au cas où
  la migration serait appelée seule sur un DB pré-`created_at`. Round-trip vérifié (valeur préservée).
- Suite complète verte : `953 passed`.

## QC flake i18n inter-tests (2026-06-22) — TICKET-091
Pendant la QC, `tests/test_saves_sorting.py::test_saves_sorting_by_last_updated_and_creation_date` a
flanché une fois en suite complète (vert en isolation). **Cause racine** (≠ ordre des tests :
`pytest-randomly` n'est même pas installé) : fuite de langue inter-tests.
- `tests/test_diagnostic_dialog.py::test_language_combo_switches_and_reruns` bascule le combo de langue
  du `DiagnosticDialog` sur `"ja"` (→ `set_language("ja")` en mémoire) **sans fermer le dialog** ; la
  fixture `dialog` faisait seulement `deleteLater()`. Le dialog survit donc, **son combo toujours
  connecté à `_on_language_changed`**, jusqu'à ce que la suppression différée soit traitée par la
  boucle d'évènements d'un test ultérieur → un signal parasite rejoue `set_language(...)`.
- `test_saves_sorting` asserte des libellés **en dur en anglais** (« Last Updated », « Creation Date »)
  construits via `tr()`. Sous `"ja"` (`tr('sort_last_updated')` = « 最終更新日時 ») → échec.
Corrections (deux niveaux) :
- **Racine** — `tests/test_diagnostic_dialog.py` fixture `dialog` : teardown déterministe
  (`_lang_combo.blockSignals(True)` + `reject()` → `finished`→`reload_translations()` immédiat) avant
  `deleteLater()`. Plus aucun signal de langue parasite ne survit au test.
- **Robustesse** — `tests/test_saves_sorting.py` : `set_language("en")` en tête de test (la fixture
  autouse `reset_i18n_cache` restaure après). Vérifié : le test passe **même en forçant `"ja"` avant**.
- Suite complète verte : `953 passed`. (NB : `test_vector_threading` peut segfault-flake sur cette
  machine Python 3.14/Fedora — classe TICKET-067, sans rapport, vert en isolation et hors CI 3.11/3.12.)

## Findings reportés (non corrigés ici → PENDING)
- **TICKET-087** : `universes/Myria/.axiom-cache/universe.db` **commité bien que gitignoré**, schéma
  périmé (pré-`fired_turn_id`) ; `compile_universe` ne le reconstruit pas (hash source inchangé).
  Sans impact utilisateur (l'installateur bundled exclut le cache → recompile propre) mais incohérent.
- **TICKET-088** : `fork_save` ne copie pas Facts/Observations/Mental_Models/Snapshots/Modifier_Snapshots.
- **TICKET-089** : `package._RUNTIME_TABLES` (purge cache d'archive) omet les tables living.
- **TICKET-090** : `paths` sans `get_universes_dir()` ; `UNIVERSES_DIR` figé à l'import (isolation
  asymétrique vs saves/vector).
