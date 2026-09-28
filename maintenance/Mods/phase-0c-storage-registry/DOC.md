# Documentation — Phase 0c : Registre unique de données de save & Éradication des listes manuelles

## Objectif
Résoudre les anomalies structurelles D6 (État caché) et D7 (Le rewind « chacun sa façon ») en remplaçant toutes les listes de tables codées en dur par un registre de stockage unifié (`axiom/storage_registry.py`).

## Politiques de Stockage
- `EVENTS` : Journal append-only d'événements ordonnés (`Event_Log`).
- `STEP_KEYED` : Table SQL relationnelle portant une colonne de temps/tour (`Timeline`, `Snapshots`, `Session_Lore`, etc.).
- `VERSIONED_KV` : Tables de métadonnées ou de définition univers/save.
- `CUSTOM` : Gestionnaires avec hooks dédiés (`VectorMemory`, etc.).
