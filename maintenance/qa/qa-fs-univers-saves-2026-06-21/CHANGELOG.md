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

## Findings reportés (non corrigés ici → PENDING)
- **TICKET-087** : `universes/Myria/.axiom-cache/universe.db` **commité bien que gitignoré**, schéma
  périmé (pré-`fired_turn_id`) ; `compile_universe` ne le reconstruit pas (hash source inchangé).
  Sans impact utilisateur (l'installateur bundled exclut le cache → recompile propre) mais incohérent.
- **TICKET-088** : `fork_save` ne copie pas Facts/Observations/Mental_Models/Snapshots/Modifier_Snapshots.
- **TICKET-089** : `package._RUNTIME_TABLES` (purge cache d'archive) omet les tables living.
- **TICKET-090** : `paths` sans `get_universes_dir()` ; `UNIVERSES_DIR` figé à l'import (isolation
  asymétrique vs saves/vector).
