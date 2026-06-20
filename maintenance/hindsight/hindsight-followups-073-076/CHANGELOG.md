# CHANGELOG — Hindsight follow-ups 073/074/075/076

## 2026-06-19 — Démarrage
- Création de l'étape (DOC/TODO/CHANGELOG). Périmètre = cluster Hindsight choisi par l'utilisateur.
- Lecture approfondie : `axiom/memory.py` (focus_terms, scoring), `axiom/arbitrator.py`
  (`process_turn`, `_identify_relevant_entities`, build de `id_to_name` après la requête RAG),
  fixtures `tests/test_arbitrator.py`. TICKET-073 confirmé : la map id→nom est bien construite
  après la requête → réordonnancement maîtrisé requis.

### TICKET-073 — Focus boost noms persos ✅
- `arbitrator.process_turn` : la lecture `Entities` (id→nom/type) + `player_persona` (une seule
  connexion) est **remontée avant la requête RAG** (elle ne dépendait ni du RAG ni de `filtered_stats`).
  L'ancien bloc, désormais en double après `filtered_stats`, est retiré (remplacé par un commentaire
  pointeur). Zéro round-trip ajouté.
- `focus_terms` passe de `[lieu]` à `[lieu] + noms des persos partageant le lieu` : balayage de
  `all_stats` (location match, non filtré), noms via `id_to_name`, joueur exclu, **cap
  `_FOCUS_SCENE_CHARACTER_CAP=5`** (constante module, le lieu est toujours gardé en plus).
- Tests `tests/test_arbitrator.py` : `test_focus_terms_include_location_and_on_scene_names`
  (lieu + nom NPC présents, nom joueur exclu) + `test_focus_terms_exclude_characters_elsewhere`
  (NPC ailleurs absent → `["Forest"]`). **43/43 verts.**

### Investigation rewind (074/075) — constats
- `checkpoint.rewind` purge par `turn_id > N` : Event_Log, Snapshots, Timeline, Facts, Observations.
- **Modifiers (074) ne sont NI event-sourcés NI snapshotés** (`saves.py:105` « current state »), et
  **jamais créés en jeu** : `add_modifier` n'est appelé que par les tests + le chargement de save
  (`saves.py`). Le tick les décrémente en minutes et les **hard-delete** à expiration. → restaurer
  l'état au tour N exige de réintroduire un historique = décision d'archi (présentée à l'utilisateur).
- Round-trips save/package : copies **explicites par colonne** (`savestore._RUNTIME_COPY`, `saves.py`)
  + purge column-agnostic (`package._RUNTIME_TABLES`) → un ajout de colonne est sûr.

### TICKET-075 — Rewind « dé-tire » les Fired_Scheduled_Events ✅
- `schema.py` : colonne **`fired_turn_id INTEGER NOT NULL DEFAULT 0`** ajoutée au DDL +
  **`ensure_fired_event_turn_column(conn)`** (PRAGMA table_info → ALTER si absente, in-transaction,
  mirror `ensure_facts_table`). Legacy rows (défaut 0) → restent tirés (choix conservateur).
- `arbitrator._mark_event_as_fired(save_id, event_id, fired_turn_id)` : signature + ensure + INSERT
  avec le tour ; appelé avec `turn_id` (ligne 645).
- `checkpoint.rewind` : ensure + `DELETE FROM Fired_Scheduled_Events WHERE save_id=? AND
  fired_turn_id > ?` dans la même transaction. Sémantique : rewind = l'événement peut se redéclencher
  quand l'horloge re-franchit sa minute.
- Tests : `test_checkpoint.py::TestRewindUnfiresScheduledEvents` (futur dé-tiré / passé gardé / legacy
  gardé) + `test_arbitrator.py::TestScheduledEventFiring` (tag du tour). Round-trips save/package
  re-vérifiés (97 verts). **59 + 97 verts.**

### TICKET-074 — Rewind restaure les Active_Modifiers ✅ (décision user : Option A, snapshot par tour)
- `schema.py` : table **`Modifier_Snapshots(save_id, turn_id, state_json)`** (PK save+turn, FK Saves
  CASCADE, template `Snapshots`) + DDL enregistré (`_ALL_DDL`, `EXPECTED_TABLES`) +
  **`ensure_modifier_snapshots_table(conn)`** (auto-migration in-transaction).
- `modifiers.py` : **`ModifierProcessor.snapshot_modifiers(save_id, turn_id)`** capture l'état post-tick
  (no-op si aucun modifier → pas de lignes vides ; absence de ligne = « aucun modifier ce tour-là ») ;
  **`rollback_modifiers(conn, save_id, target_turn_id)`** (module-level, mirror `rollback_observations`) :
  purge les snapshots > N, vide `Active_Modifiers` du save, re-matérialise l'état du tour N (ou rien).
- `arbitrator.process_turn` : `snapshot_modifiers(save_id, turn_id)` après `tick_modifiers`.
- `checkpoint.rewind` : `rollback_modifiers(conn, …)` dans la transaction de rewind (atomique avec
  events/facts/croyances/fired).
- Round-trips : `Modifier_Snapshots` ajouté à `savestore._RUNTIME_COPY` (copie explicite, skip si table
  absente) et `package._RUNTIME_TABLES` (purge gardée par existence).
- **Limite documentée** : une save chargée avec des modifiers puis rembobinée au tour 0 (avant tout tour
  joué/snapshoté) est vidée — cohérent avec « rewind-to-0 nettoie tout ».
- Tests : `test_checkpoint.py::TestRewindRestoresModifiers` (restaure l'état décrémenté du tour N /
  modifier absent au tour N effacé / snapshots futurs purgés) + `test_modifier_processor.py::
  TestSnapshotModifiers` (no-op si vide / écrit si présent). **82 verts** (modifier+checkpoint+saves+pkg).

### TICKET-076 — Retrait du résidu legacy `chronicler_interval` ✅
- Grep exhaustif : le champ (en *tours*) n'est lu **nulle part** pour le déclenchement (le Chronicler
  passe par `chronicler_minutes_interval` en *minutes* depuis TICKET-018). Seules réfs : définition
  config + docstring, préservation GUI `collect_config`, asserts de tests.
- **Retiré** : `AppConfig.chronicler_interval` (champ + ligne docstring, remplacée par un commentaire
  expliquant pourquoi un vieux settings ne casse pas). `load_config` filtre déjà les clés inconnues
  (ligne 305-307) → **aucune migration requise**, les anciens `settings.json` se chargent proprement.
- `ui/settings_dialog.py` : retrait de la préservation `chronicler_interval=getattr(...)` dans
  `collect_config` + de la ref `self._loaded_config` (devenue inutile, seule cette préservation
  l'utilisait).
- `tests/test_config.py` : 3 réfs au champ retiré remplacées par d'autres champs (`rag_chunk_count`,
  `chronicler_minutes_interval`) pour préserver la couverture « champ int chargé/round-trippé ».
- Tests : config 29 verts + settings_dialog 14 verts. `test_unknown_keys_ignored` (qui garantit le
  filtrage gracieux) reste vert → la rétro-compat des vieux settings est couverte.

## Cluster Hindsight 073/074/075/076 COMPLET. Non commité (attente feu vert).

### Doc Sphinx du moteur mise à jour (2026-06-19)
**EN (source) :**
- `docs/guides/saves.md` : section « Rewind and checkpoints » étoffée — rewind décrit comme complet
  (events/State_Cache/Timeline/Snapshots/faits/croyances + **modifiers** restaurés du snapshot par tour
  [074] + événements programmés **dé-tirés** [075]) ; précision que le store vectoriel roule séparément
  via `VectorMemory.rollback`.
- `docs/guides/memory.md` : focus boost (073) reformulé (lieu + noms des persos en scène).
- `axiom/checkpoint.py` : docstring de `CheckpointManager.rewind` réécrite (procédure complète, rendue
  par `automodule`). Pages API `automodule` (modifiers/checkpoint/config) régénérées : `chronicler_interval`
  disparaît (076), `snapshot_modifiers`/`rollback_modifiers` apparaissent.
- Build EN strict `sphinx -W` = EXIT 0, zéro warning.

**FR (rattrapage Tier 1, décision user) :**
- Découverte : mon 1ᵉʳ comptage (`grep '^msgstr ""$'`) était faux (comptait les entrées multi-lignes
  traduites comme vides). Vrai état : les **guides étaient déjà traduits** (juin), seul le **guide mémoire
  entier** (`guides/memory.po`, 57 chaînes, fichier absent) et **1 puce accueil** + mes **5 ajouts rewind**
  (`saves.po`) manquaient.
- Traduit : `guides/memory.po` (intégral), `guides/saves.po` (5 ajouts rewind), `index.po` (puce mémoire).
- **Narratif (guides + accueil + quickstart) = 100 % FR** (0 chaîne restante). **Réf API laissée EN** (choix
  TICKET-058 ; ~265 chaînes autodoc non traduites par décision).
- `.po` API resynchronisés avec la source par `sphinx-intl update` (nouvelles entrées EN-fallback). `.mo`
  non suivis par git (régénérés au build). Build **FR strict `sphinx -W` = EXIT 0**.
- `conf.py` : intersphinx neutralisé le temps des builds offline (machine bloque sur le réseau), **restauré**.
