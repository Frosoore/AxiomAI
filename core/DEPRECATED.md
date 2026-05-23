# ⚠️ Modules dépréciés — `core/`

Pilier 1 (§5) a extrait le moteur dans le package **`axiom/`** (zéro dépendance Qt).
Les fichiers suivants de `core/` ont été **copiés dans `axiom/` et ne sont plus importés**
par l'application ni par les tests :

| Fichier déprécié (`core/`) | Remplacé par |
|---|---|
| `arbitrator.py`   | `axiom/arbitrator.py` |
| `chronicler.py`   | `axiom/chronicler.py` |
| `rules_engine.py` | `axiom/rules.py` |
| `time_system.py`  | `axiom/time_system.py` |
| `config.py`       | `axiom/config.py` |
| `paths.py`        | `axiom/paths.py` |
| `logger.py`       | `axiom/logger.py` |
| `localization.py` | `axiom/localization.py` |

**Toujours utilisés (NE PAS toucher)** : `__init__.py`, `multiplayer_queue.py`, `st_parser.py`.

➡️ Suppression demandée via **TICKET-003** (`maintenance/PENDING.md`), conditionnée à la
validation complète du Pilier 1 (parité fonctionnelle + zéro régression).
