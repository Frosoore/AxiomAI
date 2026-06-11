# Memory Index — AxiomAI

- [Pilier 2 Universe-as-Code — état/reprise](project_pilier2_status.md) — TOUT TERMINÉ, VALIDÉ et COMMITÉ : pilier + UX (028→033), B3, B4, QA 034→048 ; packaging pip (TICKET-009 clos, `axiomai-engine` sur PyPI) et génération d'images (backend Gemini cloud + fiabilisation SD/ComfyUI) **mergés dans `main` le 2026-06-11** ; validations GUI en attente (images) ; PENDING = 017 (Gemini) + 049 (compile.py vs Python 3.12) + 050 (fail-fast 429 limit:0)
- [Profil utilisateur : néophyte non-codeur](user_profile_non_coder.md) — pilote tout par IA, expliquer les choix techniques en termes accessibles avant de décider
- [Workflow maintenance par étapes](feedback_maintenance_workflow.md) — Créer maintenance/<etape>/{TODO,CHANGELOG,DOC}.md avant tout travail de code
- [Style d'exécution](feedback_execution_style.md) — Implémenter directement, docs minimales (TODO+CHANGELOG), pas de superpowers
- [Environnement de test](project_test_env.md) — Gemini only (carte AMD, pas de LLM local), venv `.venv/`, harnais `debug/run_step7_live.py`
- [L'utilisateur gère git lui-même](feedback_user_handles_git.md) — ne pas commit/stage/brancher, juste IMPLÉMENTER+TESTER+DOCUMENTER (très important)
- [L'utilisateur gère ses secrets lui-même](feedback_secrets_handling.md) — jamais de token/clé dans un fichier créé par l'agent ; il les saisit à la main dans son terminal
- [Stratégie moteur/app](project_engine_split_strategy.md) — mono-repo conservé MAIS moteur PUBLIÉ sur PyPI le 2026-06-10 : `pip install axiomai-engine` → `import axiom` (pyproject racine, TICKET-009 clos, `export_engine.py` pour les releases, `axiom.help`)
- [Dev parallèle à deux](project_parallel_dev_handover.md) — branches séparées : user (Claude) = Pilier 2 Universe-as-Code, pote (Gemini) = Pilier 5 Temps ; collision = schema/format/Session ; coordination dans `maintenance/collab/` (rulebook + EN_COURS.md scindés Claude/Gemini)
- [Édition chirurgicale sans bridage](feedback_surgical_edits.md) — interdire le reformatage gratuit hors-scope, mais autoriser les grosses refontes justifiées
