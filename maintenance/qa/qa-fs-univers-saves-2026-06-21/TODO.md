# TODO — QA système fichiers / univers / saves (2026-06-21)

Contrôle qualité de bout en bout du système Universe-as-Code + saves + packaging.

## Vérifications (faites)
- [x] Suites `test_universe_as_code / universe_meta / savestore / saves_editing / packaging / dev_hotreload / bundled_universes` → 139 verts.
- [x] E2E réel sur Myria : compile → pack `.axiom` → unpack (v2) → create_save → list → duplicate → pack_save `.axiomsave` → unpack_save (re-id). Tout fonctionnel.
- [x] Audit dérive « listes de colonnes vs schéma » (`savestore._DEFINITION_COPY` / `_RUNTIME_COPY`).

## Correctifs (faits)
- [x] **BUG A** : `savestore._RUNTIME_COPY` ne copiait pas `fired_turn_id` (Fired_Scheduled_Events) → perdu à l'extraction/export d'une save embarquée legacy (`extract_save`/`pack_save`).
- [x] **BUG B** : `saves.fork_save` insérait `Fired_Scheduled_Events (save_id, event_id)` sans `fired_turn_id` → perdu au fork (et donc à `duplicate_save` d'une save embarquée).
- [x] Test de garde anti-dérive : les listes de colonnes de `savestore` doivent matcher le schéma vivant.

## Findings reportés (PENDING, non corrigés ici)
- [ ] Cache compilé `universes/Myria/.axiom-cache/` **commité alors que gitignoré** + schéma périmé (pré-`fired_turn_id`). Recompile jamais déclenché (hash source inchangé). → `git rm --cached`.
- [ ] `fork_save` ne copie pas Facts/Observations/Mental_Models/Snapshots/Modifier_Snapshots (mémoire living + snapshots de rewind perdus au fork d'une save embarquée).
- [ ] `package._RUNTIME_TABLES` (purge cache d'archive) omet Facts/Observations/Mental_Models.
- [ ] `paths` : pas de `get_universes_dir()`, `UNIVERSES_DIR` figé à l'import (non sensible à `AXIOM_DATA_DIR`/`configure`) alors que saves/vector le sont → isolation asymétrique.
