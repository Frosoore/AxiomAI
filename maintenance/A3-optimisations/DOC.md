# A3 — Optimisations chirurgicales

Améliorations de performance sans changement de comportement visible.

- **3.1** Arbitrator : 2N+1 connexions SQLite/tour → 1 connexion + 2 requêtes globales.
- **3.2** EventSourcer : N `append_event` séparés → 1 transaction `append_events_batch` par tour.
- **3.3** Arbitrator : cache mémoire `_stats_cache` pour éviter le SELECT initial à chaque tour.
- **3.4** 14 `print()` → `logger.debug/error` sur 5 fichiers.
- **3.5** `run.sh` : pip install conditionnel basé sur le hash de requirements.txt.
- **3.6** `startup_check.py` : retrait de `sentence_transformers` et `chromadb` du check au démarrage.
