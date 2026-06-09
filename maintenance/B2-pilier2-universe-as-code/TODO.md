# TODO — B2 · Pilier 2 : Universe-as-Code (doc §7 + annexe C.1)

> Définir un univers comme une **arborescence de fichiers texte** (TOML/MD) versionnable,
> le `.db` SQLite devenant un **cache compilé**. Le texte est la vérité, le `.db` est dérivé.

## Périmètre de CE lot (MVP cœur — validé 2026-06-09)

✅ inclus : compiler, decompiler, CLI `compile`/`decompile`, packaging `.axiom` v2 + compat v1, tests round-trip.
⏸ différé (tickets/sessions à part) :
- Intégration Creator Studio (Qt) → lire/écrire l'arbo. **Quand on y touchera : logique dans `axiom/`, worker Qt = coquille fine** (règle ARCHITECTURE.md).
- Hot reload `axiom dev` (watch FS + recompile incrémentale).
- §7.6 — séparer les saves dans `saves/` distinct du `.db` univers (touche `Session`, zone de collision).
- Migration des `Populate*Task` (db_tasks.py, authoring LLM) vers `axiom/compile.py`.

## Décisions actées
- **Writer TOML : `tomlkit`** (style-preserving — utile pour le futur Creator Studio qui réécrira des fichiers édités à la main). Lecture via `tomllib` (stdlib).
- Saves : restent dans le `.db` pour ce lot (séparation différée).

## Frontière définition / runtime (base du découpage)
- **Définition → arbo texte** : `Universe_Meta`, `Entities`, `Entity_Stats`, `Rules`, `Stat_Definitions`,
  `Lore_Book`, `Global_Personas`, `Scheduled_Events`, `Item_Definitions`, `Story_Setup`,
  `Locations`, `Location_Connections`.
- **Runtime/save → reste binaire (jamais dans l'arbo)** : `Saves`, `Event_Log`, `State_Cache`,
  `Snapshots`, `Timeline`, `Fired_Scheduled_Events`, `Items_Inventory`, `Active_Modifiers`.

---

## Phase 0 — Setup
- [x] Ajouter `tomlkit` à `requirements.txt` + installer dans `.venv`
- [x] Créer `maintenance/B2-pilier2-universe-as-code/{TODO,CHANGELOG,DOC}.md`
- [x] Déclarer les fichiers touchés dans `maintenance/collab/claude/EN_COURS.md`
- [x] Référencer l'étape dans `maintenance/README.md`

## Phase 1 — Compiler (`axiom/compile.py`) : arbo texte → `.db` ✅
- [x] `hash_directory(src_dir)` (hash stable du contenu source, ignore `.axiom-cache`/`.git`)
- [x] Cache check : `.axiom-cache/cache_hash.txt` ; skip si inchangé (sauf `force=True`)
- [x] Parsers (tolérants aux fichiers/dossiers absents) :
  - [x] `universe.toml` → `Universe_Meta` (meta, narrative, calendar, companion, `[extra]` passthrough) + résolution des `*_file`
  - [x] `stats/definitions.toml` → `Stat_Definitions`
  - [x] `entities/*.toml` → `Entities` + `Entity_Stats` (ignore `_index.toml`)
  - [x] `rules/*.toml` → `Rules` (conditions/actions en JSON)
  - [x] `locations/map.toml` → `Locations` + `Location_Connections`
  - [x] `lore/**/*.md` → `Lore_Book` (frontmatter TOML `+++…+++`, exclut les `*_file`)
  - [x] `events/*.toml` → `Scheduled_Events`
  - [x] `setup/questions.toml` → `Story_Setup`
  - [x] `items/*.toml` → `Item_Definitions`
  - [x] ~~personas~~ : `Global_Personas` est dans la **DB globale**, hors univers → écarté du périmètre
- [x] `compile_universe(...)` orchestrateur (build atomique tmp + WAL checkpoint + rename, écrit le hash)
- [x] Erreurs claires (`CompileError` : TOML malformé, champ requis manquant)

## Phase 2 — Decompiler (`axiom/decompile.py`) : `.db` → arbo texte ✅
- [x] `decompile_universe(db_path, output_dir)` + `read_definition(db)` (lecteur normalisé partagé)
- [x] Préserve entity_ids, rule_ids, calendrier, lore complet, locations+connections, events, setup, items
- [x] Lore/narratifs → fichiers `.md` dédiés + référence depuis `universe.toml` ; normalisation LF déterministe
- [x] Génère un `.gitignore` (`.axiom-cache/`)

## Phase 3 — CLI (`axiom/cli/`) ✅
- [x] `axiom compile <src_dir> [-o out.db] [--force]`
- [x] `axiom decompile <universe.db> <output_dir>`
- [x] (bonus) `axiom pack` / `axiom import`
- [x] Câblé dans `axiom/cli/main.py` (via `axiom/cli/compile_cmd.py`)

## Phase 4 — Format `.axiom` v2 + compat v1 (`axiom/package.py`) ✅
- [x] Packaging v2 : zip {arbo texte + `.axiom-cache/universe.db`}
- [x] Import v2 : décompresse, hash OK → `.db` embarqué, sinon recompile
- [x] Compat v1 (zip de JSON) : `detect_format` → JSON → `.db` → `decompile` → `compile` v2
- [x] **Cœur dans `axiom/` (zéro Qt).**
- [ ] ⏸ Rewire du worker `import_export_worker.py` (Qt) en coquille fine appelant `axiom.package` — différé

## Phase 5 — Tests ✅
- [x] Fixture : arbo source riche (toutes les tables)
- [x] Round-trip `texte → .db → texte → .db` : égalité sémantique des définitions
- [x] `decompile` d'un `.db` réel → `compile` → égalité (ids préservés) + validé sur `ST_Aglae.db`
- [x] Garde-fous : `test_engine_headless` + `test_cli_play` + `debug/startup_check.py` verts
- [x] Round-trip `.axiom` v2 pack/unpack + import v1→v2 + CLI

## Mise à jour ARCHITECTURE.md
- [ ] (à faire au rewire du worker) ajuster la ligne « Construction d'univers » : `axiom/compile.py` existe
      désormais ; `Populate*` (authoring LLM) reste côté app (chantier distinct)

---

## Phase 6 — Saves éditables (édition par-dessus le journal, LLM & humain) ✅ (1er jet)

> **Implémenté 2026-06-09** : `axiom/saves.py` (`materialize_state`, `resolve_point` tour+minute,
> `export_save_state`/`import_save_state`, `fork_save`) + CLI `save-show`/`-export`/`-import`/`-fork`
> (`axiom/cli/saves_cmd.py`) + `EventSourcer.state_at` (replay pur, tour 0 inclus). Tests :
> `tests/test_saves_editing.py` (14, verts) — matérialisation tour/minute, export↔import, save
> importée **jouable** (`Session`), fork (journal tronqué, source intacte, rewind OK), FK invalide.
> **Bug corrigé en chemin** : `get_events` excluait le tour 0 → `state_at`/`take_snapshot` ratait les
> events « genesis » (snapshot vide). Corrigé (`start_turn_id=-1`).
> **Hors 1er jet** : `apply_correction` sur save existante (couvert pour l'instant par export→édition→
> import = nouvelle save) ; modifiers exclus du format (TICKET-024, `Active_Modifiers` sans `save_id`).

### (référence) Cadrage initial — décisions



> Demande utilisateur (2026-06-09). **Décisions arrêtées** (explications dans CHANGELOG/échange) :
> - **D1 — Modèle** : on **garde le journal `Event_Log`** comme source de vérité (il fait tourner le
>   rewind). L'édition se fait **par-dessus** : (a) **découpe/fork** à un point choisi, (b) **événements
>   de correction** append-only. PAS d'édition directe des snapshots (dérivés → contradictions).
> - **D2 — Emplacement** : cible = **dossier `saves/` séparé** (§7.6). **Différé** (touche `Session`) →
>   chantier dédié ; pour le 1er jet, on peut rester dans le `.db`.
> - **D3 — Mémoire vectorielle** : save importée = **mémoire vide** (se remplit en jouant ; correct car
>   pas de passé joué à repêcher ; évite le coût/risque torch sur carte AMD). Pas de ré-embed à l'import.

### Constat
Save = `Saves` + `Event_Log` (journal, **vérité**) + `State_Cache`/`Snapshots` (dérivés, recalculables)
+ `Timeline`, `Items_Inventory`, `Active_Modifiers`, `Fired_Scheduled_Events`. Le rewind rejoue/charge
déjà l'état à un tour donné (`Session.rewind`, `axiom/checkpoint.py`, table `Snapshots`).

### Concept retenu : « éditeur de timeline » (découpe + corrections)
1. **Lire** : matérialiser l'état du monde à un point donné (tour N / minute M / « il y a 1h ») en
   rejouant le journal — réutilise la mécanique de rewind. Vue lisible (TOML) pour humain/LLM.
2. **Découper / forker** : créer une nouvelle save = journal tronqué jusqu'au point choisi. Sûr (pas de
   contradiction : on ne fait que rejouer jusqu'au point).
3. **Corriger** : ajouter un **événement de correction** au point choisi (« édition : Health→100, +1 épée »)
   plutôt que de réécrire le passé. Journal cohérent + append-only, rewind préservé, édition tracée.

### API moteur visée (`axiom/saves.py`, zéro Qt) — à détailler au cadrage
- `materialize_state(db, save_id, at_turn|at_minute) -> dict` : état à un point (via replay).
- `fork_save(db, save_id, at_point) -> new_save_id` : nouvelle save = journal tronqué.
- `apply_correction(db, save_id, patch)` : ajoute un event de correction (state_set/items/modifiers).
- Vue éditable : export/import d'un `save_state.toml` (l'état + le patch) ⇄ événement de correction.
- CLI : `axiom save-show`, `axiom save-fork`, `axiom save-edit` (noms à fixer).

### Sélecteurs de point (idée utilisateur)
Découpe par **tour** (`turn<=3`), par **temps in-game** (`<=15min`), ou relatif (`jusqu'à il y a 1h`).
NB : le rewind est aujourd'hui par **tour** ; le faire fonctionner en **minutes** = follow-up Pilier 5.

### Risques / garde-fous
- Touche le modèle de save (event-sourcing) → zone sensible. Tests dédiés : `materialize_state` ==
  état réel après replay ; `fork` puis `Session.take_turn` (save jouable) ; correction → état attendu ;
  rewind toujours fonctionnel après édition.
- Feature **additive** : ne pas casser les saves binaires existantes.

### À cadrer avant code
- Forme exacte du `save_state.toml` (vue) et du « patch » de correction.
- Faut-il un sélecteur par minutes dès maintenant (sinon tour seulement) ?
