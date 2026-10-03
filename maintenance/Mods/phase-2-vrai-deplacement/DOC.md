# Phase 2 — vrai déplacement (DOC)

Objectif : qu'un mod de fonctionnalité **contienne** son code, et que le décocher le coupe vraiment
(D1/D3, M1/M2 de `ETAT_REEL.md`). Le travail non commité d'octobre avait fait l'inverse (code remis
dans `axiom/`, mods réduits à `from axiom.x import *`) : voir `../audit-reel-2026-10-03/DOC.md` §3.4.

## Contrat de stockage d'un mod (décision 2026-10-03 : « code de stockage seul »)

```toml
[storage]
facts = { policy = "step_keyed_table", table = "Facts", step_column = "turn_id", columns = [...] }
observations = { policy = "custom", table = "Observations", rewind = "storage:rewind_observations", fork = "storage:fork_observations" }
vector_store = { policy = "custom", rewind = "storage:rewind_vectors", fork = "storage:fork_vectors" }
```

- `rewind(conn, save_id, target_turn)` / `fork(conn, src, dst, at_turn, *, id_maps)` /
  `snapshot(conn, save_id, turn_id)` (capture de fin de tour, facultative) ; `conn` vaut `None` pour un
  stockage hors base (pas de `table`) : il est traité **après** le commit SQL.
- Le module (`storage.py` du mod) est chargé pour **tout mod installé**, même décoché : seul ce
  fichier s'exécute (aucun hook, prompt, UI). Il ne doit importer que le noyau et ses propres
  modules de données.
- `id_maps` : correspondance ancien → nouvel id par table, remplie dans l'ordre de déclaration
  (une table qui référence des ids d'une autre est déclarée après elle).

## Ce qui reste volontairement dans le noyau
- Le tour (`arbitrator.py`, narration de `prompts.py`) : décision de périmètre du 2026-10-03.
- Les tables de **définition** d'univers et le DDL des tables (`schema.py`) : la compilation
  d'univers reste au noyau, les mods y contribuent par les hooks `axiom.universe:*`.
- `axiom/memory.py` (mémoire vectorielle) : hors des 5 fonctionnalités choisies.
