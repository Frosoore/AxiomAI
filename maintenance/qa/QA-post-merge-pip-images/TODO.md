# TODO — QA post-merge pip + images (d77db2b, 2026-06-11)

- [x] Lire memory/, maintenance/README.md, collab/ (instructions de l'autre dev : rien en cours, tout mergé)
- [x] Identifier le merge à contrôler : `d77db2b` = `fbe8b6e` (packaging pip) × `a03edf5` (génération d'images)
- [x] Vérifier les résolutions de conflits (`git show --remerge-diff`)
- [x] Vérifier qu'aucun code n'a été perdu (diff HEAD vs chaque parent)
- [x] Vérifier les conflits sémantiques packaging ↔ images (deps pyproject, contrat zéro Qt, `axiom/__init__.py`)
- [x] Lancer le contrat partagé du merge (`test_engine_headless` + `test_cli_play` + `startup_check.py`)
- [x] Lancer la suite complète (hors Qt/vector) + le lot Qt/vector séparé
- [x] Revue de code des fichiers mergés (image_generator, backends/gemini, chat_display, settings_dialog, config, localization)
- [x] Ouvrir les tickets pour les trouvailles (TICKET-051, TICKET-052, note sur 049)
- [x] Mettre à jour memory/project_test_env.md (venv passé en Python 3.14.5)
