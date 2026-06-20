# B4 — Fin du portage moteur — CHANGELOG

## 2026-06-10 — portage complet, table « non migré » vidée (session Claude)

**Moteur (zéro Qt) :**
- `axiom/db_helpers.py` : + `create_player_entity(db_path, name, description)` — entité
  joueur `origin='runtime'` (jamais touchée par le hot reload), id dérivé du nom,
  désambiguïsation sur collision, stats par défaut (10) depuis `Stat_Definitions`.
  **Fix au passage** : l'ancienne `CreatePlayerEntityTask` avait un corps entièrement
  DUPLIQUÉ (pré-existant dans HEAD) dont la seconde définition — celle active —
  utilisait `datetime` sans import → NameError latent sur nom vide ou collision.
- `axiom/regenerate.py` (nouveau) : `regenerate_variant(...)` (historique event-sourcé →
  messages LLM, prompt narratif sans tool-call, stream avec stop sequences, plafond de
  tokens par verbosité), `append_variant` (payload multiverse, conversion des payloads
  legacy `{"text": ...}`), `history_to_messages`. + méthode **`Session.regenerate_variant`**
  (la destination « méthode Session » annoncée par la table).
- `axiom/mini_dico.py` (nouveau) : `answer_lore_question(...)` — RAG scopé save + prompt
  encyclopédique + appel LLM, repli si réponse vide.
- `axiom/multiplayer.py` (nouveau) : `PlayerAction` (dataclass sans Qt) + `ActionQueue` —
  FIFO de résolution séquentielle des tours (pur threading, callbacks on_token/
  on_complete/on_error/on_status, boucle insensible à l'échec d'un tour).

**Coquilles Qt (API et signaux inchangés pour le GUI) :**
- `workers/db_tasks.py::CreatePlayerEntityTask`, `workers/regenerate_worker.py`,
  `workers/mini_dico_worker.py` → délèguent au moteur.
- `core/multiplayer_queue.py` : `ArbitratorWorker` fait tourner `ActionQueue.run_loop`
  sur son QThread et traduit les callbacks en signaux ; `PlayerAction` ré-exporté
  (l'import `from core.multiplayer_queue import ...` du tabletop ne change pas).
- `workers/chronicler_worker.py` : constat — déjà coquille sans logique ET **jamais
  instancié** (le Chronicler tourne dans le moteur depuis le Pilier 5). Ligne retirée de
  la table, annotation morte `_chronicler_worker` retirée du tabletop. Suppression du
  fichier : en attente du feu vert utilisateur.

**Doc :** table « non migré » d'ARCHITECTURE.md **vidée** (placeholder + note de portage).

**Tests :** `tests/test_engine_port_b4.py` (nouveau, 10) : entité joueur (stats/origin,
collision, nom vide = l'ancien NameError), régénération (variante ajoutée + active +
prompt sans tool-call + streaming, payload legacy converti, tour sans narratif),
mini-dico (RAG → prompt → réponse, repli), ActionQueue (FIFO séquentiel multi-joueurs,
erreur d'un tour n'arrête pas la boucle) — synchronisation déterministe (pas de course
sur stop()). Suites vertes : session/db_worker_atomic/narrative_worker/phase6/b4 (53),
garde-fous collab + startup_check, smoke offscreen de compatibilité d'API des coquilles.

## 2026-06-10 (suite) — suppression du worker mort + fix du chemin de mort hardcore

- **`workers/chronicler_worker.py` supprimé** (feu vert utilisateur) — jamais instancié.
- **Régression évitée** (merci la question utilisateur « t'as bien tout mis à jour dans le
  GUI ? ») : `ui/tabletop_hardcore.py::_start_hardcore_deletion` listait encore
  `self._chronicler_worker` (attribut retiré du tabletop en B4) → AttributeError sur le
  chemin de mort hardcore. Retiré de la liste + docstring du mixin.
- **Fix latent pré-existant sur les mêmes lignes** : la même boucle appelait
  `worker.isRunning()` sur `self._db_worker`, qui est un `DbWorker(QObject)` à pool de
  tâches — pas un QThread → AttributeError garantie dès qu'une mort hardcore survenait.
  Garde `hasattr(worker, "isRunning")` ajoutée.
- Re-validation : smoke offscreen des attributs du chemin hardcore, suites
  hardcore/phase6/b4/session/narrative (59), garde-fous collab + startup_check.
