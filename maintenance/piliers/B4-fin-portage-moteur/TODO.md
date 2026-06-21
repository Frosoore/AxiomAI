# B4 — Fin du portage moteur (vider la table « non migré ») — TODO

Dernières lignes de la table d'ARCHITECTURE.md : porter la logique restante des workers
Qt vers `axiom/` (patron coquille), table vidée à la fin.

- [x] `axiom/db_helpers.py` : + `create_player_entity` (id sûr, collision, stats par
      défaut, origin runtime) — corrige au passage le corps DUPLIQUÉ pré-existant de
      `CreatePlayerEntityTask` (2ᵉ définition active sans import `datetime` → NameError
      latent sur nom vide/collision, présent dans HEAD)
- [x] `axiom/regenerate.py` : `regenerate_variant(...)` + `history_to_messages` +
      `append_variant` (payload legacy converti) + méthode `Session.regenerate_variant`
- [x] `axiom/mini_dico.py` : `answer_lore_question(...)` (RAG save-scopé + prompt
      encyclopédique + appel LLM, repli si réponse vide)
- [x] `axiom/multiplayer.py` : `PlayerAction` (sans Qt) + `ActionQueue` (FIFO pur
      threading, callbacks, boucle insensible aux erreurs d'un tour)
- [x] Coquilles : `CreatePlayerEntityTask`, `workers/regenerate_worker.py`,
      `workers/mini_dico_worker.py`, `core/multiplayer_queue.py` (signaux Qt seulement,
      API conservée — `PlayerAction` ré-exporté, imports GUI inchangés)
- [x] `workers/chronicler_worker.py` : **supprimé** (feu vert utilisateur 2026-06-10) ;
      au passage fix du chemin de mort hardcore (référence morte + garde isRunning)
- [x] `ARCHITECTURE.md` : table « non migré » vidée (note de portage B4)
- [x] Tests : `tests/test_engine_port_b4.py` (10 — entité joueur ×3 dont l'ancien
      NameError, régénération ×3 dont payload legacy, mini-dico ×2, file ×2)
- [x] Validation : suites affectées (53) + garde-fous collab + startup_check + smoke
      offscreen de compatibilité d'API des coquilles
