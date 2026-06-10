# TICKET-033 — Retries visibles + annulation des générations — TODO

Demande utilisateur 2026-06-10 : voir dans la barre de statut quand arrive le prochain
essai (429) et combien de tentatives restent ; bouton d'annulation manuel pour toute
génération longue.

- [x] `axiom/backends/base.py` : `GenerationCancelled` + hooks neutres `on_status` /
      `cancel_event` sur `LLMBackend` (zéro Qt)
- [x] `axiom/backends/gemini.py` : attente de retry interruptible + compte à rebours émis
      (« Quota exhausted (model) — attempt i/3 — retry in Xs », rafraîchi toutes les ~5 s),
      pacing interruptible aussi (`reserve_turn` séparé de l'attente)
- [x] `axiom/populate.py` : paramètre `cancel` ; hooks branchés sur le llm ; check aux
      frontières de chunks (entités : le travail commité reste, message de reprise)
- [x] `workers/db_tasks.py` : signal `cancelled` (≠ error, pas de popup),
      `BaseDbTask.cancel()`, registre des générations actives
      (`active_generation_count` / `cancel_active_generations`), tâches marquées
      annulables (Populate* ×7, Preview, Canonize), sandbox nettoyée si la mutation
      échoue ou est annulée
- [x] `workers/db_worker.py` : relais `generation_cancelled`
- [x] `ui/main_window.py` : bouton « ✖ Annuler la génération » dans la barre de statut,
      visible seulement quand une génération tourne (poll 500 ms sur le registre)
- [x] Studio : statut « Génération annulée » ; Tabletop : bouton « Canoniser… » réactivé
- [x] Localisation EN + FR
- [x] Tests : compte à rebours émis, annulation pendant l'attente 429, annulation avant
      appel, annulation entre chunks (commits conservés), signal cancelled, registre
      (6 nouveaux + tests quota passés sur horloge factice)
- [x] Validation GUI utilisateur — **validé le 2026-06-10** → archivé dans DONE.md
