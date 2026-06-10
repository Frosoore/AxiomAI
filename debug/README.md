# debug/

Outils de **debug manuels** — pas des tests automatisés. Les tests pytest vivent dans `tests/`.

Ces scripts se lancent à la main et on **lit/observe** leur sortie (ils ne sont pas ramassés par
pytest). Lancer avec le venv du projet : `.venv/bin/python debug/<script>.py`.

| Fichier | À quoi ça sert | Usage |
|---|---|---|
| `startup_check.py` | Garde-fou : vérifie que les imports clés du moteur et de l'app chargent (démarrage sain). Référencé par le contrat de collaboration (`maintenance/collab/`). | `.venv/bin/python debug/startup_check.py` |
| `run_step7_live.py` | Harnais live headless : construit une `Session` réelle et joue un tour sur le backend LLM configuré (sans GUI). Sert à valider un vrai tour de jeu. | `PYTHONPATH=. .venv/bin/python debug/run_step7_live.py` |
| `db_integrity.py` | Diagnostic d'une base d'univers `.db` (cohérence State_Cache vs Event_Log, etc.). | `.venv/bin/python debug/db_integrity.py <universe.db>` |
| `llm_test.py` | Test manuel d'un backend LLM (connexion / réponse). | `.venv/bin/python debug/llm_test.py` |
| `test_audio_crossfade.py` | Outil **interactif** : joue un fondu enchaîné audio entre deux tags pour l'écouter. Malgré son nom `test_`, ce n'est pas un test pytest. | `.venv/bin/python debug/test_audio_crossfade.py <tag1> <tag2>` |
