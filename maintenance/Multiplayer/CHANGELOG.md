# CHANGELOG — Mode Multijoueur simultané

## 2026-06-26 — Cadrage & vérification du plan
- Plan d'origine (Gemini CLI) collé verbatim dans `PLAN.md`.
- Vérification réf-par-réf contre le code réel : plan validé sur le fond, toutes les fonctions/variables
  citées existent. 5 corrections + 3 décisions actées (voir en-tête `PLAN.md`).
- Décisions : implémenteur = Claude ; portée spatiale v1 = simple ; mode toujours disponible.
- Dossier d'étape `maintenance/Multiplayer/` créé (PLAN/TODO/CHANGELOG/DOC).

## 2026-06-26 — Implémentation (feu vert reçu)
Tous les lots du `TODO.md` réalisés :
- **Moteur** :
  - `axiom/session.py` : `take_turn_multiplayer(intents, …)` (calque de `take_turn`, sans logique Companion).
  - `axiom/schema.py` : `'Multiplayer'` ajouté au CHECK `_DDL_SAVES` ; **garde de migration corrigée**
    `if "'Companion'"` → `if "'Multiplayer'"` (sinon les bases existantes ne migraient jamais) + log.
  - `axiom/prompts.py` : branche `mode == "Multiplayer"` → règle « protagonistes au pluriel, 3ᵉ personne,
    jamais "You" » + clause de traduction des rappels de fin adaptée (chaque "I" → nom du joueur).
  - `axiom/arbitrator.py` : `process_turn` mémorise `self._active_actor_ids` ; **`_identify_relevant_entities`**
    (le vrai nom de la méthode ; le plan disait `_fetch_relevant_entities`) collecte les PNJ co-localisés
    de **tous** les joueurs actifs (cap 3 par lieu), fallback joueur unique préservé.
- **App** :
  - `workers/narrative_worker.py` : param optionnel `intents` → appelle `take_turn_multiplayer` ; solo inchangé.
  - `ui/widgets/chat_display.py` : `append_player_prep(name, text)` (marqueur cyan « action en file »).
  - `ui/tabletop_view.py` : `_pending_intents`/`_active_players` ; `_on_send_message` branche le mode ;
    `_handle_multiplayer_input` (accumulation + passage au joueur suivant) ; `_resolve_multiplayer_turn`
    (résolution simultanée quand tous ont joué) ; pool vidé à `_on_turn_complete`.
  - `ui/setup_view.py` : option `Multiplayer` ajoutée aux **deux** constructions du combobox (toujours dispo).
  - `core/locales/*.toml` : clés `multiplayer` + `mp_waiting_for` ×10 langues (i18n 757/757 OK).

### Vérifications (pytest absent de ce venv → scripts headless + outils)
- Migration schéma : DB `Companion`-only → migre et accepte `Multiplayer`, idempotente, données préservées. ✅
- Prompts : Multiplayer = 3ᵉ personne sans "You" ; solo inchangé. ✅
- Arbitre : PNJ des deux lieux des joueurs inclus, lieu sans joueur exclu, fallback solo OK. ✅
- `tools/i18n_check.py` : 757/757 toutes langues. ✅
- `debug/startup_check.py` : Passed. ✅ — imports UI/moteur OK.
- ⚠ **À lancer par l'utilisateur sur sa machine** : suite `pytest` complète + run GUI réel d'une partie
  Multiplayer (créer save Multiplayer → ajouter ≥2 joueurs au Studio → jouer un tour à plusieurs).

## 2026-06-26 — Bugfix « intentions fantômes » + nettoyage legacy
- **Bug (rapporté en réel) :** dans une nouvelle save Multiplayer, le 2ᵉ joueur « répondait » tout seul
  avec l'action saisie dans une save **précédente** (supprimée), et le tour démarrait sans input.
  **Cause :** `self._pending_intents` n'était pas réinitialisé (a) entre deux saves (`load_session`),
  ni (b) après un échec de tour (`_on_worker_error`). Scénario réel : save #1 avec backend éteint →
  les 2 intents étaient en file → résolution → erreur LLM → file **non vidée** → nouvelle save → en
  tapant pour le joueur 1, le joueur 2 était déjà « en file » (valeur fantôme) → résolution immédiate.
- **Fix :** réinit de `_pending_intents`/`_active_players` dans `load_session` ; purge de
  `_pending_intents` + retour au 1ᵉʳ joueur dans `_on_worker_error` (mode Multiplayer). Le pool ne
  survit plus jamais à un changement de save ni à un tour échoué.
- **Nettoyage legacy (feu vert user) :** `core/multiplayer_queue.py` **supprimé** (coquille Qt
  `ArbitratorWorker`/`MultiplayerQueueSignals` 100 % morte, aucun test ne la touchait). Champ mort
  `_arbitrator_worker` retiré de `tabletop_view`, import `PlayerAction` repointé sur `axiom.multiplayer`.
  **`axiom.multiplayer.ActionQueue` CONSERVÉE** (primitive moteur, gardée avec ses 2 tests
  `test_engine_port_b4.py`). `PlayerAction` reste vivant (conteneur du NarrativeWorker).

### Reste / non commité
- Réconciliation legacy `ActionQueue`/`ArbitratorWorker` (contournés) : à proposer séparément, jamais
  de suppression sans feu vert.
- README.md : conflit de merge non résolu **réparé** (côté groupé conservé) + ligne `Multiplayer/` ajoutée.
</content>
