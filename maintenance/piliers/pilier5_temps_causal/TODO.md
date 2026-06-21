# Pilier 5 — Le Temps comme substrat causal

- [x] Étape 1 : Étendre `NARRATIVE_TOOL_CALL_SCHEMA` dans `prompt_builder.py` (ajouter `elapsed_minutes` et `scene_pace`).
- [x] Étape 2 : Côté `Arbitrator`, parser ces champs et les retourner dans `ArbitratorResult` (ajouter `elapsed_minutes: int`).
- [x] Étape 3 : Côté `NarrativeWorker` / `tabletop_view._on_turn_complete`, remplacer l'avancée fixe de 15 minutes par `result.elapsed_minutes`.
- [x] Étape 4 : Appeler `tick_modifiers` avec `elapsed_minutes=result.elapsed_minutes`.
- [x] Étape 5 : Déclenchement du `Chronicler` basé sur les minutes et non plus les tours.
- [x] Étape 6 : Vérifier que les `Scheduled_Events` se déclenchent bien via `arbitrator._fetch_triggered_events`.
- [x] Étape 7 : Réactiver `TimekeeperWorker` comme fallback.
- [x] Étape 8 : Lancer `debug/run_step7_live.py` (à exécuter par l'utilisateur avec sa clé API).

## Correctifs post-review (2026-06-07)
- [x] TICKET-016 : câbler `Session._time_llm` depuis `resolve_time_model` (réglage « Time Model »).
- [x] TICKET-015 : rendre le Timekeeper désactivable (`timekeeper_enabled` + toggle UI Réglages → Général).
- [x] TICKET-018 : Chronicler déclenché en minutes in-game (franchissement de palier).
- [x] TICKET-019 : une seule ligne `Timeline` par tour.
- [x] TICKET-020 : retirer le scaffolding mort (`session.py`, `tabletop_view.py`).
- [x] TICKET-021 : installer pytest, réparer les tests cassés, ajouter la couverture temps causal.
- [x] TICKET-022 : renuméroter les tickets temps causal en doublon (TC1→TC5).
- [ ] TICKET-017 : exploiter ou retirer `major_event_description` (Timekeeper).
