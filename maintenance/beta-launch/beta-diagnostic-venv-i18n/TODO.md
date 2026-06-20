# TODO — Outil de diagnostic : venv auto + i18n

Préparation bêta. `python -m tools.diagnostic --gui` « ne marche pas » : lancé avec
le python système (hors `.venv`), les deps lourdes (torch, chromadb, google-genai…)
sont absentes → le rapport affiche « tout cassé » alors que tout est dans `.venv`.

## Tâches

- [x] **Venv auto** : ré-exécution dans `.venv/bin/python` (ou `.venv\Scripts\python.exe`).
      Garde `AXIOM_DIAG_REEXEC` + flag `--no-venv`. Détection par `sys.prefix`.
- [x] **i18n** : contenu du rapport traduit dans les 10 langues (57 clés `diag_*`).
      Données littérales (versions, chemins, ids, exceptions, backend) inchangées.
- [x] Chaînes EN gardées identiques (tests d'assertion verts).
- [x] Clés `diag_*` ajoutées aux 10 `core/locales/*.toml` (615/615 partout).
- [x] README : note de bascule auto + `--no-venv`.
- [x] Tests verts (781 + 7 + couverture i18n).
- [x] Bonus : fix d'isolation i18n dans `conftest.py` (cache de langue qui fuyait).

⚠ Non commité — l'utilisateur gère git lui-même.
