# Audit « sans pitié » des affirmations du chantier mods (2026-10-03)

> Objet : vérifier **dans le code**, pas dans les cases cochées, ce que `TODO.md`, `ETAT_REEL.md`,
> `CHANGELOG.md` et `corrections-2026-10/` déclarent fait. Base : branche `mods`, commit `8558860`
> **+ le travail non commité** (45 fichiers modifiés, 7 nouveaux), qui contient la deuxième vague
> (« lot E », K9, K10, M3, M5, M6, P2, DOC2).
> Méthode : lecture du code, sondes exécutées (scripts et tests jetables dans le scratchpad, rien
> d'ajouté au repo), suite complète relancée comme la CI, avec config et données isolées. Le
> `settings.json` réel n'a pas bougé : même empreinte md5 avant et après.

## 1. Verdict en une page

- **Les lots A et C (tests hermétiques, noyau/chargeur, patches, créateur LLM) tiennent** : vérifiés
  dans le code et par sondes.
- **Le lot B1/B2 est en grande partie réel.** Le fork garde la mémoire vivante (088 vérifié par
  sonde), 103 est filtré, le rewind Qt passe par le chemin moteur, la boucle de correction est
  rétablie et les erreurs LLM remontent. Mais plusieurs points n'ont **aucun test** (088,
  migrations, époques, 0d, rollback Chroma après commit).
- **La deuxième vague, non commitée, est en partie fausse ou trompeuse :**
  1. **« Lot E — proxys nettoyés » a été obtenu à l'envers.** Le code des fonctionnalités a été
     **remis dans le noyau** (`axiom/inventory.py` +594 l., `living_memory.py` +746,
     `stat_dynamics.py` +627, `image_generator.py` +519, `time_system.py` +195), et les mods ne sont
     plus que des réexports de 8 lignes (`from axiom.inventory import *`). Le noyau n'importe plus
     `mods/`, mais il **contient et appelle directement** le code JDR, même quand le mod est décoché.
     C'est le contraire de D1/D3 et de M2, et cela annule aussi le TICKET-106, marqué « RÉSOLU »
     dans `PENDING.md`.
  2. **K9 « `[storage]` lu » est faux en substance.** Le chargeur enregistre des tables fantômes
     (`entities`, `rules`, `facts`, `events`…) et ignore la clé `table`. Plusieurs déclarations des
     manifestes officiels sont **dangereuses si on les applique un jour**. Exemple : `axiom.time`
     rattache `Scheduled_Events`, une table de **définition d'univers**, à un rewind indexé par
     minute. Aujourd'hui le tout est inerte **par chance** : les noms ne correspondent pas, à cause
     de la casse.
  3. **`ctx.store` a deux bugs** : un plantage reproductible, et `step=0` par défaut qui rend le
     rewind inopérant en silence. Il écrit **hors** de la transaction du tour.
  4. **M6 introduit un plantage** : une section de prompt en tuple `(id, position, texte)` venant
     d'un mod tiers **fait échouer tout le tour**. C'est une régression de l'isolation K6 obtenue
     par B2.
  5. **Écran des mods (Qt)** : des clés de traduction inexistantes s'affichent brutes
     (`mods_next_launch`…).
- **La suite de tests** : 1 216 réussis, **1 échec** (dépendant de l'ordre), 45 + 8 réussis dans les
  lots Qt et mods. Aucun segfault.
- **Le suivi est incohérent.** `TODO.md` coche des choses fausses (lot E, K9, M7, M2 reformulé à la
  baisse), et laisse décochées des choses faites (088, 102, 103). `PENDING.md` n'est pas à jour.

## 2. Résultats de la suite (même découpage que la CI, config et données isolées)

| Lot | Résultat |
|---|---|
| `tests/` hors Qt multimédia | **1 216 réussis, 1 échec** : `test_image_generator.py::test_session_integration_image_generation` |
| Qt multimédia (5 fichiers) | 45 réussis |
| `mods/*/tests` | 8 réussis |

- **L'échec dépend de l'ordre d'exécution** : le test passe seul et échoue après `test_arbitrator.py`
  (trouvé par bissection).
  - Cause : `mods/axiom.illustrations/main.py:16` fait `from axiom.config import load_config` à
    l'import. Le `patch("axiom.config.load_config")` du test n'a donc plus d'effet si le module a
    déjà été chargé par un test précédent.
  - Le même test **tente un vrai appel réseau** au Timekeeper (« Universal API unreachable »,
    `localhost`). Sur une machine avec Ollama lancé, il l'appellerait vraiment. L'hermétisme T3 est
    donc incomplet.
- **La CI ne serait pas verte.**

## 3. Point par point

Légende : ✅ vrai (vérifié) · 🟡 vrai mais incomplet ou non testé · ⚠ coché mais faux ou trompeur ·
🐞 bug introduit.

### 3.1 Préalables (TICKET-100 → 105, 088)

| Point | Déclaré | Constat dans le code | Verdict |
|---|---|---|---|
| 088 fork et mémoire vivante | TODO `[ ]`, B1 « corrigé » | Sonde : fork au tour 2 → 2 faits, 1 croyance, 1 modèle mental, et les `sources` sont remappées vers les nouveaux id. Plus de `uuid4` ni d'`except: pass` dans `storage_registry.py` | 🟡 **corrigé mais sans aucun test** ; TODO pas à jour |
| 100 ids Chroma | partiel | `chunk_id()` déterministe + `upsert` (`axiom/memory.py:160,266`) ; rollback Chroma après le commit (`checkpoint.py`, `execute_external_rewind`) | 🟡 ; aucun test de « Chroma pas touchée si le SQL échoue » |
| 101 | ✅ | non revérifié en détail, test existant vert | ✅ |
| 102 rewind Qt | TODO `[~]` | `RewindTask` (`workers/db_tasks.py:160`) appelle seulement `CheckpointManager.rewind` (époque, backup, SQL, puis stockages externes) | ✅ (TODO pas à jour) |
| 103 | TODO `[~]` | `Fired_Scheduled_Events` est STEP_KEYED sur `fired_turn_id`, testé (`test_ticket_104_and_exports.py`) | ✅ (TODO pas à jour) |
| 104 regenerate | ✅ | prompt de variante + `strip_json_block` + test | ✅. La 2ᵉ branche de remplacement (`regenerate.py`, « You MUST end your response… ») est du code mort : elle ne peut rien trouver après la 1ʳᵉ |
| 105 / M4 boucle de correction | ✅ | indice comme événement du tour (`CORRECTION_EVENT`), relu au tour N+1, rembobiné ; `axiom.inventory` transmet maintenant ses rejets | ✅ |

### 3.2 Phase 0

| Point | Déclaré | Constat | Verdict |
|---|---|---|---|
| 0a harnais golden « fork à mi-partie, vérification complète » | `[x]` | Le test « mi-partie » (`test_ticket_104_and_exports.py:106`) ne vérifie que `Event_Log`, `Facts` et `Fired_Scheduled_Events`. Il ne compare **pas** la save forkée à l'état de la source au tour N, et ne couvre ni croyances/modèles (le cœur de 088), ni `Mod_KV`, ni `State_Cache`, ni Chroma | ⚠ « complète » est faux |
| 0b fin de tour unique | `[x]` | Auto-canonize uniquement dans `Session._maybe_auto_canonize`, retiré de Qt et du web ✅. Restes Qt morts : `_fact_pending`/`_fact_turn_counter` (`tabletop_view.py:373,1089`), `_accumulate_and_maybe_extract` vide mais toujours appelé (`:1157`), `workers/fact_worker.py` toujours présent | 🟡 |
| 0c rewind unique + registre | `[x]` | Chemin unique ✅. Le registre des tables de jeu reste une **liste en dur dans le noyau** (`CORE_STORAGE_REGISTRY`, avec Facts, Observations, inventaire…), contrairement à §10.2 « aucune liste tenue à la main » | 🟡 |
| 0d tour transactionnel | `[x]` | Validation d'inventaire en lecture seule ✅ ; `guarded_write` atomique ✅. **Mais `ctx.store` (K9) écrit hors du `TurnWriteBatch`** (propre connexion + `commit`, `kv_store.py`) : un tour annulé garde les écritures `Mod_KV` du mod. Aucun test pour 0d ni pour les époques | ⚠ régression de principe introduite par K9 |
| 0e migrations | `[~]` | Appliquées à la création de save et à l'ouverture d'une `Session` (sonde : table créée puis colonne ajoutée, version 2 tracée) ✅. `[schema]` du manifeste non lu ; aucun test | 🟡 |
| 0f orchestration unique | `[x]` | `process_turn` passe par le hook `axiom.turn` ; `gather_context` appelé une fois | ✅ |

### 3.3 Phase 1 — noyau

| Point | Déclaré | Constat | Verdict |
|---|---|---|---|
| K1–K5, K7, K8, K13, K14 (lot C) | `[x]` | Conflits/cycles qui n'écartent que le fautif, statut réel, ordre utilisateur, `KERNEL_API`, `cleanup` réel, découverte absolue sans `dist/`, safe mode = aucun mod : vérifiés dans `loader.py`/`context.py` | ✅ |
| K6 isolation dans le tour | `[x]` | B2 l'avait réglé (sondes `probe.badfield`/`badsection` vertes). **M6 l'a cassé** : `_parse_prompt_section_item` (`mods/axiom.turn/main.py:122-131`) fait `int(...)` **hors** de `_call_contribution`. Sonde : un mod qui renvoie `("mon.mod", "system", "texte")` → `ValueError` → **tour entier en échec** | 🐞 |
| K9 `ctx.store` + `[storage]` lu | `[x]` | Voir §4.1 et §4.2 | ⚠ + 🐞 |
| K10 modpack dans la save | `[x]` | Écrit dans `Save_Meta` à `create_save` et embarqué dans `.axiomsave` ✅. Mais : (a) **pas de hash** (la vision demande ids + versions + hash) ; (b) l'**avertissement n'est qu'un `logger.warning`**, aucune UI ne l'affiche (`modpack_compatibility` lu nulle part) ; (c) **CLI : sonde → modpack vide** si aucun registre n'a encore été chargé, et `axiom play` crée la save avant la `Session` ; (d) `except Exception: pass` et `with sqlite3.connect(...)` non fermant (`savestore.py:244,250,518,522`), soit exactement la classe de bug Windows `WinError 32` déjà corrigée ailleurs ; (e) les exports `.axiom` (univers) n'embarquent pas de modpack | 🟡/⚠ |
| K11 API publique | `[x]` | Le nouveau mod `axiom.minimal_chat` lit encore `mod_ctx._registry` (`main.py:_resolve_llm`) | 🟡 |
| K12 noyau neutre | `[ ]` | Pire qu'avant : le noyau contient maintenant aussi tout le code des fonctionnalités | ❌ (honnêtement décoché) |

### 3.4 Phase 2 — mods officiels

| Point | Déclaré | Constat | Verdict |
|---|---|---|---|
| M1 noyau sans import de `mods/` | `[ ]` mais « Lot E `[x]` proxys nettoyés » | Plus aucun import de `mods/` dans `axiom/` ✅… parce que **le code a été remis dans `axiom/`**. Le noyau appelle directement l'inventaire (`saves.py:142-796`, `turn_batch.py:112`, `storage_registry.py:247`), les stats dynamiques (`compile.py:216`, `session.py:274`, `arbitrator.py:523`) et le temps (`compile.py`, `decompile.py`), **que le mod soit coché ou non**. Les UI aussi (`tabletop_view.py:53,1185`, `main_web.py:799,2055,2591,2611`) | ⚠ contraire de la vision |
| M2 « le tour est un mod » | reformulé en « orchestration du step » et coché | `arbitrator.py` (1 492 l.) reste dans le noyau ; le noyau teste toujours les mods par leur **nom** (`arbitrator.py:480` `mod_id == "axiom.living_memory"`, ajouté par cette vague) | ⚠ critère abaissé pour pouvoir cocher |
| M3 chat minimal | `[x]` | Le mod existe et marche au niveau `Session` (test). Mais : décocher `axiom.world` ne bascule pas sur le chat. Sonde : tout tombe en cascade, `axiom.ui.qt`, `axiom.ui.web` et `axiom.cli` sont **rejetés**, et pourtant `main.py:418` et `cli/play.py:284` testent `is_mod_enabled` (le choix utilisateur, `True`) au lieu du statut réel. **L'UI se lance sans son mod et chaque tour échoue.** `--safe-mode` en Qt affiche « interface désactivée » et quitte, avec un message qui invite à `axiom mod enable` | 🟡/🐞 |
| M5 schéma JSON contribué | `[x]` | Seul l'inventaire est concerné, et via une **table codée en dur dans `axiom.turn`** (`standard_specs`, `main.py:186`), pas une contribution du mod inventaire. `stat_events`/`modifiers` restent demandés même `core.stat_dynamics` décoché. Le schéma est **dupliqué** (`prompts.py` `NARRATIVE_TOOL_CALL_SCHEMA` + copie dans `axiom.turn`), donc deux sources de vérité. Un champ tiers sans `schema` est demandé au LLM comme `"champ": 0` | 🟡/⚠ |
| M6 sections positionnées | `[x]` | Ambiguïtés (tuple de 4 = deux formats selon le 1ᵉʳ élément), « depth » sert seulement de clé de tri, position inconnue ajoutée en silence aux chunks RAG (pas d'« erreur claire » demandée), et le plantage du §3.3 | 🐞 |
| M7 UI en mods | `[x]` | Emplacements web `side_panel` envoyés par `main_web.py:1659` mais **lus par personne** dans `web/app.js` ; `settings_tab`/`action_button` web jamais lus. `main.py:20` importe `MainWindow` directement depuis `mods/` | ⚠ |
| M8 `axiom.providers` effectif | `[x]` | Sans le mod, `resolve_llm_backend` reconstruit le même LLM (`session.py:108`) : **décocher `axiom.providers` ne change toujours rien** (c'était le reproche initial) | ⚠ |
| M9 `community.survival` | `[x]` | désactivé par défaut + dépendance déclarée | ✅ |

### 3.5 Phase 3 — patches

Sondes : patch d'une **méthode** (`ArbitratorEngine._fetch_effective_stats`) accepté via trampoline ;
cibles inexistantes refusées avec `PatchTargetError` ; les points `@patchable` (P2) sont bien en place
et vus par les importeurs. **✅**

### 3.6 Phase 4 — créateur LLM

C1 : écriture confinée (chemins absolus, `..` et `mod_id` hors du dossier refusés), aucune exécution
avant `apply_generated_mod` **✅**. C2 : tous les hooks publics de `kernel/api.py` sont réellement
déclenchés **✅**. C3/C4 honnêtement non cochés.

### 3.7 Doc (DOC2)

**L'exemple canonique du README fonctionne réellement.** Sonde : mod installé + vrai tour, la
section arrive dans le prompt, l'événement `thirst_update` est écrit, le patch est appliqué. ✅
**Mais** `tests/test_canonical_mod_example.py` ne joue aucun tour. Il appelle les fonctions de
l'exemple à la main, donc il passerait même si le pipeline ignorait les sections, et c'est
exactement le bug que la revue reprochait. Le test ne prouve pas ce qu'il prétend prouver.

## 4. Détail des bugs nouveaux

### 4.1 `[storage]` des manifestes (K9)

- `loader.py:334-357` prend la **clé** de la section (`entities`, `facts`…) comme nom de table et
  ignore `table = "..."`.
  - Sonde après bootstrap : 14 specs fantômes, dont `entities`, `entity_stats`, `rules` et
    `locations`, des tables de **définition**, enregistrées comme données runtime de save.
  - `get_runtime_tables()` les liste.
- Une politique inconnue devient en silence `STEP_KEYED` (aucune erreur, contraire à D13).
- **Elles ne cassent rien aujourd'hui, par accident.** `_table_exists` compare les noms en
  respectant la casse (`entities` ≠ `Entities`), alors que SQLite ne la respecte pas. Seul
  `event_log` (EVENTS, sans contrôle d'existence) exécute un `DELETE` en double sur `Event_Log`.
- **Les déclarations elles-mêmes sont fausses.** Si on corrige un jour le chargeur pour lire
  `table`, voici ce qui arrive :
  - `axiom.time` : `events = {table="Scheduled_Events", step_column="trigger_minute"}` → un rewind
    supprimerait des **événements planifiés de l'univers** dont la minute est supérieure au numéro
    de tour ;
  - `axiom.living_memory` : `observations`/`mental_models` en STEP_KEYED sur `updated_turn_id` →
    suppression au lieu de la restauration d'historique (régression de TICKET-083) ;
  - `axiom.inventory` : `item_instances = {table="Inventory_Snapshots"}` → mauvaise table.
- L'exemple de la vision (`hunger_level = { policy = "versioned_kv" }`) crée une « table »
  `hunger_level` qui n'existe pas. Il n'a aucun lien avec `ctx.store`.

### 4.2 `ctx.store` / `Mod_KV`

- **Plantage** : `set(step=5)`, puis `delete(step=5)`, puis `set(step=5)` →
  `IntegrityError: UNIQUE constraint failed` (sonde).
- **Rewind inopérant en silence** : `step` vaut `0` par défaut (`kv_store.py:68,113`). Un mod qui
  oublie le paramètre écrase la valeur « depuis toujours », et le rewind ne l'annule jamais (sonde :
  valeur 80 conservée après le rewind).
- Une écriture dans le désordre (`step=5` puis `step=3`) produit un intervalle invalide
  `from 5 → to 3`.
- **API éloignée de la vision** (« `store.get/set`, point ») : chaque appel exige `db_path`,
  `save_id` et `step`.
- Écritures hors transaction du tour et sans garde d'époque (voir 0d).
- Les politiques `events` (réducteur pur), `on_export/on_import` et les snapshots par mod
  (§10.2) n'existent pas.

### 4.3 Écran des mods Qt

`tr()` n'a pas de paramètre `default` (`core/localization.py:147`), et les clés
`mods_next_launch`, `mods_restart_required_notice` et `mods_enable_restart_notice` n'existent dans
aucune langue. L'écran affiche donc le texte brut des clés (`mods_dialog.py:423,433`). De plus,
pour un mod activé mais **rejeté** (conflit, dépendance), l'écran annonce « prendra effet au
prochain démarrage » au lieu de la vraie raison.

### 4.4 Divers

- `axiom.rag.set_vector_memory` garde une référence par `save_id` pour toujours (fuite mémoire) et
  ignore `base_dir` ; `except TypeError` comme repli d'API (`rag/main.py`).
- `axiom.illustrations` ignore le `data_dir` de la `Session` (`paths._data_root()`) et n'a aucun
  `fork_callback` : une save forkée perd ses illustrations.
- `bootstrap_all_mods` ajoute un écouteur de faute de patch global à chaque appel, jamais retiré.

## 5. Ce qui manque toujours (inchangé depuis `ETAT_REEL.md` §6)

Snapshots par mod ; politique `events` à réducteur ; `on_export/on_import` ; `axiom mod test` sur
harnais golden (C3) ; créateur hors du noyau (C4) ; hooks d'édition hors tour ; emplacements web lus
par le SPA ; test du wheel PyPI dans un venv vierge ; coordination D-6 ; licence.

## 6. Questions pour le propriétaire

1. **Lot E inversé** : on annule le rapatriement du code dans `axiom/` et on fait le vrai
   déplacement vers `mods/` (lourd, mais c'est la vision), ou on acte une étape intermédiaire
   assumée et **écrite** ? Dans les deux cas, `TODO.md` et `PENDING.md` (TICKET-106 « RÉSOLU ») sont
   à corriger.
2. **Safe mode** : sans aucun mod, il n'y a pas d'UI non plus (l'UI est un mod). Faut-il que safe
   mode garde l'UI, ou qu'il soit CLI uniquement, avec un message clair ?
3. Réglage « Canon auto » dans `mod_settings["axiom.turn"]` alors qu'il s'applique aussi avec
   `axiom.minimal_chat` : à valider ou à déplacer.
