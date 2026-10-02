# Revue 2 — Phase 0 « assainir le moteur » + tickets TICKET-100→105 / 088 / 089

Branche `mods` (HEAD `3f100ed`) comparée à `main` (`e0ad4be`). Référence : `git show e0ad4be:maintenance/Mods/DOC.md`
§13 phase 0, `ARBITRAGE.md` rangs 1-6, 14, 16, 18, 21-24, `PENDING.md` (version main).
Légende des preuves : **[exécuté]** = vérifié en lançant du code ; **[lu]** = vérifié en lisant le code ; **[supposé]**.
Scripts de reproduction (hors repo) : `/tmp/claude-1000/axiom-review/phase0_repro*.py`.

---

## 1. Verdict

La phase 0 a vraiment été attaquée. Ce n'est pas du maquillage : il y a un registre des tables, un tampon d'écritures
avec un seul commit, des époques, un harnais de test, et le gros bug TICKET-101 (tour raté = message orphelin) est
**corrigé, je l'ai vérifié en l'exécutant**. Toute la suite de tests moteur passe (394 tests, 0 échec).
Mais la case « 0a→0f terminées » est **trop optimiste**. Plusieurs promesses centrales ne sont tenues qu'en partie :
- le fork d'une save **perd toujours, et sans rien dire**, toute la mémoire living (TICKET-088 pas corrigé, l'erreur est avalée) ;
- il reste **deux chemins de rewind** (Qt passe à côté de `Session.rewind`, donc à côté des époques) ;
- l'auto-canonize vit toujours dans Qt **et** dans le JS du web ;
- les tickets TICKET-103 (moitié), 104 et 100 (ids `uuid4`) restent ouverts.
On trouve aussi une **régression** : la « boucle de correction » (l'indice donné au narrateur quand une action est refusée)
ne marche plus du tout (vérifié en exécutant, sur la branche et sur main).
Le harnais golden est utile, mais il compare un état trop étroit pour attraper ces trous.

**Ce que ça veut dire concrètement :** la fondation est meilleure qu'avant. Elle n'est pas encore « saine » au sens du
DOC, et 3 ou 4 bugs de données doivent être corrigés avant de bâtir dessus (D17).

---

## 2. Ce qui est bien fait (preuves)

- **TICKET-101 corrigé** [exécuté, `phase0_repro.py` scénario A]. Un faux LLM lève `LLMConnectionError` au tour 2.
  Après l'échec : `turn_id == 1`, l'`Event_Log` ne contient **aucun** `user_input` du tour 2, et le tour suivant envoie au
  LLM un seul message joueur (l'action ratée n'y est pas). Mécanisme : `axiom/session.py:303-341` (restaure `_turn_id` et
  l'intent pool), tour tamponné dans `TurnWriteBatch` et commit unique `session.py:345-348`.
- **Le tour transactionnel est réel, pas un simple emballage** [lu]. `TurnWriteBatch.commit_all` (`axiom/turn_batch.py:40-313`)
  écrit tout avec la connexion qu'on lui passe, dans un seul `with conn:`. La réentrance de `_ClosingConnection`
  (`axiom/schema.py`, `__enter__`/`__exit__` avec `_enter_depth`) fait que le `with` imbriqué ne valide pas trop tôt. Les
  écritures directes au fil du tour (events, timeline, lore, modifiers, events planifiés) passent désormais par le tampon.
- **Registre des données** [lu + exécuté]. `axiom/storage_registry.py:150-223` déclare 30 tables. Il remplace les listes
  à la main de `package.py` (`_RUNTIME_TABLES` supprimée), de `savestore.py` (`_DEFINITION_COPY`/`_RUNTIME_COPY` sont
  maintenant dérivées) et de `checkpoint.py`/`saves.fork_save`. Seule table d'une save absente du registre :
  `Save_Meta` (exécuté, scénario D).
- **TICKET-089 étendu corrigé** [exécuté, scénario D]. `get_runtime_tables()` contient `Item_Instances`, `Session_Lore`,
  `Facts`, `Observations` et `Mental_Models`. La purge « définition seule » de `package.py` les retire donc.
- **TICKET-100, partie rewind, corrigée pour web/CLI** [exécuté, `phase0_repro2.py` scénario F]. Le mod `axiom.rag`
  enregistre un rewind custom (`mods/axiom.rag/main.py:163-173`). Après 3 tours, `rewind(1)` puis rejeu du tour 2, Chroma
  contient exactement 1 chunk par tour, sans doublon.
- **TICKET-102 web** [lu + exécuté]. Les globales `_FACT_*` et le thread maison de `main_web.py` ont disparu (grep).
  `LivingMemoryAccumulator.spawn_distillation` (`mods/axiom.living_memory/living_memory.py`, ~l.470) capture l'époque du
  save et la revérifie avant d'écrire. `Session.rewind` incrémente bien l'époque (exécuté, scénario G : 1 → 2).
- **0b, mémoire living** [lu]. Un seul algorithme (`LivingMemoryAccumulator`). Le web délègue à `Session`, et la méthode
  Qt `_accumulate_and_maybe_extract` est vide (`mods/axiom.ui.qt/ui/tabletop_view.py:~1197`). La CLI en profite parce
  qu'elle passe par `Session`.
- **0e** [exécuté]. Le `CHECK(difficulty IN …)` est retiré, avec sa migration (`schema.py`, `migrate_saves_difficulty_constraint`).
  `mod_settings` (et l'alias `mods`) survit à un aller-retour `load_config`/`save_config` (vérifié : `{'comm.x': {...}}`
  conservé). `apply_mod_migrations` et `Mod_Schema_Versions` existent.
- **0f** [lu]. `TurnContext` (`axiom/arbitrator.py:91-160`) expose vraiment les données intermédiaires (prompt, réponse
  brute, tool call, changements rejetés, batch…). Il y a 6 étapes nommées (`arbitrator.py:324-935`) et des points
  d'extension entre elles dans `mods/axiom.turn/main.py:80-149`.
- **TICKET-105, par effet de bord** : plus d'indice périmé après un rewind. Mais c'est pour une mauvaise raison (voir I-1).
- **Tests** [exécuté] : `test_golden_step, test_engine_headless, test_cli_play, test_checkpoint, test_session` donnent
  54 passed. `test_arbitrator, test_saves_editing, test_saves_sorting, test_savestore, test_packaging, test_inventory_rewind,
  test_schema, test_config` donnent 197 passed. `test_vector_memory, test_memory_mutations, test_memory_mods,
  test_world_turn_mods, test_mod_store_and_packaging` donnent 60 passed. `test_web_server, test_fact_worker, test_facts,
  test_factextract` donnent 83 passed. Aucun échec, donc pas eu besoin de comparer avec main sur ce point.

---

## 3. Problèmes

### BLOQUANT

**B-1. Le fork perd toute la mémoire living, sans aucune erreur (TICKET-088 non corrigé, maquillé en « corrigé »)**
- Constat [exécuté, `phase0_repro3.py`] : une save avec 2 faits, 1 croyance et 1 modèle mental, forkée au tour 2, donne
  une copie avec `0 / 0 / 0`.
- Cause [lu] : `storage_registry.py:395` (Facts), `:57` (Observations) et `:78` (Mental_Models) insèrent `str(uuid.uuid4())`
  dans des colonnes `INTEGER PRIMARY KEY AUTOINCREMENT` (`schema.py:182, 206, 228`). SQLite refuse (« datatype mismatch »),
  et l'erreur est avalée par `except sqlite3.Error: pass` (`:397`, `:59`, `:80`). Second défaut : même avec des ids
  corrects, les `sources` des croyances pointeraient vers les anciens `fact_id`.
- Garde-fou : D7 (le point d'entrée unique doit **appliquer** la politique), §10.2.
- Conséquence : dupliquer ou forker une partie en mode living donne une copie amnésique, et personne n'est prévenu. Le
  harnais golden ne le voit pas, parce qu'il ne compare pas ces tables (voir I-5).
- Correction : ne pas fournir d'id (laisser l'AUTOINCREMENT), garder une table de correspondance ancien → nouveau `fact_id`
  pour réécrire les `sources` des Observations et des Mental_Models, supprimer les `except: pass`, et ajouter Facts,
  Observations et Mental_Models au canonicaliseur du harnais.

**B-2. Deux points d'entrée de rewind : Qt contourne `Session.rewind`, donc les époques (TICKET-102 ouvert côté Qt)**
- Constat [lu] : Qt rembobine via `DbWorker.execute_rewind` → `RewindTask` → `CheckpointManager.rewind`
  (`workers/db_tasks.py:156-178`, appelé depuis `tabletop_view.py:1004` et `:1076`), puis lance **lui-même** le rollback
  vectoriel (`tabletop_view.py:1079-1093`). Il refait aussi sa sauvegarde auto et la purge des illustrations, déjà faites
  dans `Session.rewind` (`session.py:438-468`).
- [exécuté, scénario G] `CheckpointManager.rewind` **n'incrémente pas** l'époque (1 → 1), alors que `Session.rewind`
  l'incrémente (1 → 2).
- Garde-fou : D7 (« un seul point d'entrée »), D5, §10.4.
- Conséquence : dans l'appli Qt, un rewind pendant qu'une distillation de mémoire tourne laisse ce job écrire des faits
  issus de tours annulés. C'est exactement TICKET-102, toujours ouvert côté Qt. ChromaDB est aussi rembobinée deux fois
  (sans dégât, mais c'est la preuve qu'il y a deux chemins).
- Correction : faire de `Session.rewind` (ou d'une fonction moteur unique qui incrémente l'époque) le seul chemin.
  `RewindTask` doit l'appeler. Sortir la sauvegarde auto de Qt pour la mettre dans ce chemin. Supprimer le
  `VectorWorker` de rewind dans Qt.

### IMPORTANT

**I-1. Régression : la boucle de correction du narrateur ne fonctionne plus (et c'est elle qui « corrige » TICKET-105)**
- Constat [exécuté, `phase0_repro4.py`, sur la branche **et** sur un worktree de main] : on rejette un changement d'état
  (entité inconnue) au tour 1. Sur main, l'indice `[NARRATOR HINT …]` est présent dans le prompt du tour 2 (`True`).
  Sur `mods`, il est absent (`False`).
- Cause [lu] : `mods/axiom.turn/main.py:19-24` crée un **nouvel** `ArbitratorEngine` à chaque tour. La variable
  `_ENGINE_CACHE` (l.16) existe mais n'est jamais utilisée. Or l'indice vit sur `self._pending_correction`
  (`arbitrator.py:232, 586, 1823`).
- Garde-fou : D6 (état caché sur `self`). Le bon correctif de TICKET-105 était de stocker l'indice dans le stockage de
  save, pas de le perdre.
- Conséquence : quand le joueur tente une action impossible, le narrateur ne raconte plus l'échec au tour suivant.
- Correction : stocker l'indice comme donnée du tour (un event `correction_hint` ou une ligne `versioned_kv`), lue au tour
  suivant et donc rembobinée automatiquement. Ajouter un test golden « rejet → indice au tour suivant ».

**I-2. TICKET-103 seulement à moitié corrigé**
- [exécuté, scénario C] Un fork au tour 2 d'une save où un événement planifié s'est déclenché au tour 5 copie quand même
  ce déclenchement (`fired_turn_id>2` : 1 ligne). `storage_registry.py:376-384` copie `Fired_Scheduled_Events` sans
  filtre. `Session_Lore` (`:362-375`) et `Facts` sont bien filtrés.
- Conséquence : dans la save forkée, l'événement ne se déclenchera jamais.
- Correction : `AND fired_turn_id <= ?`, ce qui est justement la colonne déclarée dans le registre.

**I-3. Le registre n'est pas encore « déclaratif » : le fork reste une liste de cas codés à la main**
- [lu] `execute_fork` (`storage_registry.py:350-398`) contient un `if/elif` par nom de table (Timeline, Session_Lore,
  Fired…, Facts). Les tables `STEP_KEYED` qui ne sont pas dans cette liste (`Snapshots`, `Modifier_Snapshots`, `State_Cache`)
  ne sont pas copiées par la politique (State_Cache et Snapshots sont reconstruits par `fork_save`). `get_runtime_tables()`
  garde un `preferred_order` écrit à la main (`:238-254`). Le rewind exclut `State_Cache` par son nom (`:313`).
  `Item_Instances` n'a pas de handler (rembobiné en douce par `_rewind_inventory`).
- Le `[storage]` des manifestes de mods (`mods/*/mod.toml`) est lu (`axiom/kernel/manifest.py:222`) mais **aucun code
  ne le consomme** (grep `manifest.storage` vide). Les politiques déclarées par les mods sont donc décoratives.
- Les mods enregistrent leurs handlers dans une **liste globale** (`register_custom_storage`, `:415-428`) sans passer par
  `ModContext`. Désactiver le mod ne les retire pas (D11). Leurs noms (`assets`, `vector_store`) se retrouvent dans
  `get_runtime_tables()` (exécuté, scénario D) : sans conséquence aujourd'hui grâce au test `sqlite_master` de `package.py`.
- Pas de **snapshots par mod** (§10.2) : un seul `Snapshots.state_json` global. Pas de crochets `on_export`/`on_import`.
- Garde-fou : D7, D11, §10.2.
- Conséquence : la classe de bugs « on a oublié une table » (088, 089, 103) peut revenir. Chaque nouvelle table doit
  encore être prévue dans du code, pas seulement déclarée.
- Correction : `STEP_KEYED` doit suffire (copie `WHERE step_column <= at_turn` avec les colonnes déclarées, ids régénérés
  quand c'est un AUTOINCREMENT). Brancher `manifest.storage` sur le registre, avec désinscription via `ModContext`.

**I-4. 0b incomplet : l'auto-canonize est toujours dans les interfaces, en double**
- [lu] Qt : `tabletop_view.py:870` puis `_maybe_auto_canonize` (`:1179-1192`). Web : `web/app.js:1410, 1436, 4310`
  (`maybeAutoCanonize`). Il n'y a rien dans `Session._post_turn_pipeline` (`session.py:587-630`), donc la CLI n'en
  bénéficie pas. Le CHANGELOG 0b n'en parle même pas.
- Code mort laissé dans Qt : `_run_fact_extraction` (`tabletop_view.py:1235-1284`) et `workers/fact_worker.py`.
- Garde-fou : D4, D5 (le DOC cite précisément ce cas : « auto-canonize, Qt seulement »).
- Conséquence : la même règle de jeu est codée deux fois, avec deux comportements possibles, et la CLI n'a pas de canon auto.
- Correction : mettre un réglage `auto_canonize` dans la config et un post-commit dans `Session` (ou un hook
  `after_step` d'un mod). Les UI n'affichent plus qu'un interrupteur.

**I-5. Le harnais golden ne compare qu'une partie de l'état, et il n'est pas hermétique**
- [lu] `SessionStateCanonicalizer.canonicalize` (`axiom/testing/golden_harness.py`) compare les entités, l'inventaire,
  les modifiers, le Session_Lore, l'heure et l'Event_Log. Il **ignore** Facts, Observations, Mental_Models, Timeline,
  Fired_Scheduled_Events, Snapshots, Item_Definitions et ChromaDB. C'est pour ça qu'il ne voit ni B-1 ni I-2.
- [lu] `tests/test_golden_step.py:296-300` forke au tour 8 **après** être revenu au tour 8. Le fork « au milieu » de la
  partie (le cas de TICKET-103) n'est jamais testé. Il n'y a pas d'export « définition seule » (`pack_universe`).
- [exécuté] `test_session_epoch_bump_and_stale_worker_discard` est vide de sens : le faux LLM est épuisé, donc
  `distil_narrative_to_memory` renvoie 0 fait **même sans aucune époque** (scénario E : `facts_stored: 0` sans garde).
- [lu] Le fixture ne fait que `paths.configure(data_dir=…)` sans `config_dir` (`test_golden_step.py:39`). Le test lit
  donc le vrai `~/.config/AxiomAI/settings.json` (mods activés, mode mémoire…). Il charge aussi tous les mods de
  `mods/`, y compris `community.survival` (vu au chargement pendant mes runs).
- Point positif : le harnais protège bien le découpage de 0f, puisqu'il passe par `Session` et donc par le pipeline du
  mod `axiom.turn`.
- Conséquence : le « filet de sécurité » ne garantit l'absence de dérive que sur une partie des données de partie.
- Correction : canonicaliser **toutes** les tables `is_runtime` du registre (c'est son rôle), plus le nombre de chunks
  Chroma par tour ; ajouter un fork à mi-partie ; isoler `config_dir` ; refaire le test d'époque avec un LLM qui renvoie
  vraiment des faits.

**I-6. Le tour avale toutes les erreurs des mods : les UI perdent le type d'erreur et un tour peut être validé à moitié**
- [exécuté, scénario A] Un `LLMConnectionError` ressort de `take_turn` sous la forme
  `RuntimeError("Turn pipeline mod returned no result.")`. En effet `KernelRegistry.invoke_hook`
  (`axiom/kernel/registry.py:88-102`) avale toute exception sauf `GenerationCancelled`.
  `workers/narrative_worker.py:96` et `axiom/cli/play.py:263` ont un message dédié à `LLMConnectionError`, qui
  n'est donc plus jamais affiché.
- [lu] Inversement, si un hook `axiom.step:after_step` plante (par exemple celui de `axiom.time`, qui ajoute la Timeline,
  `mods/axiom.time/main.py:85-95`), l'erreur est journalisée et le tour est **commité quand même** sans cette partie.
- Garde-fou : 0d (le tour est tout ou rien) entre en tension avec l'« isolation des plantages ».
- Conséquence : le joueur voit « erreur inattendue » au lieu de « LLM injoignable, vérifiez votre clé ». Et un mod
  défaillant peut produire des tours incohérents (temps qui n'avance plus) sans que la partie s'arrête.
- Correction : relancer l'exception d'origine pour le hook `axiom.kernel:execute_step`. Pour les hooks *dans* le tour,
  choisir explicitement : soit annuler le tour, soit désactiver le mod fautif et prévenir. Ne pas tout avaler en silence.

**I-7. « Aucune écriture SQL pendant le tour » n'est pas tout à fait vrai**
- [exécuté, scénario B] Si le tour plante après le LLM (étape 6), `Event_Log` et `Session_Lore` restent propres. En
  revanche `Item_Definitions` contient l'objet `mystery_orb` inventé par le tour avorté. La cause est
  `ensure_item_definition` + `conn.commit()` pendant la validation d'inventaire (`arbitrator.py:1910-1952`).
- Autres écritures hors tampon après le commit, donc acceptables mais à savoir : `Saves.last_updated`
  (`session.py:598-607`), snapshot périodique, Chronicler (post-commit, `mods/axiom.time/main.py:~133`).
- Conséquence : un tour annulé peut laisser une définition d'objet dans la save, et un rewind ne l'efface pas, car c'est
  une table de définition.
- Correction : mettre la création de définition d'objet dans le tampon (`write_batch`).

**I-8. TICKET-104 non corrigé, et TICKET-100 seulement à moitié**
- [lu] `axiom/regenerate.py` est **inchangé** (`git diff main...HEAD -- axiom/regenerate.py` vide). La consigne remplacée
  (l.75-79) n'existe toujours pas dans `prompts.py:57`. Le JSON est donc encore stocké dans les variantes.
- [lu] `axiom/memory.py:239` utilise toujours `doc_id = str(uuid.uuid4())`. Le rejeu sans doublon dépend entièrement du
  rollback du mod `axiom.rag`, et ce rollback tourne **à l'intérieur** de la transaction SQL du rewind
  (`checkpoint.py:79-81` → `storage_registry.py:323-325`). Si la partie SQL échoue ensuite, Chroma est déjà rembobinée.
- `PENDING.md` et `Mods/TODO.md` (section « Préalable », décision D-1) laissent TICKET-100→105 **non cochés**, alors que
  certains sont corrigés. Aucune trace de quoi est fait et quoi ne l'est pas.
- Correction : appliquer la piste de TICKET-104. Utiliser des ids déterministes `"{save}:{turn}:{type}:{idx}"` avec
  `upsert`. Rembobiner Chroma **après** le commit SQL. Mettre à jour PENDING/TODO ticket par ticket.

### MINEUR

- **m-1. Fork des modifiers** [lu] : `storage_registry.py:98-102`. Si `modifiers_at` renvoie `[]`, ce qui veut dire
  « aucun modifier à ce tour » (doc de `modifiers.py:374-377`), le code recopie les modifiers **actuels**. Un buff futur
  fuit donc dans la copie. → supprimer ce repli.
- **m-2. Croyances au fork** [lu] : `_fork_observations` et `_fork_mental_models` filtrent sur `updated_turn_id <= at_turn`.
  Une croyance créée avant le point de fork mais mise à jour après disparaît, au lieu d'être remise dans son état d'alors.
  → copier puis appliquer `rollback_observations` à la copie.
- **m-3. `apply_mod_migrations` n'est utilisé nulle part** (grep : seulement `schema.py` et des tests). Aucun mod ne
  déclare de version de schéma. `Mod_Schema_Versions` est classée « définition » (`storage_registry.py:178`) : elle est
  copiée depuis l'univers et n'est pas purgée à l'export. Les étapes ne sont pas des transactions séparées (`with conn`
  imbriqué dans `get_connection`, donc tout ou rien) [lu]. → câbler au chargeur, et ranger la table côté save.
- **m-4. 0e** : `[mods.<id>]` est devenu la clé JSON `mod_settings` (l'alias `mods` est lu, puis réécrit en
  `mod_settings`). Les autres clés inconnues sont toujours effacées (exécuté : `future_core_key` perdu). C'est conforme
  à la lettre de l'arbitrage (rang 18), ça mérite juste d'être documenté.
- **m-5. 0f, deux orchestrations du même tour** [lu] : `ArbitratorEngine.process_turn` (`arbitrator.py:261-321`, encore
  utilisé par `axiom/multiplayer.py:81` et par `test_arbitrator.py`) et `mods/axiom.turn/main.py:38-169`. Les 50 tests de
  `test_arbitrator` testent donc le chemin « sans registre », qui n'est pas celui joué en production. Le hook
  `axiom.step:gather_context` est déclenché **deux fois** par tour (`arbitrator.py:502` **et** `axiom.turn/main.py:82`).
  `step_1` (180 lignes) et `step_5` (201 lignes) restent des blocs monolithiques. Le tour vit toujours en pratique dans
  `axiom/arbitrator.py` (1955 lignes, dans le moteur) ; le mod `axiom.turn` n'est qu'un emballage de 177 lignes.
- **m-6. Époques** : la vérification puis l'écriture ne sont pas atomiques (petite fenêtre de course,
  `living_memory.py:~65-76`). `run_extract_now` (bouton « extraire maintenant ») n'a pas de garde d'époque.
  `Session.fork()` incrémente l'époque de la save **source** sans raison (annule à tort un job en cours).
  `TurnContext` n'a ni `epoch` ni `llm`, donc `on_after_step` du mod mémoire passe `None`, ce que rattrape
  `spawn_distillation`.
- **m-7. Scaffold et créateur LLM** : les modèles générés s'abonnent à `axiom.turn:after_step` (`axiom/kernel/scaffold.py:150, 180`,
  `llm_creator.py:81, 104`), alors que le moteur déclenche `axiom.step:after_step`. Un mod généré ne sera jamais appelé
  (hors périmètre phase 0, signalé pour la revue phase 4).
- **m-8.** Le docstring de `CheckpointManager.rewind` dit encore que Chroma est « rollée par l'appelant » (`checkpoint.py:62-63`).
  `axiom test --golden` lance `pytest tests/test_golden_step.py` avec un chemin relatif (`axiom/cli/test.py:50`), ce qui
  ne marche pas depuis le paquet installé.

---

## 4. Écarts entre la doc/TODO et le code

| Affirmation (doc de Frosoore) | Réalité |
|---|---|
| `Mods/TODO.md` : 0a→0f `[x]` | 0b partiel (I-4), 0c partiel (B-1, B-2, I-3), 0e partiel (m-3) |
| `phase-0c/CHANGELOG` : « éliminant le bug historique TICKET-089 » ; TODO « Unifier le Fork » | 089 : vrai. Mais le fork perd Facts, Observations et Mental_Models (B-1), et 103 n'est qu'à moitié corrigé (I-2) |
| `phase-0c/TODO` : « Supprimer les DELETE éparpillés », rewind unique | Vrai dans `checkpoint.py`, mais Qt garde son propre enchaînement de rewind (B-2) |
| `phase-0d/DOC` : « Aucune écriture SQL directe pendant la génération du tour » | `Item_Definitions` est écrit pendant la validation (I-7, exécuté) |
| `phase-0d/CHANGELOG` : test « rejet des écritures des workers obsolètes » | Le test passerait même sans garde d'époque (I-5, exécuté) |
| `phase-0b/TODO` : « Éviter la duplication… tabletop_view » | Mémoire living : oui. Auto-canonize : toujours dans Qt et dans le web, jamais mentionné (I-4) |
| `phase-0a/DOC` : banc « hermétique » | Il lit la config utilisateur réelle et charge tous les mods de `mods/` (I-5) |
| `phase-0e/TODO` : migrations de mods | L'exécuteur existe mais n'est branché nulle part (m-3) |
| `phase-0f/CHANGELOG` : parité vérifiée par `test_arbitrator` | `test_arbitrator` teste `process_turn`, qui n'est pas le chemin du mod `axiom.turn` (m-5) |
| `Mods/TODO.md` « Préalable » TICKET-100→105 | Toujours décochés et `PENDING.md` les dit « ouvert ». En réalité 101 corrigé, 105 sans objet (I-1), 100 à moitié, 102 à moitié (web oui, Qt non), 103 à moitié, 104 non |
| Coordination D-6 (propriétaire unique de `arbitrator.py`/`session.py`, Multiplayer gelé avant 0f) | Toujours décoché dans TODO, aucune trace dans `maintenance/collab/` (ls) |

---

## 5. Questions pour Frosoore / le propriétaire

1. **Erreurs de mods dans le tour (I-6)** : quand un mod plante pendant un tour, on préfère annuler tout le tour
   (cohérence) ou continuer sans lui (robustesse) ? Aujourd'hui c'est « continuer en silence », y compris pour les
   erreurs du LLM. Décision utilisateur à tracer en §14.
2. **Correction du narrateur (I-1)** : la perte de l'indice était-elle voulue ? Sinon, d'accord pour la stocker comme
   donnée de save, ce qui la rend rembobinable ?
3. **Rewind Qt (B-2)** : la sauvegarde auto avant rewind n'existe que dans Qt. On la met dans le chemin moteur unique
   (donc aussi pour le web et la CLI) ?
4. **Auto-canonize (I-4)** : doit-il devenir un réglage moteur ou un mod `after_step` ? Qui le porte ?
5. **Préalable D-1** : pourquoi TICKET-100→105 n'ont-ils pas été traités comme tickets (statut, preuve, test) avant la
   phase 0 ? Peut-on mettre à jour `PENDING.md` ticket par ticket avec les constats ci-dessus ?
6. **D-6** : la coordination sur `arbitrator.py`/`session.py` et le gel de Multiplayer ont-ils été décidés quelque part ?
