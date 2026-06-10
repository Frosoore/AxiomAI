# TICKET-033 — Retries visibles + annulation des générations — CHANGELOG

## 2026-06-10 — implémentation complète (session Claude)

**Backend (zéro Qt) :**
- `axiom/backends/base.py` : + `GenerationCancelled` (annulation volontaire ≠ erreur) ;
  hooks optionnels `on_status` / `cancel_event` sur `LLMBackend` (posés par l'appelant
  après construction, un backend qui les ignore reste valide) + helpers `_notify` /
  `_check_cancelled`.
- `axiom/backends/gemini.py` : `_interruptible_wait(delay, label)` — attente par tranches
  de 5 s, **compte à rebours** émis via `on_status` (« Quota exhausted (model) — attempt
  1/3 — retry in 27s ») et interruption immédiate si `cancel_event` est armé. Utilisée
  pour l'attente de retry 429 ET le pacing (`_RateLimiter.reserve_turn` séparé de
  l'attente). Bascule sur le modèle de secours également annoncée via `on_status`.

**Moteur :**
- `axiom/populate.py` : + paramètre `cancel` sur les 7 générateurs ; `_hook_llm` branche
  progression + annulation sur le backend ; `populate_entities` vérifie l'annulation à
  chaque frontière de chunk — les chunks commités restent (même philosophie de reprise
  que le 429), message explicite.

**Workers :**
- `workers/db_tasks.py` : signal `cancelled` sur TaskSignals (relayé par DbWorker en
  `generation_cancelled`) ; `BaseDbTask.cancel()` + `cancellable` ; **registre process-wide
  des générations actives** (`active_generation_count` / `cancel_active_generations`) —
  Populate* ×7, PreviewPopulateTask et CanonizeStoryTask sont annulables ;
  `_stage_source_change` nettoie la sandbox si la mutation échoue/est annulée.

**GUI :**
- `ui/main_window.py` : bouton « ✖ Annuler la génération » dans la barre de statut,
  caché par défaut, visible quand le registre est non vide (poll 500 ms — aucune vue à
  câbler) ; clic → `cancel_active_generations()` + statut « annulation… ». Les comptes à
  rebours du backend remontent déjà dans la barre via les signaux status existants.
- Studio : `generation_cancelled` → statut (pas de popup d'erreur) ; Tabletop : bouton
  « Canoniser… » réactivé sur annulation.
- `axiom/localization.py` : clés EN + FR.

**Tests :** `tests/test_generation_cancel.py` (nouveau, 6) : compte à rebours émis et
décroissant, annulation pendant l'attente de retry (pas de nouvel essai), annulation
avant appel, annulation entre chunks (commits conservés), tâche annulée → signal
`cancelled` (jamais `error`), registre start/cancel/join. `tests/test_gemini_client.py` :
les tests quota passent sur **horloge factice** (sleep avance monotonic — l'attente par
tranches boucle sur l'horloge, un sleep no-op aurait busy-waité). Suites vertes :
gemini/populate_engine/populate_resume/source_preview/generation_cancel (59),
db_worker_atomic/phase6/universe_as_code/savestore/localization/narrative_worker/session
(105), garde-fous collab + startup_check. Smoke offscreen : bouton MainWindow
(apparition/clic→event armé/disparition).

**Reste :** validation GUI utilisateur.
