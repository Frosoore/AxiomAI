# A5 — Hotfix : import circulaire au démarrage

Régression introduite par A3.4 (print→logger) : `database/schema.py` importe
`from core.logger import logger`, ce qui déclenche `core/__init__` →
`arbitrator` → `event_sourcing` → `database.schema.get_connection` (pas encore
défini). L'app ne démarre plus.

- [x] Retirer la dépendance `core` au chargement de `database/schema.py`
- [x] Idem `database/backup_manager.py` (même dépendance latente)
- [x] Vérifier `debug/startup_check.py` : `[1/3] DbWorker signals` repasse SUCCESS
