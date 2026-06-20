# Changelog — A5 hotfix import circulaire

## Session 2026-05-22

- `database/schema.py` : remplacé `from core.logger import logger` par
  `logger = logging.getLogger("Axiom AI")`. La couche `database/` ne déclenche
  plus l'init du package `core` au chargement → cycle cassé.
- `database/backup_manager.py` : même correction (dépendance latente identique,
  non encore déclenchée mais à risque).
- Vérifié : `import database.schema`, `import core`, `from workers.db_worker
  import DbWorker` OK ; `debug/startup_check.py` → `[1/3] SUCCESS`.

Note : `startup_check.py [3/3]` signale encore `google.genai` manquant — c'est
une dépendance d'environnement (venv via run.sh), hors périmètre de ce hotfix.
