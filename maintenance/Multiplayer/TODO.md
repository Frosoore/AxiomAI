# TODO — Mode Multijoueur simultané (hotseat local)

Plan détaillé : `PLAN.md`. Implémenteur : Claude. **Code terminé le 2026-06-26** (détail : `CHANGELOG.md`).
Restent uniquement les vérifs à lancer par l'utilisateur (pytest + GUI réel).

## 1. Moteur — Session
- [x] `axiom/session.py` : `take_turn_multiplayer(...)` (calque de `take_turn`, sans Companion).

## 2. Moteur — Schéma (migration)
- [x] `axiom/schema.py` : `'Multiplayer'` dans le CHECK de `_DDL_SAVES`.
- [x] Garde de migration `if "'Companion'"` → `if "'Multiplayer'"` (sinon bases existantes jamais migrées).
- [x] Message de log adapté.

## 3. Moteur — Prompts (narration 3ᵉ personne)
- [x] `axiom/prompts.py` : branche `mode == "Multiplayer"` (protagonistes pluriel, 3ᵉ personne, pas de "You").
- [x] Rappels de fin : clause de traduction adaptée (chaque "I" → nom du joueur).

## 4. Moteur — Arbitre (spatial v1 simple)
- [x] `process_turn` mémorise `_active_actor_ids` ; `_identify_relevant_entities` (vrai nom, ≠ plan) =
      PNJ co-localisés de TOUS les joueurs actifs (cap 3/lieu), fallback solo préservé.

## 5. App — Worker
- [x] `workers/narrative_worker.py` : param optionnel `intents` → `take_turn_multiplayer` ; solo inchangé.

## 6. App — GUI Tabletop (accumulation à la Companion)
- [x] `ui/tabletop_view.py` : `_pending_intents`/`_active_players`, `_handle_multiplayer_input`,
      `_resolve_multiplayer_turn`, pool vidé à `_on_turn_complete`.
- [x] `ui/widgets/chat_display.py` : `append_player_prep` (marqueur « action en file »).

## 7. App — Création de save
- [x] `ui/setup_view.py` : option `Multiplayer` aux 2 constructions du combobox (toujours dispo).
- [x] Clés i18n `multiplayer` + `mp_waiting_for` ×10 langues.

## 8. Vérifs finales
- [x] Scripts headless (migration, prompts, arbitre) + `tools/i18n_check.py` (757/757) + `startup_check.py`.
- [ ] **(utilisateur)** Suite `pytest` complète sur sa machine (pytest absent de ce venv).
- [ ] **(utilisateur)** Run GUI réel : save Multiplayer → ≥2 joueurs au Studio → tour à plusieurs.
- [x] Réconciliation legacy : `core/multiplayer_queue.py` (ArbitratorWorker, mort) **supprimé** ;
      `ActionQueue` conservée (primitive moteur + tests). Champ mort `_arbitrator_worker` retiré.
- [x] Bugfix « intentions fantômes » : `_pending_intents` réinitialisé dans `load_session` et purgé
      dans `_on_worker_error` (ne survit plus à un changement de save ni à un tour échoué).

## Hors périmètre v1
- Réseau / multi-machines (ce mode est hotseat local).
- Spatial complet (réécriture de l'hypothèse `player_entity_id` unique dans tout l'arbitre).
</content>
