# Revue 3 — Les mods extraits (phase 2) et la frontière noyau / mods

> Relecteur : agent Claude (angle « mods extraits »), 2026-10-03, branche `mods` (HEAD `3f100ed`).
> Méthode : lecture du code + expériences réelles isolées (config et données dans
> `/tmp/claude-1000/axiom-review/`, via `AXIOM_CONFIG_DIR` / `AXIOM_DATA_DIR` ; aucune config
> utilisateur touchée, aucun fichier du repo modifié). Légende : **[EXÉCUTÉ]** = vérifié en lançant
> du code, **[LU]** = vérifié en lisant le code, **[SUPPOSÉ]** = déduction non vérifiée.
>
> Scripts utilisés (reproductibles) : `/tmp/claude-1000/axiom-review/turn_probe.py`,
> `run_scenarios.sh`, `slot_probe.py`, `correction_probe.py`, mods sondes dans `tmpmods/`.

---

## 1. Verdict

Le système de chargement fonctionne vraiment : les mods sont découverts, ordonnés, chargés, et
**chaque mod de jeu optionnel (inventaire, temps, mémoire vivante, RAG, illustrations, stats
dynamiques, providers) peut être décoché sans que le tour plante** — je l'ai vérifié en jouant des
tours avec un faux LLM. Les emplacements du tour (`prompt_sections`, `output_fields`, filtres,
`llm_backend`) sont réellement consultés, et un mod tiers peut recevoir un champ de sortie.

Mais la promesse centrale « petit noyau + tout le reste en mods » **n'est pas tenue** :
le « mod » `axiom.turn` est une coquille de 177 lignes qui appelle `axiom/arbitrator.py` (1 955
lignes, resté dans le noyau) ; environ 9 400 lignes de code JDR/LLM restent dans `axiom/` ; le
noyau importe les mods (proxys) au point que **le paquet « noyau seul » ne sait même plus compiler
un univers** ; le stockage par politiques (`versioned_kv`, `ctx.store`) n'existe pas ; « tout
décoché » ne donne **aucun** chat. J'ai aussi trouvé **une régression de jeu** (la boucle de
correction de l'Arbitre est morte) et un défaut d'isolation qui fait qu'**un bug dans un mod tiers
fait échouer tous les tours** — l'exemple de mod du `DOC.md` actuel déclenche exactement ce cas.

Ce que ça veut dire concrètement : l'architecture *ressemble* à la vision (dossiers `mods/`,
manifestes, CLI), mais le moteur de jeu n'a pas été déplacé, il a été *enveloppé*. Remplacer le tour
ou la mémoire par un mod tiers reste aujourd'hui impossible sans réécrire le cœur.

---

## 2. Ce qui est bien fait (preuves)

- **Désactivation mod par mod : ça ne plante pas, et l'effet est réel. [EXÉCUTÉ]**
  Scénarios (désactivation via la vraie CLI `axiom mods disable`, config isolée, 2 tours, faux LLM) :

  | Désactivé | Tour joué ? | Effet observé |
  |---|---|---|
  | (aucun) | oui | +5 pièces, objet `rusty_key` créé, temps 130 → 135 min, timeline écrite |
  | `axiom.inventory` | oui | aucun objet créé, `output_fields` sans `inventory_changes` |
  | `axiom.time` | oui | temps figé à 0, timeline vide |
  | `axiom.living_memory` | oui | service absent, tour normal |
  | `axiom.rag` | oui | service absent, tour normal |
  | `axiom.illustrations` | oui | service absent, tour normal |
  | `core.stat_dynamics` | oui | hook `axiom.turn:arbitrate_stats` absent |
  | `axiom.providers` | oui | (mais voir I8 : sans effet réel) |
  | `axiom.world` | **non** | `NoTurnPipelineInstalledError` (cascade attendue, voir B5) |
  | tout | **non** | `NoTurnPipelineInstalledError` |

- **Les emplacements du tour sont réellement branchés. [EXÉCUTÉ]** Un mod sonde tiers
  (`tmpmods/review.hunger`) a contribué `output_fields` (`hunger`), `final_text_filter` et
  `stream_filter` : il a bien reçu `7` puis `9`, le texte final a été transformé (« key » → « KEY »),
  et le flux streamé passé en majuscules. Code : `mods/axiom.turn/main.py:86-143`. Le backend LLM
  passe par l'emplacement exclusif `axiom.turn:llm_backend` (`mods/axiom.turn/main.py:43-52`).
- **Cascade de dépendances correcte** dans le résolveur (`axiom/kernel/resolver.py:69-88`) : couper
  `axiom.world` désactive bien tout ce qui en dépend, cycles et conflits détectés.
- **Les mods officiels n'utilisent aucun patch** (aucun `ctx.patch` / `@patchable` dans `mods/`)
  → D9 respecté. **[LU]**
- **Vrai déménagement de code pour plusieurs features** : `inventory.py`, `time_system.py`,
  `stat_dynamics.py`, `living_memory.py`, `image_generator.py` vivent maintenant dans `mods/`
  (`mods/axiom.inventory/inventory.py`, etc.). **[LU]**
- **Les mods contribuent vraiment à l'UI Qt** via des emplacements consommés par l'UI :
  `axiom.ui.qt:sidebar_widget` (inventaire, timeline) et `axiom.ui.qt:settings_tab` (providers,
  mémoire, images) — `mods/axiom.ui.qt/ui/constants_sidebar.py:107-135`,
  `settings_dialog.py:284-288`. Avec tous les mods optionnels désactivés, la fenêtre Qt se construit
  sans erreur. **[EXÉCUTÉ]**
- **Message clair si le tour manque** (`axiom/session.py:309-313`) au lieu d'un plantage obscur.
- **Tests** : la majorité des fichiers de tests des mods passe (voir §3, I9).

---

## 3. Problèmes, par gravité

### BLOQUANT

#### B1. Le noyau dépend des mods ; le paquet « noyau seul » est cassé
- **Constat.** Six modules du noyau sont des proxys qui remplacent leur propre entrée dans
  `sys.modules` par le module du mod : `axiom/inventory.py:12-17`, `axiom/stat_dynamics.py:12-17`,
  `axiom/living_memory.py:12-17`, `axiom/time_system.py:12-17`, `axiom/image_generator.py:12-17`
  (et `core/st_parser.py:25`). Le noyau s'en sert à **20 endroits** : `arbitrator.py:515,552,1040,1908`,
  `compile.py:27,216`, `decompile.py:38`, `saves.py:142,151,402,416,495,520,532,796`,
  `session.py:217,231`, `storage_registry.py:118`, `turn_batch.py:94,98`. **[LU]**
- **Test d'import sans `mods/`** (copie de `axiom/` seule dans `/tmp/.../pkg`) **[EXÉCUTÉ]** :
  - `import axiom`, `axiom.session`, `axiom.kernel` : OK ;
  - `import axiom.compile` / `axiom.decompile` : `ImportError: cannot import name 'CalendarConfig'
    from 'axiom.time_system'` ;
  - `axiom compile …` (CLI) : même erreur → **impossible de compiler un univers** ;
  - `axiom mods list` : « No mods found » → aucun tour possible (`NoTurnPipelineInstalledError`) ;
  - `import axiom.inventory` sans mod : réussit **silencieusement** mais module vide
    (`except Exception: _impl = None`) → l'erreur surgira plus tard, loin de la cause.
- **Le garde-fou de packaging est contourné.** `export_engine.check_headless` interdit
  `import mods` par regex (`export_engine.py:47-49`) ; les proxys passent par
  `importlib.import_module("mods…")` sous forme de chaîne, ce que la regex ne voit pas →
  `check_headless(Path('axiom'))` renvoie `[]` **[EXÉCUTÉ]**. Le CHANGELOG le présente comme une
  solution (`audit-and-fix-mods-decoupling/CHANGELOG.md:36` : « au lieu d'imports statiques AST »).
  Or `pyproject.toml:59` ne publie que `axiom*` : **le paquet PyPI n'a ni tour, ni monde, ni temps.**
- **Garde-fous violés** : D1, D3 (les proxys n'ont aucune date de fin et sont présentés comme
  « rétrocompatibilité propre »), D-8.
- **Concrètement** : un développeur qui fait `pip install axiomai-engine` obtient un moteur qui ne
  peut ni compiler un univers ni jouer un tour. Et dans le repo, « décocher » un mod ne débranche
  pas le code : le noyau l'importe quand même.
- **Correction** : inverser la dépendance. Ce dont le noyau a besoin (ex. `CalendarConfig` pour
  compiler) doit soit rester dans le noyau sous une forme générique, soit passer par des hooks de
  compilation (§11 du DOC d'origine : `compile/decompile` par mod). Supprimer les proxys, et faire
  échouer `check_headless` sur toute chaîne `"mods.` dans `axiom/`.

#### B2. « Le tour est un mod » : non — `axiom.turn` est une coquille, le pipeline est resté dans le noyau
- **Constat [LU].** `mods/axiom.turn/main.py` (177 lignes utiles) importe `ArbitratorEngine`
  depuis `axiom/arbitrator.py:11` et appelle `engine.step_1_gather_context` … `step_6_stage_mutations`
  (`main.py:81-149`). Tout le travail (stats, RAG, lieux, lore, faits, Timekeeper, modificateurs,
  règles, écriture) est dans `axiom/arbitrator.py` (1 955 lignes), `axiom/prompts.py` (1 118 lignes,
  schéma JSON du LLM en dur, `prompts.py:56-75`, y compris `inventory_changes`), `axiom/turn_batch.py`
  (champs `inventory_mutations`, `modifier_mutations`, `timeline_entries` en dur), `axiom/rules.py`,
  `axiom/modifiers.py`, `axiom/chronicler.py`, `axiom/memory.py`, `facts.py`, `observations.py`,
  `mental_models.py`, `factextract.py`, `consolidate.py`, `axiom/backends/`, `axiom/retrieval/`.
  Total mesuré : **≈ 9 400 lignes de code JDR/LLM dans `axiom/`** contre ≈ 4 300 lignes (hors UI)
  dans les mods de jeu.
- **Le noyau connaît les mods par leur nom [LU]** : `arbitrator.py:470-471`
  (`has_service("living_memory")`), `510-511` (`has_hook("axiom.turn:arbitrate_stats")`),
  `651-652` (`has_service("time")`), `404` (`get_service("rag")`) ; `session.py:171,183,204,216,613,740`
  (`"providers"`, `"rag"`, `is_mod_enabled("axiom.rag")`, `is_mod_enabled("core.stat_dynamics")`…).
  C'est exactement le symptôme D2 « `if mod_id == "axiom-turn"` ».
- **La logique du temps est dans le noyau, pas dans le mod temps [LU]** : appel LLM du Timekeeper et
  durées par défaut par rythme de scène dans `arbitrator.py:654-697` ; le mod `axiom.time` ne fait
  que réécrire `elapsed_minutes` après coup (`mods/axiom.time/main.py:56-65`).
- **Code dupliqué [LU]** : chaque étape garde un chemin « sans registre »
  (`if self.kernel_registry is None`, `arbitrator.py:550, 569, 824, 851, 905-917`) qui duplique les
  mods : boucle du RulesEngine (`arbitrator.py:851-901` ≈ `mods/axiom.world/main.py:186-232`),
  validation d'inventaire (`arbitrator._validate_inventory_change:1878` ≈
  `mods/axiom.inventory/main.py:107-213`), indexation RAG (`arbitrator.py:914-918` ≈
  `mods/axiom.rag/main.py:127-148`). En jeu normal ces branches sont mortes (la `Session` crée
  toujours un registre), mais elles restent et divergeront.
- **Garde-fous** : D1, D2, D3, D5 ; vision §1.4 (« Axiom peut servir à autre chose que du JDR,
  puisque le tour est lui-même un mod ») ; D-3 (« entités/stats dans un mod monde »).
- **Concrètement** : un auteur qui veut « remplacer le tour » ou « remplacer la mémoire » (exemples
  de succès du §1.4) ne le peut pas : il devrait réécrire l'Arbitre du noyau.
- **Correction** : déplacer réellement `arbitrator.py`, `prompts.py` (partie narration),
  `turn_batch.py` (partie jeu) dans `mods/axiom.turn/` ; supprimer les branches
  `kernel_registry is None` ; remplacer `has_service("time")` etc. par des emplacements/hooks
  déclarés par `axiom.turn` lui-même.

#### B3. Régression : la boucle de correction de l'Arbitre ne fonctionne plus
- **Constat [EXÉCUTÉ].** Même scénario sur `main` (export `git archive` dans `/tmp`) et sur `mods` :
  tour 1, le LLM modifie une entité inexistante `ghost_zz` ; on regarde si le prompt du tour 2
  contient la correction.
  - `main` : `rejected_t1: 1 | correction in turn-2 prompt: True`
  - `mods` : `rejected_t1: 1 | correction in turn-2 prompt: False`
- **Causes [LU]** : (1) `axiom.world` calcule `rejection_messages` mais ne s'en sert jamais
  (`mods/axiom.world/main.py:129,172`) — l'ancien code appelait `self._queue_correction(...)` ;
  (2) `axiom.turn` recrée un `ArbitratorEngine` neuf à chaque tour (`mods/axiom.turn/main.py:19-24`,
  le cache `_ENGINE_CACHE` ligne 16 n'est jamais utilisé), donc toute correction mise en file
  (modificateurs, inventaire) est perdue. Effet secondaire probable **[SUPPOSÉ, LU]** : le Lore Book
  est ré-indexé à chaque tour (`_lore_synced` est par moteur, `arbitrator.py:238,1441-1446`).
- **Concrètement** : quand le narrateur se trompe (stat inconnue, entité inexistante), il n'est plus
  prévenu au tour suivant et répète l'erreur. Aucun test ne l'a vu (le harnais golden ne le vérifie pas).
- **Correction** : faire passer les rejets par `ctx` (ex. `ctx.corrections`) et les réinjecter au
  tour suivant via le stockage de save, pas via l'état d'un objet ; ajouter ce cas au harnais golden.

#### B4. Isolation des plantages inversée : un bug de mod tiers fait échouer **tous** les tours
- **Constat.** Le registre avale toute exception d'un hook (`axiom/kernel/registry.py:79-104`).
  Or **tout le tour** est un seul hook (`axiom.kernel:execute_step`). Les gestionnaires
  `output_fields` des autres mods sont appelés *dans* ce hook sans protection
  (`mods/axiom.turn/main.py:135-143`). Résultat : n'importe quelle exception (mod tiers, ou LLM)
  annule le tour entier et la `Session` lève `RuntimeError("Turn pipeline mod returned no result.")`
  (`axiom/session.py:336-338`).
- **Preuves [EXÉCUTÉ]** :
  - L'exemple « modèle canonique » du `DOC.md` actuel, copié tel quel dans un mod
    (`tmpmods/review.docexample`) : `AttributeError: 'TurnWriteBatch' object has no attribute
    'stage_event'` → `RuntimeError Turn pipeline mod returned no result.` Le tour est perdu.
  - `tests/test_providers_illustrations_mods.py::test_full_turn_with_all_official_mods_and_implicit_llm` :
    la vraie erreur (`LLMConnectionError: … model 'llama3.2' not found`) est journalisée puis
    remplacée par « Turn pipeline mod returned no result ». Dans Qt, `workers/narrative_worker.py:96`
    attrape `LLMConnectionError` pour afficher « LLM unreachable — check your Ollama server or API
    key » : ce message utile ne peut plus jamais s'afficher.
- **Garde-fou** : DOC d'origine §6.1 (« si un mod lève une exception, sa contribution est ignorée,
  le mod est désactivé et signalé, **le step continue** »).
- **Concrètement** : un mod communautaire mal écrit rend Axiom injouable, et les erreurs de clé API ou
  de modèle s'affichent comme une erreur interne incompréhensible.
- **Correction** : ne pas isoler le hook du tour lui-même (laisser remonter `LLMConnectionError`),
  mais isoler chaque contribution de mod *dans* le tour (try/except par gestionnaire `output_fields`,
  par section de prompt, par filtre), avec désactivation + signalement du mod fautif.

#### B5. Test décisif de la vision (§1.4) : « tout décoché » ne donne aucun chat
- **Constat [EXÉCUTÉ]** : tous les mods désactivés → `NoTurnPipelineInstalledError: No turn pipeline
  installed. Ensure 'axiom.turn' mod is loaded.` ; `main.py` refuse de démarrer si `axiom.ui.qt` est
  décoché (`main.py:418-433`), `main_web.py` idem (`main_web.py:2846`). Il n'existe aucun mod
  « chat minimal + chargement de modèle » ; et même l'UI Qt dépend de `axiom.turn`, qui dépend de
  `axiom.world` (`mods/axiom.ui.qt/mod.toml`, `mods/axiom.turn/mod.toml:9-10`) : **pas de chat sans
  le modèle de monde JDR**.
- **Cascade muette [EXÉCUTÉ]** : décocher `axiom.world` désactive en réalité 11 mods (turn, cli,
  ui.qt, ui.web, providers, rag, illustrations, inventory, time, living_memory…) ; il ne restait que
  `help_system` et `sillytavern`. `bootstrap_all_mods` ignore `report.disabled_mods`
  (`axiom/kernel/loader.py:252-264`) et `axiom mods list` affiche toujours ces 11 mods comme
  **« enabled »**. Le DOC d'origine §1.4 exige « les mods qui en dépendent se désactivent avec lui,
  **en le signalant** ».
- **Concrètement** : l'utilisateur qui décoche « Monde » ne peut plus rien faire, et la liste lui dit
  que tout est actif.
- **Correction** : créer un mod « chat » minimal (prompt + historique + backend) indépendant de
  `axiom.world` ; faire dépendre les UI d'un « fournisseur de tour » abstrait (`provides`) ; afficher
  dans `mods list` et dans l'UI le statut réel calculé par le résolveur.

#### B6. Stockage des mods : les politiques déclarées ne sont pas implémentées
- **Constat [LU]** :
  - Il n'y a **pas de `ctx.store`** dans `ModContext` (`axiom/kernel/context.py:16-94`), alors que
    c'est le cœur de D6 (« le stockage de save doit être plus simple à utiliser qu'un `self.x` »).
  - **Pas de table `versioned_kv`** (aucune occurrence de `from_step`/`to_step` dans le code) :
    le mot `VERSIONED_KV` n'est qu'une étiquette posée sur les tables de définition d'univers
    (`axiom/storage_registry.py:150-178`).
  - La section `[storage]` des manifestes est parsée (`axiom/kernel/manifest.py:222-253`) **mais
    jamais lue** par personne. Les déclarations des mods sont donc décoratives, et parfois fausses
    (`axiom.world` déclare `entities = { policy = "versioned_kv" }`, `axiom.living_memory` déclare
    `facts` sans nom de table).
  - Le registre de stockage est **une liste tenue à la main dans le noyau** contenant toutes les
    tables de jeu (`Item_Instances`, `Facts`, `Mental_Models`, `Active_Modifiers`, `Timeline`…,
    `storage_registry.py:150-226`) avec des fonctions de rewind/fork spécifiques à l'inventaire, aux
    modèles mentaux, etc. (`storage_registry.py:42-143`).
  - `axiom.rag` et `axiom.illustrations` s'enregistrent via `register_custom_storage` du noyau
    (`mods/axiom.rag/main.py:163-170`), **pas via `ctx`** → non retiré à la désactivation (D11).
- **Garde-fous** : D6, D7 (« aucune liste de tables tenue à la main »), D11, D1.
- **Concrètement** : un mod tiers (la « jauge de faim » du §1.4) n'a aucun endroit officiel où
  stocker sa valeur pour qu'elle suive le rewind. Il devra créer sa propre table et écrire son propre
  rewind — exactement ce que la vision voulait interdire.
- **Correction** : implémenter `ctx.store` (`get/set` sur une table noyau `Mod_KV(save_id, mod_id,
  key, value, from_step, to_step)`), faire lire `[storage]` par le chargeur, déplacer les specs des
  tables de jeu dans les manifestes des mods concernés.

### IMPORTANT

#### I1. `output_fields` : le routage marche, la contribution au schéma n'existe pas
- **[EXÉCUTÉ]** Inventaire désactivé, le prompt système contient toujours la consigne
  `inventory_changes` (`prompt_has_inventory_rule: True`) : le schéma JSON est figé dans
  `axiom/prompts.py:56-75`. Aucun code n'ajoute au schéma les champs contribués par les mods.
  Un mod tiers reçoit son champ **seulement si** le LLM a l'idée de le produire ; à lui d'écrire la
  consigne dans une section de prompt.
- DOC d'origine §7.1.1 : « un mod contribue un champ au schéma de sortie (**sous-schéma + consigne**)
  et reçoit la valeur parsée ». Moitié faite.
- **Concrètement** : on paie des tokens pour décrire un inventaire désactivé, et la « jauge de faim »
  d'un mod tiers ne sera jamais demandée au LLM sans bricolage.
- **Correction** : accepter des contributions `{"name", "schema", "instruction", "handler"}` et
  générer le bloc JSON à partir de l'emplacement.

#### I2. Le hook `axiom.step:gather_context` est appelé deux fois par tour
- **[EXÉCUTÉ]** Compteur enregistré sur ce hook : **2 appels pour 1 tour**. Causes :
  `axiom/arbitrator.py:501-502` et `mods/axiom.turn/main.py:82`.
- **Concrètement** : un mod qui ajoute un souvenir ou incrémente une jauge à cette étape le fait en double.

#### I3. Sections de prompt : ordre ignoré, formats rejetés en silence
- **[LU]** Le tri par `depth` (`mods/axiom.turn/main.py:88`) ne s'applique qu'aux dicts ; or presque
  toutes les contributions officielles sont des fonctions → clé 0 pour toutes, ordre = ordre de
  chargement. Un tuple est ignoré sans message (`main.py:108-109` ; **[EXÉCUTÉ]** : la section
  « soif » de l'exemple du DOC n'apparaît pas dans le prompt). Une position inconnue est ajoutée à
  `ctx.rag_chunks` **après** la construction du prompt (`main.py:118-119`) → perdue.
- Le format `(id, position, profondeur, texte, ordre)` du §7.1.3 n'est pas implémenté.
- **[SUPPOSÉ, LU]** En mode mémoire « living », les faits sont injectés deux fois : préfixés dans
  `ctx.rag_chunks` par le noyau (`arbitrator.py:473-499`) puis rendus par la section RAG
  (`mods/axiom.rag/main.py:96-125`), et une seconde fois par la section `axiom.living_memory`
  (`mods/axiom.living_memory/main.py:92-144`).

#### I4. Les mods officiels utilisent des API internes non publiques
- **[LU]** `ModContext` n'offre aucun moyen public de lire un emplacement ; les mods officiels lisent
  donc l'attribut privé `ctx._registry` : `mods/axiom.turn/main.py:175`,
  `mods/axiom.providers/main.py:64-79`, `mods/axiom.ui.qt/main.py:32-39`, `mods/axiom.ui.web/main.py:27-40`.
  `axiom.turn` appelle aussi `session._load_history()` (`main.py:60`).
- Les mods importent directement 13 modules internes non versionnés : `axiom.schema` (12 fois),
  `axiom.facts` (4), `axiom.db_helpers` (4), `axiom.observations` (3), `axiom.storage_registry`,
  `axiom.arbitrator`, `axiom.chronicler`, `axiom.memory`… (comptage `grep`).
- Un mod tiers *peut* techniquement faire pareil (Python, pas de sandbox), donc ce n'est pas un
  privilège au sens strict ; mais l'API réellement utilisée n'est ni documentée ni versionnée (D12),
  et les mods officiels ne servent pas d'exemple « API publique » (D2, §12).
- **Correction** : ajouter `ctx.get_slot()` / `ctx.slot_contributions()` publics ; exposer une petite
  façade versionnée (connexion DB, historique) et y migrer les mods officiels.

#### I5. Interfaces : des lanceurs déguisés en mods, logique de jeu encore dans les UI
- **[LU]** `mods/axiom.ui.web/main.py` (109 lignes) importe `main_web` à la racine
  (`main.py:56`) : le vrai serveur web (2 891 lignes) n'a pas bougé. `mods/axiom.ui.qt/main.py:44-52`
  fait `import main` (racine). `main.py:20` importe l'UI en dur depuis `mods.axiom.ui.qt…` sans passer
  par le chargeur. Le mod `axiom.cli` (40 lignes) appelle `axiom/cli/play.py` (359 lignes, noyau).
- **Bug [LU]** : `main_web.py:2859` importe `axiom.kernel.bootstrap`, **qui n'existe pas** ; l'erreur
  est avalée (`except Exception: logger.exception`) — le démarrage web ne charge donc pas les mods
  (ils le seront plus tard, à la création de la session).
- **Logique de jeu dans l'UI web (D4/D5) [LU]** : rattrapage de la mémoire vivante
  (`main_web.py:1645-1662`, absent de Qt), repli de déplacement d'inventaire écrivant en base
  (`main_web.py:1590-1599`), inférence des stats dynamiques (`main_web.py:2048-2056`).
  Côté Qt, un ancien ordonnanceur de faits (`tabletop_view.py:121-123, 1235-1282`) reste en code mort.
- **Qt reconstruit tout à chaque tour [LU + EXÉCUTÉ]** : `tabletop_view.py:674` crée une `Session`
  par tour sans registre → `bootstrap_all_mods` est relancé à chaque tour (`session.py:156-158`) :
  ré-exécution du `main.py` de chaque mod, nouveau registre global. Mesuré : 0,6 s au premier, 0,01 s
  ensuite — coût faible, mais l'état des services est recréé à chaque tour.
- **Dépendance non déclarée [EXÉCUTÉ]** : l'UI Qt importe `mods.axiom.help_system` à 28 endroits
  sans le déclarer. Mod *désactivé* : OK. Mod *désinstallé* (dossier absent, copie dans `/tmp`) :
  la fenêtre plante au démarrage avec `TypeError: 'module' object is not callable`
  (`hub_view.py:100`) — erreur incompréhensible due au chercheur d'imports de `mods/__init__.py:75-79`
  qui fabrique un paquet vide pour un chemin inexistant au lieu de lever `ImportError`.
- **UI web** : les emplacements `axiom.ui.web:side_panel/settings_tab/action_button` sont déclarés,
  mais **aucun mod n'y contribue** et le SPA (`web/`) ne lit pas `side_panels` (aucune occurrence).
- **Symlink `mods/axiom_ui_qt -> axiom.ui.qt`** (commit `659c21b`) : inutile (le chercheur gère déjà
  les alias soulignés, `mods/__init__.py:31-44`), découvert deux fois sous Linux (même id), et
  transformé en simple fichier texte sous Windows sans support des symlinks. À supprimer.

#### I6. Mode sans échec : les mods officiels restent actifs (privilège par préfixe)
- **[LU]** `is_official_mod` = id commençant par `axiom.` ou `core.` (`axiom/kernel/loader.py:52-60`) ;
  le mode sans échec ne coupe que les autres. Le DOC d'origine §4.1 dit « démarrer **sans aucun mod** ».
  N'importe quel auteur peut nommer son mod `axiom.truc` pour être « officiel ». Garde-fou D2.

#### I7. Chargement dépendant du dossier courant ; ordre utilisateur et versions ignorés
- **[EXÉCUTÉ]** `discover_installed_mods` cherche `Path("mods")` et `Path("dist/mods")` **relatifs au
  dossier courant** (`axiom/cli/mods_cmd.py:65`) : lancé depuis un autre dossier, « No mods found ».
- **[LU]** `bootstrap_all_mods` n'envoie jamais l'ordre utilisateur au résolveur
  (`loader.py:253`, `user_order` absent) : pas de « load order » façon Skyrim, ordre alphabétique.
  Les contraintes de version (`">=1.0.0"`) ne sont jamais comparées (`resolver.py:69-88` ne teste que
  la présence).

#### I8. `axiom.providers` est décoratif
- **[LU]** Les UI construisent le LLM elles-mêmes via `axiom.config.build_llm_from_config`
  (`axiom/config.py:463`, appelé par `tabletop_view.py`, `main_web.py`, `workers/db_tasks.py`,
  `axiom/cli/play.py`, `axiom/session.py`…) et le passent à la `Session`. Désactiver le mod ne change
  donc rien ; les backends restent dans `axiom/backends/`. Le noyau « connaît les LLM » (D1).
  Les pilotes sont enregistrés hors `ctx` (`svc.register_driver`, `mods/axiom.providers/main.py:151-153`, D11).

#### I9. Tests : majoritairement verts, mais non hermétiques et polluants
Résultats **[EXÉCUTÉ]** (fichier par fichier, config isolée) :

| Fichier | Résultat |
|---|---|
| `mods/community.survival/tests/test_survival.py` | 1 passed |
| `mods/core.stat_dynamics/tests/test_stat_dynamics_mod.py` | 7 passed (simple ré-export de `tests/…`) |
| `tests/test_world_turn_mods.py` | 6 passed |
| `tests/test_time_inventory_mods.py` | 5 passed |
| `tests/test_memory_mods.py` | 5 passed |
| `tests/test_stat_dynamics_mod.py` | 7 passed |
| `tests/test_mods_decoupling_and_effectivity.py` | 7 passed |
| `tests/test_kernel_loader.py` | 13 passed |
| `tests/test_mod_localization.py` | 9 passed |
| `tests/test_golden_step.py` | 5 passed |
| `tests/test_mod_ui_deactivation.py` | 6 passed |
| `tests/test_mods_dialog_ui.py` | 5 passed |
| `tests/test_phase6.py` | 30 passed |
| `tests/test_providers_illustrations_mods.py` | **3 failed**, 2 passed |
| `tests/test_sillytavern_mod.py` | **1 failed**, 6 passed |
| `tests/test_help_system_mod.py` | **1 failed**, 6 passed |
| `tests/test_ui_mods_and_cli.py` | **1 failed**, 7 passed |

- Les 6 échecs viennent de deux causes : (a) les tests exigent des artefacts **non versionnés** dans
  `dist/mods/` (`axiom.providers.axmod`, `store_index.json`…, `dist/` est dans `.gitignore`) ;
  (b) un test appelle **un vrai Ollama** sur `localhost:11434` (modèle `llama3.2` introuvable).
- **Pollution observée pendant ma revue** : un test du créateur de mods (lancé par un autre relecteur)
  a déposé `dist/mods/community.fatigue-0.1.0.axmod` dans le repo ; comme `dist/mods` est un dossier
  de découverte, **ce mod de test a été chargé automatiquement** dans mes scénarios (il apparaissait
  même avec « tout décoché », car un mod inconnu est actif par défaut). Il s'accroche à
  `axiom.turn:after_step`, un hook qui n'existe pas (le vrai est `axiom.step:after_step`) — sans
  aucun avertissement. Le fichier a disparu depuis (nettoyage par un autre test).
- `community.survival` (mod d'exemple tiers) est livré **actif par défaut**, modifie le prompt de
  tout le monde, et ne déclare pas sa dépendance à `axiom.turn` dont il utilise l'emplacement.

### MINEUR
- `_ENGINE_CACHE` déclaré mais jamais utilisé (`mods/axiom.turn/main.py:16`) ; `rule_chain_warning`
  n'est plus jamais positionné par `axiom.world` (avertissement de boucle de règles perdu).
- `validate_inventory_change` écrit en base et `commit()` pendant la *validation*
  (`mods/axiom.inventory/main.py:143-148, 213`), hors du tampon transactionnel du tour (phase 0d).
- Imports en boucle : les mods importent leur propre code via `mods.axiom.X…` puis se replient sur
  `axiom.X` (`mods/axiom.inventory/main.py:16-41`, idem time, stat_dynamics) — qui est un proxy
  vers… le mod. Le repli ne peut jamais servir.
- `ctx.patch()` sur une cible inexistante (`"axiom.world:calculate_stamina"`, exemple du DOC) est
  accepté sans erreur au chargement **[EXÉCUTÉ]**.

---

## 4. Écarts entre la doc / TODO et le code

| Affirmation | Réalité |
|---|---|
| `DOC.md` actuel, §I : « Le noyau (`axiom/`) ne contient plus aucune règle métier propre au JDR, aucun prompt en dur » | Faux : `axiom/arbitrator.py` (1 955 l.), `axiom/prompts.py` (schéma JSON en dur l. 56-75), `rules.py`, `modifiers.py`, `chronicler.py`… (B2) |
| `DOC.md` actuel, « Modèle canonique d'un `main.py` » | Cassé 3 fois : la section renvoyée en tuple est ignorée, `write_batch.stage_event` n'existe pas (fait échouer le tour), `axiom.world:calculate_stamina` n'existe pas et aucun `@patchable` n'existe dans le code **[EXÉCUTÉ]** |
| `DOC.md` actuel : « Registre de Sauvegarde Déclaratif (EVENTS, STEP_KEYED, VERSIONED_KV, CUSTOM) » ; tableau des mods avec leur politique | `versioned_kv` et `ctx.store` n'existent pas ; `[storage]` jamais lu (B6) |
| `TODO.md` phase 1 : « [x] Stockage par politiques » | Idem B6 |
| `TODO.md` phase 5 : « [x] Packaging PyPI headless micro-kernel (exclusion mods/UI) » | Le paquet ne compile pas d'univers et n'a pas de tour (B1) |
| `audit-and-fix-mods-decoupling/DOC.md:5-21` : « détachement total du code du noyau », « shims… sans violer l'indépendance structurelle » | Le noyau garde les branches de repli et la logique du temps ; les shims contournent `check_headless` (B1, B2) |
| `verification-and-functional-audit/CHANGELOG.md:9` : « le core n'exécute pas de règles fantôme si `axiom.world` est désactivé » | Vrai, mais parce que **plus aucun tour** ne tourne (cascade), et sans le signaler (B5) |
| `DOC.md` actuel : « `--safe-mode` neutralise tout mod tiers » | Vrai, mais la vision demandait « sans aucun mod » (I6) |
| `mods/axiom.turn/mod.toml:6` : « validation Arbitrator et boucle de correction » | La boucle de correction ne fonctionne plus (B3) |
| `mods/axiom.ui.web/mod.toml` : « Gestionnaire de mods… » + emplacements web | Aucun mod n'y contribue, le SPA ne les lit pas (I5) |

---

## 5. Questions pour Frosoore / le propriétaire

1. **Proxys `axiom/inventory.py` & co** : quelle est leur date de fin (D3) ? Qui en a encore besoin
   hors du repo ? Peut-on les supprimer et faire passer `compile/decompile` par des hooks de mod ?
2. **Déplacer l'Arbitre** : êtes-vous d'accord que `arbitrator.py` + la partie narration de
   `prompts.py` + `turn_batch.py` doivent physiquement aller dans `mods/axiom.turn/` avant de
   déclarer la phase 2 terminée ? (C'est la condition pour que « remplacer le tour » soit possible.)
3. **Boucle de correction** : était-elle volontairement abandonnée ? Sinon, c'est une régression à
   corriger avant toute fusion (B3).
4. **Isolation** : faut-il qu'une erreur LLM (clé, modèle) remonte telle quelle à l'UI ? (Je pense
   que oui ; aujourd'hui elle est masquée, B4.)
5. **« Tout décoché »** : la vision promet « un chat + chargement de modèle ». Qui écrit ce mod
   minimal, et l'UI Qt doit-elle dépendre de lui plutôt que de `axiom.turn` + `axiom.world` ?
6. **Stockage** : `ctx.store` / `versioned_kv` sont au cœur de D6/D7 et de l'exemple « jauge de faim ».
   Ont-ils été reportés volontairement ? Si oui, le TODO doit le dire.
7. **Mode sans échec** : décision de garder les mods `axiom.*`/`core.*` actifs — à tracer en §14
   ou à corriger (le DOC d'origine dit « aucun mod »).
8. **`dist/mods/` comme dossier de découverte** : est-ce voulu ? Il mélange artefacts de build,
   artefacts de tests et mods installés.
9. **`community.survival` actif par défaut** chez tous les utilisateurs : voulu ?
