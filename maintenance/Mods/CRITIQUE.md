# CRITIQUE — Système de mods (revue de `DOC.md` contre le code)

> Revue indépendante du 2026-09-23. Base : `maintenance/Mods/DOC.md` (vision validée), `ARCHITECTURE.md`,
> et lecture du code (`axiom/`, `ui/`, `workers/`, `main_web.py`, `tests/`, `maintenance/`).
> Les références `fichier:ligne` correspondent au commit `392644f` plus l'arbre de travail actuel.
> Ce qui est marqué **(vérifié par lecture)** a été lu dans le code mais pas exécuté. Ce qui est marqué
> **(non vérifié)** est une hypothèse.
> Gravité : **BLOQUANT** / **IMPORTANT** / **MINEUR**.

---

## 1. Résumé

La vision se tient, et Axiom a déjà des bases rares pour un système de mods : moteur headless, event
sourcing, rewind/fork, callbacks plutôt que signaux Qt, Universe-as-Code. **Mais le document décrit
le noyau comme s'il existait déjà des frontières propres dans le code. Ce n'est pas le cas.** Le « tour
de jeu » est éclaté en au moins quatre endroits (arbitre, `Session`, vue Qt, serveur web), avec des
logiques qui divergent. Il fait une dizaine de transactions SQLite indépendantes et garde de l'état
caché en mémoire. Le stockage « rembobiné automatiquement » bute sur trois choses : des listes de
tables tenues à la main (déjà désynchronisées : bugs réels ci-dessous), des stores hors SQLite
(ChromaDB, images) et des jobs en arrière-plan. Les patches à la Harmony sont faisables en Python
seulement si le moteur est préparé pour ça (trampolines), et ils sont **globaux au processus**, ce qui
contredit « 1 save = 1 modpack » dès que deux saves vivent dans le même processus. Mon verdict : **oui
à la vision, non à l'ordre de migration proposé.** Il faut d'abord unifier et « transactionnaliser » le
tour dans le moteur actuel, poser un filet de tests de caractérisation, et définir un **modèle de
données noyau** (le document n'en parle pas). Ensuite seulement viennent le chargeur, les hooks et les
mods.

---

## 2. Ce qui marcherait bien

### 2.1 Le moteur est déjà headless et piloté par callbacks, une bonne fondation pour des « UI-mods » — gravité : n/a (atout)
- `ARCHITECTURE.md` impose déjà la dépendance à sens unique app → moteur, et `tests/test_packaging.py`
  la garde. Le patron « worker-coquille » (`workers/narrative_worker.py:65-100`) montre qu'une UI peut
  se contenter de consommer `on_token`/`on_status`/`on_hero_decision`.
- En pratique, **deux frontends (Qt et web) consomment déjà le même `Session`**
  (`workers/narrative_worker.py:74-94`, `main_web.py` `execute_session_turn`). C'est la meilleure
  preuve qu'« UI = client d'une API moteur » est réaliste.

### 2.2 L'event sourcing rend le rewind/fork pensable de façon générique — atout
- `Event_Log` est la source canonique (`axiom/schema.py:136-146`). `State_Cache` est une vue
  matérialisée reconstruite par `EventSourcer.rebuild_state_cache` (`axiom/events.py:204-272`), avec
  des snapshots (`events.py:231-248`). Si les mods pouvaient enregistrer leurs propres types d'events
  **et leurs réducteurs**, les données d'un mod retiré « resteraient en sommeil » gratuitement : les
  events sont ignorés au replay (`events.py:526-527`, « All other event types … produce no cache
  change »). C'est exactement la sémantique voulue au §8.

### 2.3 Le « pool d'intents » est déjà un embryon de tick générique — atout
- `Session.submit_intent` / `resolve_tick` (`axiom/session.py:196-215`) découplent déjà la collecte
  des actions de leur résolution. Le multijoueur hotseat s'est branché dessus proprement
  (`take_turn_multiplayer`, `session.py:~380`). Un « mod de tour » alternatif (autre chose que du JDR)
  aurait un point d'entrée naturel : `resolve_tick`.

### 2.4 Universe-as-Code fournit déjà le niveau « Données (zéro code) » — atout
- Univers = arborescence TOML/MD compilée (`axiom/compile.py:545-599`), hot reload (`axiom/dev.py`),
  passthrough sans perte des clés inconnues via `[extra]` (`compile.py:204-207`). C'est le socle
  naturel des mods de données, et `axiom dev` sert de modèle pour `axiom mod dev`.

### 2.5 Il existe déjà des « emplacements » de fait, qu'il suffit de nommer — atout
- Backend LLM : l'interface abstraite `LLMBackend` (`axiom/backends/base.py:141-247`, `complete` /
  `stream_tokens` / `parse_tool_call` / `cancel_event`) est un bon contrat d'emplacement exclusif.
- Mémoire : `VectorMemory.query` fusionne déjà plusieurs sources par RRF
  (`axiom/retrieval/fusion.py`, `cap_per_source`). C'est un emplacement « collecte » **avec une
  politique de fusion**, ce qui montre au passage ce qu'il manque au §6 (voir 3.5).
- Frontières de config par rôle : `resolve_time_model`, `resolve_extraction_model`,
  `resolve_memory_fact_model` (`axiom/config.py`) sont déjà des « emplacements de modèle ».

### 2.6 La discipline de maintenance du projet est un vrai atout pour un chantier aussi long — atout
- Tickets numérotés, QA systématique, `PENDING.md` honnête (la classe de bugs « pas rembobiné / pas
  copié au fork » y est documentée : TICKET-083/088/089). C'est ce qui rend une migration en 5 étapes
  pilotable par des agents.

---

## 3. Ce qui marcherait moins bien / risques

### 3.1 Le « tour de jeu » n'est pas dans le moteur : il est éclaté en 4 endroits qui divergent — IMPORTANT (proche du bloquant pour l'étape 2)
Le §10 étape 2 propose de « découper `process_turn` ». Mais `process_turn` n'est qu'une partie du tour :
1. `ArbitratorEngine.process_turn` (`axiom/arbitrator.py:181-842`) : RAG, prompt, LLM, Timekeeper,
   règles, modifiers, inventaire, events.
2. `Session.resolve_tick` (`axiom/session.py:196-320`) : incrément de `turn_id` (l.209), Chronicler
   (l.236-248), snapshot périodique (l.254), génération d'image (l.262-310), `last_updated`.
3. **Vue Qt** `ui/tabletop_view.py:729-803` (`_on_turn_complete`) : auto-canonize (l.1111),
   accumulation + extraction de faits/croyances/modèles mentaux (l.1130, 1157-1215, via
   `workers/fact_worker.py`).
4. **Serveur web** `main_web.py` `execute_session_turn` → `schedule_living_memory_after_turn`
   (l.2491) → `_spawn_living_memory_job` (l.2669-2751). **L'algorithme est différent** :
   rattrapage depuis l'`Event_Log` avec `distil_turns_to_memory`, fenêtre de 6 tours, contre un buffer
   de textes avec `distil_narrative_to_memory` côté Qt (`axiom/living_memory.py:20` vs `:83`).

S'y ajoute `axiom/regenerate.py`, qui reconstruit un prompt **par un autre chemin** : sans stats, sans
RAG, sans lore (`regenerate.py:60-70`). Un mod qui accroche « avant le prompt » ne s'appliquera donc
pas aux régénérations, sauf si l'on unifie.

**Conséquence :** faire du tour un mod avec des hooks « après la réponse » suppose que l'orchestration
post-tour vive dans le moteur. Aujourd'hui, elle enfreint déjà la règle 4 d'`ARCHITECTURE.md`
(« une seule source de vérité par feature »). Il faut rapatrier ça **avant** l'étape 2.

### 3.2 Le tour n'est pas transactionnel : ~10 commits indépendants, écritures avant l'appel LLM — IMPORTANT
Chaque helper ouvre sa connexion et commit (`get_connection`, `axiom/schema.py:1287-1313`). Dans un
seul `process_turn` :
- les intents sont écrits et commités **avant** l'appel LLM (`arbitrator.py:229-236`, `append_event` →
  commit immédiat, `events.py:104-126`) ;
- Timeline (l.636-641), ajout/retrait de modifiers (via `ModifierProcessor`), snapshot d'inventaire
  « tour précédent » (l.714-717), mutations d'inventaire par item, tick + snapshot de modifiers
  (l.789-790), snapshot d'inventaire (l.795-797), embedding vectoriel (l.801, **avant** le batch
  d'events), batch d'events (l.811), mise à jour de `State_Cache` (l.817), marquage des events planifiés
  (l.822).

**Bug existant (vérifié par lecture) :** si le tour échoue ou est annulé (`GenerationCancelled`,
`main_web.py` `execute_session_turn`), `Session._turn_id` a déjà été incrémenté (`session.py:209`) et
l'event `user_input` reste en base **sans narration**. Aucun code de nettoyage n'existe (recherche
« orphan », « `_turn_id -= 1` » : rien).

**Pourquoi ça compte pour les mods :** le §9 promet l'« isolation des plantages : un mod qui lève une
exception est désactivé, Axiom ne plante pas ». Sans unité de travail transactionnelle, désactiver un
mod qui lève au milieu du tour laisse un état **à moitié écrit** : moitié des events, snapshot sans
Timeline, vecteur sans event. Rattraper l'exception sans pouvoir annuler ce qui a déjà été écrit,
c'est échanger un crash visible contre une save corrompue sans bruit.

### 3.3 État caché en mémoire, jamais persisté ni rembobiné — IMPORTANT
- `ArbitratorEngine._pending_correction` (`arbitrator.py:152`, lu l.450, vidé l.465, posé l.1731) est
  une donnée de gameplay d'un tour à l'autre (la « boucle de correction »). Elle n'est **ni persistée
  ni rembobinée** : `Session.rewind` n'appelle que `invalidate_stats_cache()`, qui est un no-op
  (`arbitrator.py:166-176`, `session.py:408-414`). Après un rewind, la correction d'un tour annulé
  fuit dans le tour rejoué. Elle est aussi perdue au redémarrage.
- `process_turn` stocke des variables par tour sur `self` (`_mode`, `_player_entity_id`,
  `_active_actor_ids`, l.218-227) : le moteur n'est pas réentrant.
- **Pour les mods :** c'est le style que les auteurs de mods (et les LLM qui en écrivent) reproduiront
  par défaut, avec des globales de module. Le stockage fourni par le noyau ne sert que si **il est plus
  simple à utiliser qu'un attribut `self.x`**. Et il faut un moyen de détecter ce genre d'état (voir 5.6).

### 3.4 Trois chemins de rewind différents, et l'un oublie la mémoire vectorielle — IMPORTANT (bug réel)
- Qt : `workers/db_tasks.py:151-178` (backup auto + `CheckpointManager.rewind` + troncature des
  images), puis `ui/tabletop_view.py:1011-1023`, qui enchaîne `VectorWorker` →
  `VectorMemory.rollback` (`workers/vector_worker.py:83`, `axiom/memory.py:482-501`).
- CLI et web : `Session.rewind` (`session.py:408-437`), **qui n'appelle jamais
  `VectorMemory.rollback`**. Ça concerne `main_web.py:1808-1815` (rewind) et `main_web.py:1925-1931`
  (édition de message = rewind puis nouveau tour), ainsi que `axiom/cli/play.py:185`.
  **(vérifié par lecture)** Sur le web et en CLI, après un rewind, les chunks narratifs des tours
  annulés restent dans ChromaDB et remontent au RAG : fuite du « futur ».
- C'est exactement la classe de bugs que le §8 veut éliminer. Ça montre surtout que le rewind n'a
  **pas de point d'entrée unique**. Un hook `on_rewind` n'a de sens que s'il n'existe qu'un seul
  rewind.

### 3.5 Les 3 règles de combinaison ne couvrent pas les vrais cas du code — IMPORTANT
Cas concrets qui n'entrent proprement dans ni exclusif, ni chaîne, ni collecte :
1. **La sortie JSON structurée du LLM.** Le contrat est un bloc unique partagé par stats, stat_events,
   modifiers, inventaire, pace, tag (`axiom/prompts.py:56-78`), parsé une fois
   (`arbitrator.py:490-508`) puis réparti à la main. Un mod « faim » qui veut que le LLM émette
   `"hunger_changes"` doit (a) **contribuer** un fragment de schéma et d'instructions au prompt,
   (b) **recevoir** sa clé après le parsing. C'est un quatrième motif : **contribution + routage**
   (chaque mod déclare « ses » champs, le noyau aiguille). Ni une collecte (le résultat ne se
   « rassemble » pas), ni une chaîne.
2. **Le streaming.** `_call_llm` filtre les tokens avec un tampon de 15 caractères pour cacher le bloc
   JSON (`arbitrator.py:896-911`). Une chaîne « anti-jurons → style → traduction » (exemple du §6)
   **ne peut pas s'appliquer token par token** : un filtre a besoin de contexte, une traduction de la
   phrase entière. Il faut deux emplacements distincts : un **transformateur de flux à état**
   (générateur → générateur, avec tampon) et une **chaîne sur le texte final**. Il faut aussi une règle
   de cohérence (le texte affiché en stream ≠ le texte stocké si seule la chaîne finale transforme).
3. **Les dépendances de données entre « collecteurs ».** La mémoire n'est pas une collecte à plat :
   le RAG (l.301) nourrit la détection des entités pertinentes (l.315, `_identify_relevant_entities`
   scanne les `rag_chunks`, l.1078-1085). Ces entités déterminent les personnages en scène, qui
   filtrent ensuite faits, croyances et modèles mentaux (l.396-440). Un mod mémoire « relations » qui
   veut les personnages en scène dépend de la sortie d'une autre étape. Il faut **des étapes
   ordonnées avec un contexte partagé typé**, pas seulement des collectes indépendantes.
4. **Collecte sans politique de fusion = ordre arbitraire.** Le projet a lui-même eu besoin de RRF et
   de `cap_per_source` pour fusionner deux sources de mémoire (`axiom/retrieval/fusion.py`).
   TICKET-084 (« budget `living` = 3× `rag_chunk_count` ») est déjà un cas d'explosion du prompt à
   l'intérieur même du noyau. Je ne remets pas en cause « pas de trieur obligatoire ». Mais le créateur
   d'une collecte doit au minimum **choisir la fonction de fusion** (concat par load order, RRF,
   entrelacement…), sinon « l'ordre de chargement » décide seul de ce qui entre dans le prompt.
5. **Les transactions.** Un hook qui écrit en base pendant le tour doit écrire **dans la transaction
   du tour** (voir 3.2). Aucune des trois règles ne dit qui possède la connexion.
6. **Les callbacks d'UI.** `on_token`/`on_status` sont passés par l'appelant (l'UI). Si les UI sont des
   mods, ce sont des **abonnements à des événements** (pub/sub, zéro à N abonnés, aucun résultat
   attendu). C'est un cinquième motif, plus simple que la collecte, qu'il faut nommer. Il faut aussi
   documenter **le thread sur lequel les abonnés sont appelés** (voir 3.9).

### 3.6 Des listes de tables tenues à la main, déjà désynchronisées — IMPORTANT (preuve que le §8 est nécessaire, et qu'il est difficile)
Le code maintient au moins **cinq** listes parallèles des tables « d'une save » :
- `checkpoint.py:76-160` (rewind : Event_Log, Snapshots, Timeline, Facts, Observations,
  Mental_Models, modifiers, inventaire, Fired_Scheduled_Events) ;
- `saves.py:844-963` (`fork_save`) ;
- `savestore.py:469-495` (`_RUNTIME_COPY`, extraction/export) ;
- `savestore.py:41-55` (`_DEFINITION_COPY`, copie de la définition dans chaque save) ;
- `package.py:94-105` (`_RUNTIME_TABLES`, purge à l'export d'univers).

Incohérences constatées :
- **TICKET-088/089** (connus) : `fork_save` et `_RUNTIME_TABLES` oublient les tables living.
- **Nouveau (vérifié par lecture)** : `fork_save` copie **tous** les `Fired_Scheduled_Events` de la
  source, **sans filtrer `fired_turn_id <= turn_id`** (`saves.py:947-957`). Un fork au tour 5 d'une
  save arrivée au tour 20 marque comme « déjà tirés » des événements tirés au tour 15, qui ne se
  déclencheront jamais dans la branche.
- **Nouveau (vérifié par lecture)** : `fork_save` copie les `Active_Modifiers` **présents** et non ceux
  du tour du fork (`saves.py:931-941`), alors que `Modifier_Snapshots` existe pour ça (utilisé par
  `rollback_modifiers`).
  (Portée : saves embarquées legacy. Les saves séparées sont copiées fichier à fichier.)

**Pour les mods :** si le noyau garde ce modèle « chaque table sait se rembobiner à sa façon », chaque
mod devra déclarer ses tables dans les cinq listes. C'est précisément ce qu'un auteur de mod (humain ou
LLM) oubliera. Le noyau doit posséder **un registre unique des données de save**, avec pour chaque
entrée sa politique (voir 5.2), et ces cinq fonctions doivent devenir des itérations sur ce registre.

### 3.7 Le schéma n'est pas extensible et il n'a pas de système de migration — IMPORTANT
- Les migrations sont ad hoc : on détecte des colonnes ou le texte du DDL (`schema.py:1109-1120`,
  `migrate_location_tables` compare le SQL de `sqlite_master`, l.1130-1170). Il n'y a ni
  `PRAGMA user_version`, ni table de versions.
- Des tables sont créées paresseusement (`ensure_facts_table`, etc., `schema.py:509-590`), et les
  appels défensifs `ensure_…` sont semés dans `checkpoint.py` et `saves.py`.
- **Les modes de jeu sont figés dans le DDL** :
  `CHECK(difficulty IN ('Normal','Hardcore','Companion','Multiplayer'))` (`schema.py:128`). Ajouter
  « Multiplayer » a demandé une migration de table (`maintenance/Multiplayer/TODO.md` §2). Si « le tour
  est un mod », un mod qui ajoute un mode de jeu devra reconstruire la table `Saves`. Ce CHECK doit
  disparaître du noyau.
- **Pour les mods**, il faut : (a) des tables préfixées par mod (`mod_<id>__…`) ou un stockage
  générique ; (b) une version de schéma **par mod** stockée dans la save (`Save_Meta` existe pour les
  saves séparées, `savestore.py:57-62`, mais pas pour les saves embarquées legacy) ; (c) un exécuteur
  de migrations appelé à l'ouverture, qui gère le cas « mod réactivé après N versions » (données en
  sommeil au schéma v1, mod en v3).

### 3.8 Compile/décompile d'univers : les données de mods seraient silencieusement perdues — IMPORTANT
- `_parse_tree` construit un dict **fermé** (`compile.py:520-538`) et `create_universe_db` recrée la
  base de zéro (`compile.py:580-583`). Une section `[hunger]` dans `universe.toml` est ignorée : seul
  `[extra]` est préservé (`compile.py:204-207`). Un dossier `hunger/` est pris en compte dans le hash
  (`_iter_source_files`, l.73-82) mais jamais parsé.
- `dev.refresh_definition` et `_DEFINITION_COPY` (`savestore.py:41-55`) synchronisent une liste fixe
  de tables de définition.
- **Il faut donc des hooks `compile`/`decompile`/`refresh_definition` par mod.** Sinon, l'aller-retour
  sans perte (promesse de Universe-as-Code) casse dès qu'un mod apporte des données d'univers.
- Les univers embarquent déjà des sections de features : `[calendar]` et `[companion]` dans
  `universes/Myria/universe.toml`, parsées en dur (`compile.py:183-202`). Si le temps et le Companion
  deviennent des mods, **le format d'univers lui-même devient modulaire**.

### 3.9 Threads : des jobs de fond écrivent pendant que le tour ou le rewind tourne — IMPORTANT
- Web : `ThreadingHTTPServer` (`main_web.py:3179`) + `ACTIVE_SESSION_LOCK`. Mais le job de mémoire
  living est un `threading.Thread` daemon (`main_web.py:2751`) qui lit `ACTIVE_SESSION._db_path` et
  écrit Facts/Observations **sans prendre `ACTIVE_SESSION_LOCK`**. Un rewind pendant ce job peut voir
  réapparaître des faits d'un tour annulé juste après le rollback (course **non vérifiée par test**,
  vérifiée par lecture). TICKET-083 est une variante temporelle du même problème.
- Qt : `NarrativeWorker` (QThread), `FactExtractWorker`, `VectorWorker`, tâches `QRunnable` de
  `db_tasks.py`, autant d'écrivains concurrents.
- **Pour les mods :** (a) si les hooks sont appelés dans le thread du moteur, un mod d'UI Qt qui touche
  un widget depuis un hook plante ou fige l'app (le projet a déjà eu un figement Qt lié aux threads,
  cf. `collab/claude/EN_COURS.md`, `notify()`) ; (b) **les patches appliqués « à chaud » pendant
  qu'un tour tourne dans un autre thread** donnent un tour exécuté à moitié avec l'ancien code et à
  moitié avec le nouveau ; (c) les jobs de fond d'un mod doivent être rattachés à une « époque » de
  save (voir 5.3).

### 3.10 Config globale fermée : les réglages d'un mod seraient effacés — IMPORTANT
- `load_config` **filtre les clés inconnues** (`config.py:319-321` :
  `filtered = {k: v … if k in known}`), et `save_config` réécrit `asdict(config)`
  (`config.py:363-366`). Un mod qui ajoute sa clé dans `settings.json` la perd au premier
  enregistrement des réglages par l'UI.
- La config est un singleton de processus, mis en cache par mtime (`config.py:295-302`), et appelé
  à chaud au milieu du tour (`arbitrator.py:247-248`, `:924`). Le logger est un singleton reconfiguré
  par `Session` (`session.py:129`).
- Il faut une **config namespacée par mod** (`[mods.<id>]`), avec un schéma déclaré, et des réglages
  **par modpack/save** en plus des réglages machine.

### 3.11 Les patches façon Harmony/Mixin : faisables, mais pas « sur n'importe quelle fonction » sans préparation — IMPORTANT
Les pièges Python, avec leur fréquence réelle dans le code :
- **Références capturées par `from x import f`** : **106** imports `from axiom.x import y` au niveau
  module dans `axiom/`. Remplacer `axiom.rules.RulesEngine` n'affecte pas `arbitrator.py`, qui l'a
  importé à la ligne 36. Les **186** imports locaux (dans les fonctions) se re-résolvent à chaque appel
  et, eux, verraient le patch. Le résultat serait donc **incohérent selon le site d'appel**. Les tests
  le savent déjà : ils patchent `axiom.config.load_config` justement parce que l'arbitre l'importe
  localement (commentaire `arbitrator.py:245-246`).
- **Constantes importées par valeur** : `from axiom.prompts import HISTORY_TURN_CAP`
  (`session.py:32`). Un patch de la constante dans `axiom.prompts` n'a aucun effet sur `Session`.
- **Instances créées une fois** : `self._rules_engine = RulesEngine(...)` (`arbitrator.py:146`) et
  `EventSourcer`/`ModifierProcessor` (l.147-148). Patcher la méthode sur la classe marche (résolution à
  l'appel), mais **remplacer la classe** n'affecte pas les instances existantes.
- **Méthodes liées déjà passées en callback** : `on_token=self.token_received.emit`
  (`narrative_worker.py:77`), `stream_token_callback`. Une fonction déjà remise à quelqu'un ne se
  « dé-patche » pas.
- **Retirer un patch au milieu d'une pile** : si A puis B patchent `f` et que A se désactive, il faut
  reconstruire la pile. Impossible si l'on a simplement fait `module.f = wrapper`.
- **Patch textuel de prompts** : `regenerate.py:74-79` fait un `.replace("You MUST end your response
  with a JSON block", …)` sur une chaîne qui **n'existe pas** dans `prompts.py` (`git log -S` : jamais
  présente dans `axiom/prompts.py`). Le remplacement est un no-op silencieux. Probable conséquence
  (vérifiée par lecture, non testée) : les variantes régénérées contiennent le bloc JSON dans le
  texte stocké, que seul l'affichage Qt masque (`ui/widgets/chat_display.py:80-95`). C'est exactement
  le mode de casse des patches « instables » : **aucune erreur, juste un effet qui disparaît**.
- **Globalité au processus** : c'est le point le plus grave, voir 4.3.

Solution praticable : voir 5.4 (trampolines déclarés).

### 3.12 Le noyau risque d'être « vide de sens » et la vraie API se déplace dans le mod `axiom-turn` — IMPORTANT
Si le tour, la mémoire, le temps, les stats, les providers et les UI sont des mods, le noyau ne connaît
ni entité, ni stat, ni LLM, ni tour. Or :
- le **stockage rembobinable** a besoin d'une notion d'**étape/tour** : le rewind est indexé par
  `turn_id` partout (`checkpoint.py:76-160`) ;
- l'`Event_Log` est au cœur du rewind/fork, mais son réducteur ne connaît que les stats
  (`events.py:303`, `:495-527`) ;
- presque tous les mods de jeu dépendront d'`axiom-turn` (le manifeste d'exemple le montre, DOC §4).

Donc, en pratique, **la stabilité qui compte pour les auteurs de mods est celle des hooks du mod
`axiom-turn`**, pas celle du noyau. La « version d'API » du manifeste (`axiom_api = "1"`) ne protège
que ce qui change le moins. C'est viable (Fabric fonctionne ainsi : Loader minuscule + Fabric API qui
est un mod), à condition de **l'assumer** : `axiom-turn` doit être versionné, documenté et stabilisé
comme une API publique, pas comme « un mod parmi d'autres ». Voir 5.1 pour la frontière que je propose.

### 3.13 « Désactiver à chaud » : illusoire pour le code Python — IMPORTANT
Python ne décharge pas un module proprement : références restantes, threads démarrés par le mod,
widgets Qt créés, callbacks enregistrés chez des tiers, classes dont des instances vivent encore.
`importlib.reload` ne met pas à jour les références existantes. Minecraft, Skyrim et Blender (où
`unregister()` est notoirement imparfait) exigent un redémarrage ou tolèrent des fuites. Je recommande :
**à chaud pour les mods de données et les hooks enregistrés via un contexte traçable, au prochain
lancement pour les patches et le code arbitraire.** La liste à cocher doit l'afficher.

### 3.14 La suite de tests actuelle ne protège pas une refonte de `process_turn` — IMPORTANT
- **1 029 fonctions de test** dans 73 fichiers. 24 fichiers touchent `process_turn`, `_arbitrator` ou
  `ArbitratorEngine`. Beaucoup testent des helpers privés (`arb._…`) ou des chemins précis. Une
  refonte en étapes nommées cassera beaucoup de tests **pour de mauvaises raisons** (structure
  interne) et en laissera passer d'autres (comportement de bout en bout non couvert).
- Il manque des **tests de caractérisation bout en bout** : faux LLM scripté → N tours → état complet
  de la base (events, State_Cache, Timeline, modifiers, inventaire, faits) → rewind → fork → export →
  comparaison. Il existe des faux LLM ad hoc dispersés (`tests/test_engine_port_b4.py:91,156,173`,
  `tests/test_populate_engine.py:22`), mais pas un harnais commun. Ce harnais est **le** prérequis de
  l'étape 2, et il servira ensuite de « module de test » pour les mods (§9).
- Rappel : `maintenance/Multiplayer/TODO.md` §8 note que la suite pytest n'a pas été lancée dans le venv
  de l'agent. La discipline « `main` toujours vert » repose donc sur l'humain.

### 3.15 Coût réel de la migration : sous-estimé d'un ordre de grandeur — IMPORTANT
- Étape 1 (« emballer tout dans `axiom-legacy` ») est **peu coûteuse et apporte peu** : un mod qui
  enregistre un seul fournisseur exclusif « tour » qui appelle `Session`. Ça valide le chargeur, pas
  l'architecture.
- Le vrai coût est dans les étapes 2-3 : ~660 lignes de `process_turn`, plus l'orchestration Session,
  Qt et web (3.1), plus cinq listes de tables (3.6), plus compile/decompile (3.8), plus deux UI de
  **144 Ko (`main_web.py`) + 191 Ko (`web/app.js`)** sans aucun point d'extension, qui accèdent aux
  privés de `Session` (**40×** `ACTIVE_SESSION._db_path`, **26×** `._save_id`, plus un attribut ajouté
  de l'extérieur `_last_lore_hits`, `main_web.py:2947`). Les UI importent ~30 modules moteur
  (`axiom.config` 43×, `axiom.savestore` 26×, `axiom.facts`/`observations`/`mental_models`…). Chaque
  extraction de feature en mod oblige à re-câbler ces imports.
- Ordre de grandeur (estimation) : plusieurs mois de travail d'agents avec QA, pendant lesquels
  **toute feature ajoutée l'est deux fois** (dans le legacy puis dans le mod), ou alors il faut un gel.

### 3.16 Le paquet PyPI : « `axiomai-engine` = noyau seul » casse les utilisateurs existants — MINEUR à IMPORTANT
- `axiomai-engine` 0.2.0 expose `from axiom import Session, Universe` (`axiom/__init__.py`) et
  `axiom.help` documente `Session(...).take_turn(...)`. Si le paquet devient le noyau seul, ce code
  casse.
- Les mods de base ont des dépendances lourdes, aujourd'hui dans les dépendances du paquet :
  `chromadb`, `sentence-transformers` → torch (`pyproject.toml`). Un `.axmod` en zip ne peut pas
  embarquer torch (extensions C, roues par plateforme). **La question de l'installation des
  dépendances pip d'un mod n'est pas traitée dans le DOC** (voir 6.1).
- Alternative : `axiomai-kernel` (nouveau paquet, noyau seul) et `axiomai-engine` qui devient un
  méta-paquet « noyau + mods de base ». Les utilisateurs actuels ne cassent pas.

### 3.17 Une priorité globale unique est trop grossière — MINEUR
Le §6 utilise **un seul load order** pour désigner les gagnants exclusifs, ordonner les chaînes, les
collectes et les patches. Or je peux vouloir que A gagne le backend et que B passe en premier dans la
chaîne de filtres. Skyrim en souffre au point d'avoir LOOT (un trieur externe). Prévoir un **ordre
global par défaut + surcharges par emplacement**, et des contraintes déclaratives dans le manifeste
(`after`, `before`, `conflicts`, `provides`), comme les `ordering`/`breaks` de Forge et Fabric.

---

## 4. Éléments bloquants

### 4.1 Il n'y a pas de frontière de transaction du tour — BLOQUANT pour « stockage rembobiné auto » + « isolation des plantages »
**Ce qui bloque :** 3.2. Tant que chaque écriture commit seule, le noyau ne peut garantir ni qu'un
tour est tout ou rien, ni qu'un mod désactivé en cours de route ne laisse pas de demi-état.
**Pour lever :** restructurer le tour en **lecture → appels LLM → une seule phase d'écriture**, dans
une transaction portée par un objet `TurnContext`/`UnitOfWork` transmis aux étapes (et donc aux
hooks). Il ne faut pas garder une transaction d'écriture ouverte pendant le streaming LLM : en WAL,
elle bloquerait les autres écrivains (jobs de fond). Il faut donc bufferiser les écritures, comme le
fait déjà `_pending_events` pour les events (`arbitrator.py:229`, `:811`), et étendre ce patron à
Timeline, modifiers, inventaire et snapshots. Les stores non-SQLite (ChromaDB) s'écrivent **après** le
commit, avec une réparation idempotente au démarrage (« le vecteur du tour N existe-t-il ? »).

### 4.2 Pas de point d'entrée unique pour rewind / fork / export — BLOQUANT pour le §8
**Ce qui bloque :** 3.4 et 3.6 : trois chemins de rewind, cinq listes de tables, un store vectoriel et
des images hors SQLite.
**Pour lever :** un **registre des données de save** dans le moteur actuel, *avant* les mods :
chaque « donnée » (table ou store externe) déclare sa politique (voir 5.2). `rewind`, `fork_save`,
`extract_save`, `pack_save`, `_runtime_free_cache_copy` et le Qt `RewindTask` deviennent des boucles
sur ce registre. Les stores externes (ChromaDB, images) implémentent une interface
`on_rewind/on_fork/on_export/on_import`. **C'est le cœur du futur « stockage de save » du noyau :
le construire d'abord pour les features actuelles, c'est à la fois corriger TICKET-088/089 et les bugs
de 3.4/3.6, et valider le design avant qu'un seul mod existe.**

### 4.3 Patches globaux au processus vs « 1 save = 1 modpack » — BLOQUANT (conflit interne à la vision)
Un monkeypatch modifie le processus entier. Or un même processus manipule déjà plusieurs saves :
- le Hub liste et prévisualise des saves ; `fork_save` et `extract_save` ouvrent source et cible ;
- le serveur web est multi-thread (`ThreadingHTTPServer`) et pourra servir plusieurs sessions ;
- le multijoueur **réseau** (hors périmètre v1, mais annoncé dans `maintenance/Multiplayer/DOC.md`)
  impliquera un serveur hébergeant plusieurs parties.

Si la save A a le mod « faim » et la save B non, les patches de « faim » s'appliquent à B dès qu'ils
sont chargés. **Il faut trancher :** (a) **un modpack actif par processus**, et changer de save avec
un modpack différent = redémarrer le moteur (c'est ce que font MultiMC/Prism pour Minecraft : une
instance = un modpack), avec un Hub qui lit les saves **sans charger leurs mods** ; ou (b) hooks et
emplacements **par session** (registre porté par `Session`), les patches restant globaux et réservés
aux mods « de processus ». L'option (a) est la plus simple et cohérente avec le §2. Elle impose que le
Hub/lanceur fasse partie du noyau, ou d'un mod toujours présent (voir 4.5).

### 4.4 Le noyau n'a pas de modèle de données défini — BLOQUANT pour démarrer l'étape 0
Le §3.1 liste des mécanismes (chargeur, registre, hooks, patches, stockage, modpack) mais aucune
donnée. Or le stockage rembobinable a besoin de savoir **par rapport à quoi** rembobiner (tour ?
minute de jeu ? les deux axes existent : `turn_id` et `Timeline.in_game_time`, cf. `saves.py:55-80`
`resolve_point(at_turn | at_minute)`). Il faut aussi décider si **Entités / Stats / Event_Log /
State_Cache** sont du noyau ou du mod `axiom-turn`. Tout Universe-as-Code (`compile.py`, `savestore`,
`dev.py`) en dépend.
**Pour lever :** écrire noir sur blanc le modèle noyau. Ma proposition : `Save`, `Step` (tour,
monotone, unité de rewind), `Event_Log` générique (types et réducteurs enregistrés par les mods),
stockage par mod, `Universe` = arbo de fichiers + manifeste. Entités et stats iraient dans un mod de
base « monde », ou resteraient dans le noyau si l'on veut que les univers restent portables
(à arbitrer, question 7.2).

### 4.5 Le gestionnaire de mods et le mode sans échec ne peuvent pas être des mods d'UI — BLOQUANT (mineur à lever, fatal si oublié)
Si toutes les UI sont des mods et que l'UI active est cassée par un mod, l'utilisateur n'a plus
d'interface pour décocher le mod fautif. Le mode sans échec et la liste des mods doivent être
accessibles **hors du système de mods** : un flag de lancement `--safe-mode` / variable
d'environnement, une commande noyau `axiom mods list/disable/enable`, et idéalement une UI de secours
minimale livrée avec le noyau (ou une UI « verrouillée » toujours chargée en premier et non
patchable). À prévoir dès l'étape 0.

### 4.6 L'orchestration post-tour vit dans les UI — BLOQUANT pour « le tour est un mod »
Voir 3.1. Tant que la mémoire living et l'auto-canonize sont déclenchées par `tabletop_view.py` et
`main_web.py` avec deux algorithmes différents, un mod de tour ne peut pas reproduire le comportement
actuel, et un mod d'UI tiers (CLI, futur Discord) n'aura jamais la mémoire living.
**Pour lever :** rapatrier dans `Session` un planificateur de tâches post-tour (avec file et
annulation), que les UI se contentent d'observer. C'est d'ailleurs une application directe des règles
actuelles d'`ARCHITECTURE.md`, indépendante des mods.

---

## 5. Bonnes idées d'architecture / alternatives

### 5.1 Adopter le découpage Fabric : Loader minuscule + « Axiom API » (mod de base) + features
- **Noyau (≈ Fabric Loader)** : chargeur, résolution des dépendances, registre, bus d'événements,
  stockage de save rembobinable, modpack, config namespacée, mode sans échec, CLI `axiom mods`.
- **`axiom-api` / `axiom-turn` (≈ Fabric API)** : le pipeline de tour en étapes nommées, les
  emplacements standard (backend narrateur, contributeurs de prompt, champs de sortie structurée,
  mémoire, filtres de flux), le modèle monde (entités/stats) si ce n'est pas le noyau. Versionné et
  documenté comme une API publique.
- **Features** : temps, mémoire living, inventaire, stats dynamiques, images, Companion, UI…
Ça respecte « le tour est un mod » tout en donnant aux auteurs de mods une cible stable.

### 5.2 Stockage de save : une politique déclarée par donnée, trois implémentations
Pour chaque donnée de mod, le noyau propose l'une des politiques suivantes. Il les applique à
rewind/fork/export sans que le mod écrive une ligne :
1. **`events`** : le mod émet des events typés `mod.<id>.<type>` et enregistre un **réducteur pur**.
   Rewind/fork gratuits (ils suivent l'`Event_Log`). Données en sommeil gratuites. Point de vigilance :
   les **snapshots** (`Snapshots.state_json`, pris tous les 25 tours, `session.py:254`) doivent être
   **par mod**. Sinon, réactiver un mod après un snapshot pris sans lui produit un état faux, car
   `rebuild_state_cache` part du dernier snapshot (`events.py:231-248`).
2. **`versioned_kv`** : table noyau `Mod_Data(save_id, mod_id, key, value_json, from_step, to_step)`
   (validité temporelle). Écrire = fermer la ligne courante et en ouvrir une. Rewind = supprimer
   `from_step > N` et rouvrir `to_step > N`. Fork = copier `from_step ≤ N`. C'est le plus simple pour un
   auteur (et un LLM) : `store.get/set`, point.
3. **`turn_keyed_table`** : table SQL propre au mod, avec une colonne de tour **déclarée dans le
   manifeste**. Le noyau fait `DELETE … WHERE step > N` au rewind et `INSERT … SELECT … WHERE step ≤ N`
   au fork. C'est ce que font déjà Facts et Modifier_Snapshots.
4. **`custom`** : le mod implémente `on_rewind/on_fork/on_export/on_import`. C'est la seule option pour
   les stores externes (ChromaDB, fichiers, images). Le noyau appelle ces hooks **depuis l'unique
   point d'entrée** (4.2).
Plus une règle : les données dérivées de plusieurs tours (croyances, modèles mentaux :
`checkpoint.py:118-128`) sont estampillées **au tour où elles sont calculées**, pas au plus vieux tour
source. C'est le correctif de TICKET-083, généralisé.

### 5.3 Époques de save pour les jobs de fond
Chaque rewind/fork/chargement incrémente une « époque » de session. Un job de fond (mémoire living
aujourd'hui, n'importe quel mod demain) capture l'époque au lancement et **refuse de commiter** si
elle a changé. Ça élimine la course de 3.9 sans verrou global et se généralise aux mods.

### 5.4 Patches : trampolines déclarés plutôt que monkeypatch libre
- Marquer les fonctions patchables avec un décorateur `@patchable("arbitrator.call_llm")`. Il installe
  **dès le chargement** un trampoline stable qui consulte une pile de patches (prefix / postfix /
  around, priorité, identifiant de mod). Parce que le trampoline est l'objet importé partout, les
  `from x import f` capturés voient les patches (3.11). Retirer un mod = retirer ses entrées de la
  pile. `axiom mods patches` liste qui patche quoi (c'est l'équivalent de `Harmony.GetPatchInfo`).
- Pour une fonction non décorée : fallback « best effort » en remplaçant `func.__code__` par un code
  trampoline, ce qui préserve l'identité de l'objet fonction. C'est à documenter comme fragile
  (closures, méthodes C, fonctions déjà inlinées dans des callbacks).
- Interdire le patch pendant un tour en cours : la pile est figée par tour (copie à l'entrée du
  `TurnContext`).
- C'est l'esprit de Mixin (points d'injection nommés) sans bytecode, et ça rend l'erreur de 3.11
  (`regenerate.py` qui remplace une chaîne absente) détectable : `axiom mod validate` vérifie que
  chaque cible existe.

### 5.5 S'appuyer sur `pluggy` pour les hooks
`pluggy` (le système de plugins de pytest, plus de 1 000 plugins en production) fournit déjà :
hookspecs typées, `firstresult=True` (= **exclusif**), résultats en liste (= **collecte**),
`hookwrapper`/`wrapper=True` (= **autour/chaîne**), `tryfirst`/`trylast`, enregistrement et
désenregistrement, blocage d'un plugin, traçage des appels. Ça couvre la majorité du §5-6 sans rien
inventer. Pour la découverte des mods installés par pip : les **entry points** (`importlib.metadata`,
à la stevedore), en complément des `.axmod`.

### 5.6 Contexte de mod traçable (patron Obsidian / VS Code)
Chaque mod reçoit un `ModContext` et **toutes** ses inscriptions passent par lui : `ctx.hook(...)`,
`ctx.slot(...)`, `ctx.patch(...)`, `ctx.thread(...)`, `ctx.config`, `ctx.store`. Dans Obsidian,
`this.registerEvent`/`registerInterval` sont automatiquement défaits à `onunload`. Ça rend la
réversibilité **structurelle** au lieu de reposer sur la discipline de l'auteur. Le contexte peut
aussi exposer une « détection de globales » en dev (diff des attributs de module avant et après un
tour) pour attraper les états cachés à la `_pending_correction`.

### 5.7 Contributions déclarées dans le manifeste (VS Code)
VS Code fait déclarer dans `package.json` les *contribution points* (commandes, vues, réglages) et les
*activation events*. Le gestionnaire sait ce que fait une extension **sans l'exécuter**. Appliqué ici :
`mod.toml` déclare `[provides.slots]`, `[contributes.hooks]`, `[patches]`, `[storage]`, `[config]`.
Bénéfices : l'écran de conflits (§6) se calcule sans charger de code, `validate` est statique, le
créateur LLM a une liste de ce qu'il peut cibler, et un mod en « sommeil » reste listable.

### 5.8 Assemblage du prompt en sections positionnées (SillyTavern)
SillyTavern injecte les contributions d'extensions dans le prompt avec une **position** (avant ou après
le system prompt, dans l'historique) et une **profondeur**. Ça correspond au besoin réel
d'`build_narrative_prompt` (`prompts.py:671-690`, 18 paramètres). Il vaut mieux un emplacement
« sections de prompt » où chaque contributeur fournit `(section_id, position, depth, text, priority)`
qu'une collecte de chaînes brutes. Le **schéma de sortie JSON** (3.5.1) suit la même logique : chaque
mod contribue `{champ: sous-schéma + consigne}` et reçoit son champ parsé.

### 5.9 Harnais de test « golden turn » d'abord, pour l'humain et pour le LLM
Faux backend LLM déterministe (réponses scriptées, y compris le JSON), fabrique de save temporaire,
assertions sur un dump normalisé de la base. Il sert (1) à sécuriser l'étape 2, (2) de
`axiom mod test` fourni aux auteurs, (3) de boucle de rétroaction au créateur LLM (il écrit un mod,
lance le golden test, lit le diff d'état).

### 5.10 Faire les étapes « sans mods » d'abord (réordonner le §10)
Proposition d'ordre :
- **0a** Harnais golden turn (5.9).
- **0b** Unifier le tour : post-tour dans `Session` (4.6), un seul `rewind` (4.2), `regenerate`
  aligné sur le même assembleur de prompt.
- **0c** Registre des données de save + politiques (5.2), qui corrige 088/089 et les bugs de 3.4/3.6.
- **0d** Transaction de tour (4.1) + état caché persisté (`_pending_correction`).
- **0e** Config namespacée (3.10), suppression du CHECK `difficulty` (3.7), versions de schéma.
- **Puis** le chargeur, les hooks (pluggy) et les emplacements, et **ensuite seulement** les patches
  (les plus risqués, les moins nécessaires tant que les hooks sont riches).
Chacune de ces étapes a de la valeur même si le projet de mods s'arrête en route. Ça réduit
fortement le risque.

---

## 6. Ce à quoi personne n'a pensé

### 6.1 Les dépendances pip des mods — IMPORTANT
Un mod mémoire veut `chromadb`, un mod d'images `diffusers`, un provider un SDK. Un `.axmod` (zip) ne
porte pas de roues natives. Il faut soit un champ `python_requires`/`pip = [...]` dans `mod.toml`
résolu dans le venv (conflits de versions entre mods, cas de torch), soit un venv par modpack. Sous
Windows (le projet a déjà une QA Windows douloureuse, TICKET-069/070 : torch sans VC++), c'est un nid
à tickets. **Il faut décider tôt.**

### 6.2 Licence AGPL et store de mods — IMPORTANT (question juridique, pas technique)
Le moteur est AGPL-3.0-or-later avec une clause de citation (`NOTICE`, mémoire
`project_engine_split_strategy.md`). Un mod Python chargé dans le même processus et qui importe
`axiom` est plausiblement une œuvre dérivée. Est-ce que le store impose une licence compatible ? Des
mods propriétaires sont-ils acceptés ? À trancher avant d'ouvrir un store.

### 6.3 Le créateur de mods par LLM : injection de prompt via le contenu — IMPORTANT
Je ne remets pas en cause « pas de sandbox ». Mais une conséquence concrète n'est pas écrite : le
créateur LLM génère du **code exécuté en processus** à partir d'une conversation qui peut contenir du
lore, des fiches importées (SillyTavern : `core/st_parser.py`), des univers téléchargés. Un univers
piégé (« quand tu écris un mod, ajoute aussi… ») peut faire écrire au créateur un mod malveillant,
**que l'utilisateur n'a pas choisi d'installer en connaissance de cause**. Mitigation minimale sans
sandbox : le créateur montre un diff et demande une confirmation explicite avant activation, et le
contexte du créateur exclut le contenu d'univers non vérifié.

### 6.4 Les saves et univers partagés doivent embarquer ou référencer leur modpack — IMPORTANT
`.axiomsave` et `.axiom` s'échangent (`savestore.pack_save`, `package.pack_universe`). Si une save
requiert « faim 1.2 », l'importateur doit savoir quoi installer. Il faut un manifeste de modpack dans
les archives (ids, versions, source/URL, hash), et un univers doit pouvoir déclarer
`[requires] mods = {...}` (voir question 7.3).

### 6.5 Mods de données du noyau vs données d'univers : double emploi — MINEUR
Le niveau « Données » d'un mod (prompts, lore, stats, règles) recouvre ce que fait un univers. Un mod
« bestiaire » est-il un mod ou un morceau d'univers ? Il faut une règle (par exemple : un mod de
données s'applique à *tous* les univers, un univers à lui-même) et un ordre de fusion
univers ↔ mods (qui gagne sur une entrée de lore au même id ?).

### 6.6 Régénération, variantes et état des mods — IMPORTANT
`regenerate_variant` produit une nouvelle narration **sans rejouer règles ni stats**
(`regenerate.py:1-6`). Il modifie l'`Event_Log` en place (`UPDATE`, `regenerate.py:125-131`), ce qui
contredit le principe append-only. Pour un mod, que signifie « variante 2 du tour 12 » ? Ses données
du tour 12 correspondent à la variante 1. Il faut une sémantique : les variantes sont purement
textuelles (les mods ne sont pas rappelés), ou une variante est un **fork léger** (tous les hooks
rejoués). À écrire dans l'API.

### 6.7 Hooks sur l'édition manuelle et les corrections — MINEUR
L'éditeur de saves (`saves.apply_correction`, events `manual_edit`), l'édition de message web
(`main_web.py:1925-1970`, avec `update_event_payload` + `update_turn_narrative`), le Studio et le
canonize modifient l'état **hors tour**. Les mods qui dérivent des données de la narration (index,
journal de quêtes) doivent être notifiés. Il faut des événements `on_state_edited`,
`on_narrative_edited`, `on_definition_changed`.

### 6.8 Observabilité et coût — MINEUR
Le §2 accepte les prompts obèses. Mais l'utilisateur doit **voir** qui ajoute quoi : un inspecteur de
prompt par section et par mod (tokens contribués), un profil de temps par hook, et un compteur d'appels
LLM par mod (chaque mod peut en ajouter : Timekeeper, extraction, consolidation… Aujourd'hui, un tour
fait déjà jusqu'à 2 appels synchrones + 1 d'image + N en fond). Sans ça, « c'est la responsabilité de
l'utilisateur » est une responsabilité qu'il ne peut pas exercer.

### 6.9 Internationalisation des mods — MINEUR
Toute l'i18n vit dans `core/localization.py` + `core/locales/*.toml` (10 langues, outil
`tools/i18n_check.py`), **côté app**. Un mod d'UI doit pouvoir apporter ses clés et ses langues. Il
faut un espace de noms de traduction par mod, et adapter `i18n_check` pour valider les mods.

### 6.10 Doc intégrée et aide — MINEUR
`ui/help_system.py` (registre de ~242 clés `doc_*`, F1, quick tour) est centralisé. Les mods doivent
pouvoir y contribuer (emplacement « collecte » d'entrées d'aide), sinon l'aide décrit des features
absentes et ignore celles des mods.

### 6.11 Identité et unicité des ids de mod — MINEUR
Deux auteurs publient `hunger`. Il faut des ids namespacés (`auteur.hunger`) ou un registre
d'attribution d'ids dans le store. Prévoir aussi `provides` (capacités virtuelles : deux mods
fournissent `memory`) et `conflicts`.

### 6.12 Reproductibilité d'un modpack — MINEUR
« 1 save = 1 modpack (ids + versions) » ne suffit pas si deux builds différents portent la même
version (mods générés par LLM, modifiés localement). Stocker un **hash du contenu** du `.axmod` dans le
modpack de la save permet d'avertir « même version, contenu différent ».

---

## 7. Questions ouvertes pour le propriétaire

1. **Un modpack par processus (redémarrage pour changer de modpack), ou des modpacks par session ?**
   (4.3) La réponse conditionne toute la conception des patches.
2. **Entités / stats / lieux / Event_Log : noyau ou mod ?** (4.4) Si c'est un mod, un univers n'est
   plus lisible sans ce mod. Si c'est le noyau, le noyau reste « un moteur de JDR », et « Axiom
   pourrait servir à autre chose » s'affaiblit.
3. **Un univers peut-il exiger des mods ?** Si oui : l'univers déclare `[requires]`, et ouvrir un
   univers propose d'installer ou d'activer le modpack. Quelle relation univers ↔ modpack : l'univers
   *recommande* un modpack, ou le *contient* ?
4. **« Désactiver à chaud » : acceptez-vous « au prochain lancement » pour les mods avec du code ?**
   (3.13)
5. **Faut-il geler les features pendant les étapes 0b-0e et 2-3 ?** Sinon, qui porte la double
   implémentation ? Vu l'historique (commit `1f48c82` « fixes for frosoore's shitty update », gros
   commit multi-sujets `4967506` qui touchait stats, mémoire et inventaire, donc le tour), une refonte
   de `process_turn` en parallèle de features sur le tour produira des conflits sémantiques que git ne
   voit pas. **Qui est propriétaire de `arbitrator.py`/`session.py` pendant la refonte ?** Et le web
   (`main_web.py`/`app.js`, surtout touché côté Frosoore / Boss Baby) : qui le transforme en UI-mod à
   emplacements ?
6. **PyPI :** nouveau paquet `axiomai-kernel` avec `axiomai-engine` qui devient un méta-paquet (sans
   casse), ou rupture assumée avec un bump majeur ?
7. **Dépendances pip des mods :** venv partagé, venv par modpack, ou mods « pur Python » uniquement
   au début ? (6.1)
8. **Licence des mods du store** (AGPL imposée ? libre choix ?) (6.2)
9. **Sémantique des variantes (régénération) pour les mods** : textuelles uniquement, ou mini-forks ?
   (6.6)
10. **Qu'est-ce que « un tour » pour le noyau** si Axiom sert à autre chose qu'un JDR ? Le rewind a
    besoin d'une unité de temps. Est-ce qu'un « step » générique monotone vous convient ?
11. **Priorité unique ou surcharges par emplacement ?** (3.17)
12. **Voulez-vous corriger dès maintenant, hors chantier mods**, les bugs trouvés pendant cette revue ?
    (1) `Session.rewind` ne rembobine pas ChromaDB (web + CLI) ; (2) tour échoué ou annulé → `user_input`
    orphelin et `turn_id` décalé ; (3) `_pending_correction` non rembobinée ; (4) `fork_save` copie
    les events planifiés tirés après le point de fork et les modifiers présents plutôt que ceux du
    tour de fork ; (5) `regenerate.py` remplace une consigne qui n'existe pas (JSON probablement stocké
    dans les variantes) ; (6) job de mémoire living web hors verrou (course avec le rewind). Ils
    tombent tous dans la catégorie que le système de mods prétend résoudre. Les corriger d'abord
    permet de concevoir le registre de données (4.2) sur un code sain.
