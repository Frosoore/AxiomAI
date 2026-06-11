# Memory Index — AxiomAI

- [Pilier 2 Universe-as-Code — état/reprise](project_pilier2_status.md) — TOUT TERMINÉ, VALIDÉ et COMMITÉ sur dev-0 (2026-06-10) : pilier + UX (028→033), B3, B4, QA 034→048 ; backend image Gemini (2026-06-10, branche `image-gen`) : code+tests FAITS, validation GUI en attente ; PENDING = 009 (différé) + 017 (Gemini) + 049 (compile.py vs Python 3.12)
- [Profil utilisateur : néophyte non-codeur](user_profile_non_coder.md) — pilote tout par IA, expliquer les choix techniques en termes accessibles avant de décider
- [Workflow maintenance par étapes](feedback_maintenance_workflow.md) — Créer maintenance/<etape>/{TODO,CHANGELOG,DOC}.md avant tout travail de code
- [Style d'exécution](feedback_execution_style.md) — Implémenter directement, docs minimales (TODO+CHANGELOG), pas de superpowers
- [Environnement de test](project_test_env.md) — Gemini only (carte AMD, pas de LLM local), venv `.venv/`, harnais `debug/run_step7_live.py`
- [L'utilisateur gère git lui-même](feedback_user_handles_git.md) — ne pas commit/stage/brancher, juste IMPLÉMENTER+TESTER+DOCUMENTER (très important)
- [Stratégie moteur/app](project_engine_split_strategy.md) — mono-repo, pas de split physique avant reprise solo ; migration features app→engine = chantier des piliers
- [Dev parallèle à deux](project_parallel_dev_handover.md) — branches séparées : user (Claude) = Pilier 2 Universe-as-Code, pote (Gemini) = Pilier 5 Temps ; collision = schema/format/Session ; coordination dans `maintenance/collab/` (rulebook + EN_COURS.md scindés Claude/Gemini)
- [Édition chirurgicale sans bridage](feedback_surgical_edits.md) — interdire le reformatage gratuit hors-scope, mais autoriser les grosses refontes justifiées
