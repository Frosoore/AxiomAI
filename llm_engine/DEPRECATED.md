# ⚠️ Modules dépréciés — `llm_engine/`

Pilier 1 (§5) a extrait le moteur dans le package **`axiom/`**.
Les fichiers suivants de `llm_engine/` ont été **copiés dans `axiom/` et ne sont plus importés** :

| Fichier déprécié (`llm_engine/`) | Remplacé par |
|---|---|
| `base.py`             | `axiom/backends/base.py` |
| `prompt_builder.py`   | `axiom/prompts.py` |
| `vector_memory.py`    | `axiom/memory.py` |
| `universal_client.py` | `axiom/backends/universal.py` |
| `gemini_client.py`    | `axiom/backends/gemini.py` |
| `ollama_client.py`    | `axiom/backends/ollama.py` |

**Note** : `workers/db_helpers.py` est aussi déprécié → remplacé par `axiom/db_helpers.py`
(les autres modules de `workers/` restent : ce sont les wrappers QThread de l'app).

➡️ Suppression demandée via **TICKET-003** (`maintenance/PENDING.md`).
