# Lot B1 — saves, rewind, fork, stockage (corrections 2026-10)

**Arrêté avant la fin, à la demande du propriétaire.** Aucun fichier n'est à moitié modifié. Je n'ai rien commité ni indexé, et je n'ai rien supprimé.

## 1. Corrigé (code écrit)

### R2-B-1 / TICKET-088 : le fork perdait la mémoire « living » (`axiom/storage_registry.py`, réécrit)
- Ce qui change dans la copie :
  - les id AUTOINCREMENT sont laissés à SQLite (on ne fournit plus de `uuid4`) ;
  - une table de correspondance par table (`id_maps`) fait le lien entre ancien et nouvel id ;
  - les `sources` des Observations sont réécrites avec les nouveaux `fact_id`, et celles des Mental_Models avec les nouveaux `observation_id`.
- Tous les `except sqlite3.Error: pass` sont supprimés. Une erreur pendant le fork remonte, et `fork_save` (`axiom/saves.py`) supprime alors la save à moitié créée.
- R2-m-2 : au fork, on copie les croyances et modèles nés au plus tard au tour N, puis on applique `rollback_observations` / `rollback_mental_models` à la copie. Le résultat est donc le même que celui d'un rewind.
- Vérifié avec le script de reproduction `phase0_repro3` :
  - avant : la save forkée avait `0/0/0` (faits/croyances/modèles) ;
  - après : `2/1/1`, comme la source.

### R2-I-3 : fork générique
- Les tables `EVENTS` et `STEP_KEYED` sont copiées par `_fork_generic` à partir des colonnes déclarées : `WHERE step <= N`, avec un id régénéré (`id_column` / `id_autoincrement`).
- Nouvelle politique `DERIVED` pour `State_Cache` : l'exclusion codée en dur par nom de table disparaît.
- Il reste des gestionnaires spécifiques là où c'est inévitable, pour les raisons documentées dans le code :
  - Observations, Mental_Models, Active_Modifiers, Item_Instances : des id sont stockés dans du JSON ;
  - les snapshots sont rattachés à leur table avec `fork_with`.
- `preferred_order` est remplacé par un ordre dérivé du registre.
- **TICKET-103** : `Fired_Scheduled_Events` est filtré sur `fired_turn_id <= N`. Vérifié avec `phase0_repro` scénario C (0 ligne) et par le test adapté `test_saves_editing::test_fork_copies_modifiers_and_fired_events`.
- **m-1** : le repli qui recopiait les modifiers actuels est supprimé. Les Modifier_Snapshots `<= N` sont copiés avec les id remappés.
- Le fork ne prend plus de snapshot supplémentaire : les Snapshots `<= N` sont copiés.

### R2-B-2 / TICKET-102 Qt : un seul rewind
- `CheckpointManager.rewind` (`axiom/checkpoint.py`) est maintenant le chemin moteur unique. B2 a fait passer `Session.rewind` par lui. Il enchaîne :
  1. incrément de l'époque de la save ;
  2. sauvegarde auto, via `set_rewind_backup_handler` : le moteur headless ne peut pas importer `database`. L'application installe le handler dans `workers/db_tasks.py` ;
  3. rewind SQL et `Saves.last_updated`, dans une seule transaction, puis commit ;
  4. reconstruction de `State_Cache` ;
  5. **après** le commit seulement, les stockages externes des mods.
- `RewindTask` (`workers/db_tasks.py`) appelle seulement ce chemin.
- Dans `tabletop_view.py`, `_on_rewind_done` appelle directement `_finalize_rewind`. Le `VectorWorker` de rollback et ses deux slots sont supprimés.
- Tests : `test_edit_messages_ui.py` a été adapté (`test_tabletop_view_rewind_has_no_second_vector_rollback`) et j'y ai ajouté `test_rewind_task_uses_engine_rewind_path` (vérifie que l'époque est incrémentée et que le backup est créé). Les 8 tests passent.

### TICKET-100 / R2-m-8 : ids Chroma déterministes et rollback après le commit
- `axiom/memory.py` :
  - format d'id `chunk_id()` = `"{save}:{turn}:{type}:{idx}"`, écrit avec `upsert` ;
  - nouveau paramètre `chunk_index` ; le mod rag passe 0 pour le récit d'un tour ;
  - le cache BM25 est vidé quand un id existant est écrasé.
- Nouveau `VectorMemory.copy_to` : le fork copie la mémoire sémantique `<= N` (service rag `fork`).
- Le rollback Chroma s'exécute après le commit SQL, via `execute_external_rewind`.
- La docstring périmée est réécrite.
- Tests `test_vector_memory.py` : `test_returns_string_id` adapté, `test_replayed_turn_overwrites_its_chunk` ajouté. Ils passent.

### TICKET-104 : regenerate (`axiom/regenerate.py`)
- Le prompt remplace la vraie consigne `NARRATIVE_TOOL_CALL_SCHEMA` (`prompts.py:57`) par une consigne « prose seule ».
- `strip_json_block` retire tout bloc JSON final avant `append_variant`.
- Vérifié à la main sur 5 cas. **Pas de test pytest écrit.**

### R2-I-7 / 0d : définition d'objet pendant la validation (`mods/axiom.inventory/main.py`)
- La validation est maintenant en lecture seule : plus d'`ensure_item_definition` ni de `commit`.
- La définition est créée par `add_item`, au moment du commit du `write_batch`.
- Vérifié avec `phase0_repro` scénario B : 0 ligne `mystery_orb` (il y en avait 1 avant). **Pas de test pytest écrit.**

### R2-m-6 : époques (`axiom/epoch.py`, `mods/axiom.living_memory/living_memory.py`)
- Nouveau `SessionEpochManager.guarded_write()` : verrou partagé avec `bump()`.
- Les 3 écritures de la mémoire living passent par `_epoch_guarded`, qui fait la vérification et l'écriture de façon atomique.
- `run_extract_now` capture l'époque au départ et la vérifie avant d'écrire ; `consolidate_facts_to_beliefs` accepte maintenant l'époque.
- **Pas de test pytest écrit.**

### R2-m-3 / 0e : migrations des mods
- Nouvelles fonctions dans le registre : `register_mod_migrations`, `apply_registered_mod_migrations`.
- Nouvelle méthode `ctx.register_migrations()` dans `axiom/kernel/context.py`. Elle est retirée au `cleanup` du mod.
- Les migrations sont appliquées à la création d'une save (`savestore.create_save`).
- `Mod_Schema_Versions` passe côté save (`is_runtime=True`, `save_scoped=False`) :
  - elle n'est plus copiée depuis l'univers ;
  - elle n'est ni forkée ni purgée.
- **Pas de test pytest écrit.** Les migrations ne sont pas non plus appliquées à l'ouverture d'une save : voir §4.

### Point 9 : stockages des mods
- Nouvelle méthode `ctx.register_storage()` dans `context.py`, qui fait l'enregistrement par propriétaire et le retrait au `cleanup`.
- `axiom.rag` et `axiom.illustrations` l'utilisent. Le double enregistrement `VectorMemory` de rag (deux rollbacks Chroma par rewind) est supprimé.
- Les stockages externes ne figurent plus dans `get_runtime_tables()`.

### Harnais golden (`axiom/testing/golden_harness.py`), partiel
- `canonicalize` compare maintenant :
  - **toutes** les tables runtime du registre (clé `tables`), avec des clés de contenu à la place des id ;
  - le nombre de chunks Chroma par tour et par type (`vector_chunks`, si on passe `vector_memory=`).
- Pour un `at_turn` passé, l'état est reconstruit sur une copie de la base rembobinée.
- **Bug trouvé par le nouveau harnais (corrigé)** : `State_Cache` est vide après `create_save`, et la mise à jour par tour (`turn_batch._apply_events_to_state_cache`) transformait un delta en valeur absolue : `Arcane Focus` valait `-15` au lieu de `85` après un tour. C'est ce que lisait `get_current_stats`.
  - Correctif : `savestore.create_save` matérialise `State_Cache` dès la création.
  - La racine du problème est dans `turn_batch.py`, voir §4.

## 2. Non fait / partiel
- **Nouveaux tests golden non écrits** :
  - fork à mi-partie comparé à l'état de la source au tour N ;
  - export « définition seule » (`pack_universe`) ;
  - test d'époque avec un faux LLM qui produit vraiment des faits ;
  - test d'atomicité de l'époque.
- **Pas vérifié** que les nouveaux tests échouent sur l'ancien code. Seuls les scripts de reproduction ont été relancés avant/après (088, 103, B).
- Pas de tests pytest dédiés pour : TICKET-104, 0d, `run_extract_now`, `ctx.register_storage` / `register_migrations`, rollback Chroma non exécuté si le SQL échoue.
- La politique `[storage]` des manifestes n'est pas branchée sur le registre.

## 3. Tests
Commande : `AXIOM_CONFIG_DIR/AXIOM_DATA_DIR` temporaires, script `/tmp/claude-1000/axiom-fix/b1/run.sh`.

| Moment | Lots | Résultat |
|---|---|---|
| Avant mes changements | tous les lots demandés | verts (122 + 45 + 61 + 7) |
| En cours de travail | lot 1 | 3 échecs, corrigés ensuite (test d'époque, fork des modifiers, `check_headless` sur l'import `database`) |
| En cours de travail | lot 2 | 1 échec (id uuid), corrigé |
| En cours de travail | `test_providers_illustrations_mods`, `test_ticket_fixes` | 16 passés |
| Derniers passages | `test_saves_editing`, `test_vector_memory`, `test_packaging` | 86 passés |
| Derniers passages | `test_golden_step` | 5 passés |
| Derniers passages | `test_edit_messages_ui` | 8 passés |

**Non relancé après les tout derniers changements** :
- changements : `State_Cache` matérialisé dans `create_save`, fork sans snapshot supplémentaire, copie Chroma au fork ;
- tests concernés : `test_checkpoint`, `test_savestore`, `test_saves_sorting`, `test_inventory_rewind`, `test_memory_*`, `test_observations`, `test_facts`, `test_fact_worker`, `test_schema`, `test_ticket_fixes`.

À relancer en priorité.

## 4. Hors périmètre, à faire, questions
- **Lot B2 / lot du tour** :
  - `turn_batch._apply_events_to_state_cache` doit partir des stats de base (`Entity_Stats`) quand le cache ne contient pas la stat ;
  - `arbitrator.py:1910-1952` crée encore des `Item_Definitions` pendant la validation, sur le chemin sans registre ;
  - `Session.rewind` refait la purge des assets et `last_updated` (doublons sans effet, à retirer) ;
  - `Session.__init__` devrait appeler `storage_registry.apply_registered_mod_migrations(db_path)` à l'ouverture d'une save ;
  - le web/CLI doit appeler `checkpoint.set_rewind_backup_handler(create_auto_backup)`, sinon le rewind ne fait pas de sauvegarde auto.
- **Dans mon périmètre mais à signaler** : `execute_rewind(conn, …)` garde `external=True` par défaut pour rester compatible avec `test_providers_illustrations_mods`.
- **Question au propriétaire** : la sauvegarde auto avant chaque rewind, qui ajoute une copie de la base à chaque fois, doit-elle s'appliquer aussi au web/CLI ? Aujourd'hui, c'est seulement là où l'application installe le handler.
