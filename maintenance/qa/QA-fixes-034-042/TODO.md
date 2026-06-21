# QA-fixes-034-042 — TODO

Correction des tickets ouverts par la QA du 2026-06-10 (PENDING.md → DONE.md).

- [x] TICKET-034 — fork_save : copier Active_Modifiers + Fired_Scheduled_Events (+ test)
- [x] TICKET-035 — populate_events/stats : idempotence sur collision d'id (+ tests)
- [x] TICKET-036 — unpack_save : re-lier Save_Meta à l'univers de destination (+ test)
- [x] TICKET-037 — conversion .db plat : ne pas exporter les entités runtime vers la définition (+ test)
- [x] TICKET-038 — savestore/library/db_tasks : fermer les connexions sqlite (closing)
- [x] TICKET-039 — pack_universe : exclure .git/sidecars, purger les tables runtime du cache embarqué (+ test)
- [x] TICKET-040 — _recent_narrative : garde isinstance sur payload legacy
- [x] TICKET-041 — _safe_id : fallback déterministe pour noms non-latins (+ test)
- [x] TICKET-042.1 — cache load_config (mtime) + create_global_db une fois
- [x] TICKET-042.2 — canonisation : garde « déjà en cours » + réutiliser les DbWorker existants
- [x] TICKET-042.3 — annulation : couvrir les tâches encore en file (registre à la construction)
- [x] TICKET-042.4 — i18n : court-circuit populate_tab + contaminations fr/es/de relevées
- [x] TICKET-042.5 — hub delete : sidecars -wal/-shm + dossiers vector orphelins
- [x] TICKET-042.6 — setup_view : refresh_save_definition hors main thread
- [x] TICKET-042.7 — decompile : collisions _safe_filename désambiguïsées
- [x] TICKET-042.8 — manifest .axiomsave : échappement TOML
- [x] TICKET-042.9 — supprimer les sidecars debug_*.db-wal/-shm orphelins à la racine
- [x] Re-passer les suites de tests (par sous-ensembles)
- [x] PENDING.md → DONE.md (trace condensée)
