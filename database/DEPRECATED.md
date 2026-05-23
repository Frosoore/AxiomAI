# ⚠️ Modules dépréciés — `database/`

Pilier 1 (§5) a extrait le moteur dans le package **`axiom/`**.
Les fichiers suivants de `database/` ont été **copiés dans `axiom/` et ne sont plus importés** :

| Fichier déprécié (`database/`) | Remplacé par |
|---|---|
| `event_sourcing.py`     | `axiom/events.py` |
| `checkpoint.py`         | `axiom/checkpoint.py` |
| `modifier_processor.py` | `axiom/modifiers.py` |
| `schema.py`             | `axiom/schema.py` |
| `presets.py`            | `axiom/presets.py` |

**Toujours utilisés (NE PAS toucher)** : `__init__.py`, `backup_manager.py`.

➡️ Suppression demandée via **TICKET-003** (`maintenance/PENDING.md`).
