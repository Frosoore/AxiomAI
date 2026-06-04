# Memory Index — AxiomAI

- [Workflow maintenance par étapes](feedback_maintenance_workflow.md) — Créer maintenance/<etape>/{TODO,CHANGELOG,DOC}.md avant tout travail de code
- [Style d'exécution](feedback_execution_style.md) — Implémenter directement, docs minimales (TODO+CHANGELOG), pas de superpowers
- [Environnement de test](project_test_env.md) — Gemini only (carte AMD, pas de LLM local), venv `.venv/`, harnais `debug/run_step7_live.py`
- [L'utilisateur gère git lui-même](feedback_user_handles_git.md) — ne pas commit/stage/brancher, juste implémenter+tester+documenter
- [Stratégie moteur/app](project_engine_split_strategy.md) — mono-repo, pas de split physique avant reprise solo ; migration features app→engine = chantier des piliers
- [Dev parallèle + handover](project_parallel_dev_handover.md) — possesseur fait les features GUI via Gemini CLI, utilisateur fait le moteur ; garde-fous ARCHITECTURE.md + test headless
