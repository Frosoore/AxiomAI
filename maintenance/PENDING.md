# PENDING — tickets à étudier

> Règle de vie du fichier : un ticket **terminé** part dans `DONE.md` (trace condensée) et
> **disparaît d'ici**, index compris. Ne restent dans PENDING que les tickets ouverts,
> différés ou en attente d'une validation utilisateur.

## Index des tickets

| N°        | Titre                                                          | Statut    |
|-----------|----------------------------------------------------------------|-----------|
| TICKET-017| Temps causal : `major_event_description` ignoré + **time-skip Chronicler** (spec §6.4) | ouvert (partiellement couvert par TICKET-018, domaine Pilier 5/Gemini) |
| TICKET-057| 📋 Doc intégrée à l'app GUI (tooltips, bouton « explique cette page », quick tour, annuaire) | 🔄 ouvert — **contenu jugé trop succinct (2026-06-13), à enrichir** (cf. [[project-doc-chantier]]) |
| TICKET-059| Test threadé flaky : `test_generation_cancel.py::test_registre_cancel_active_generations` (passe en isolation, flanche sous charge) | ouvert — fiabilité de la suite |
| TICKET-061| i18n : placeholders/titres encore en dur dans les éditeurs du Studio | ouvert — quick win |
| TICKET-062| 🚀 **Préparation bêta publique** : items 1/2/4 ✅ **validés GUI (2026-06-13)** ; reste **check Windows** + **screens/GIF** | ouvert — chantier, priorité haute |
| TICKET-063| Backend `openai` : modèles reasoning (gpt-5/o-series) incompatibles avec le payload actuel (`max_tokens`→`max_completion_tokens`, `temperature` figée à 1) | ouvert — suite de `feature-cloud-text-providers` |
| TICKET-064| Backend d'**images** Venice AI (`POST /image/generate`, clé `venice_api_key` déjà en config) | ouvert — idée feature |
| TICKET-065| `world_tension_level` : **deux casses de clé** (`World_Tension_Level` seedée/lue par le Chronicler vs `world_tension_level` écrite par Studio/compilateur) → le curseur de tension du Studio est sans effet réel | ouvert — bug latent |
| TICKET-067| Suite de tests : **segfault** quand `test_ambiance_manager.py` (Qt multimédia) précède `test_arbitrator.py` (import torch→triton) — `pytest tests/` plante, chaque moitié passe seule | ouvert — fiabilité de la suite, environnement (Python 3.14/Fedora) |
| TICKET-069| **Validation Windows sur machine réelle** : 🔄 **gros lot fait les 2026-06-14** (crash WinError 32 résolu, classe connexion-non-fermée corrigée moteur+app, suite 753✅, **`run.bat`/startup_check OK + `main.py` atteint la boucle d'événements sans crash**, **audio requalifié quasi nul** : Ogg/FLAC/AAC supportés sur Win11 + aucun asset audio embarqué — cf. `TICKET-062-windows-support/CHANGELOG.md`). Reste : **un vrai tour de jeu GUI** + génération d'images locale | ouvert — bien allégé |
| TICKET-070| **torch ne charge pas sous Windows** (`OSError WinError 126`) : **VC++ Redistributable x64 manquant**. App dégradée gracieusement (no-op + warning) ; **diagnostic FAIL actionnable** (`_check_embedding_runtime`) **+ alerte GUI au lancement** avec lien de téléchargement (`ui/runtime_check.py`, i18n ×10, marqueur « ne plus afficher »). `requirements.txt` impossible (composant système, pas un paquet pip). Reste action utilisateur → **installer vc_redist.x64.exe** | ouvert — environnement (code côté app = FAIT) |
| TICKET-083| **Croyances : fuite temporelle au rewind** (`created_turn_id = min(tours des sources)` → une croyance survit à un rembobinage avant qu'elle ait été consolidée) | ouvert — QA Hindsight 2 (2026-06-19), sévérité basse-moyenne |
| TICKET-084| **Budget de prompt `living` = jusqu'à 3× `rag_chunk_count`** (croyances + faits + chunks narratifs cumulés) | ouvert — QA Hindsight 2 (2026-06-19), coût tokens |
| TICKET-085| **Cache BM25 : `collection.get()` plein corpus tourne encore au cache-hit** (seul le build d'index est caché) | ouvert — QA Hindsight 2 (2026-06-19), micro-opt mineure |
| TICKET-088| **`fork_save` ne copie pas** Facts/Observations/Mental_Models/Snapshots/Modifier_Snapshots (mémoire living + snapshots de rewind perdus au fork d'une save embarquée) | ✅ résolu (IDs entiers, remappage sources, summary filtré, fork externe unifié) |
| TICKET-089| **`package._RUNTIME_TABLES` omet** Facts/Observations/Mental_Models **+ `Item_Instances`/`Session_Lore`** (données de partie d'une save embarquée peuvent fuir dans un `.axiom` « définition seule ») | ✅ résolu (`all_runtime_table_names()` utilisé) |
| TICKET-090| **`paths` : pas de `get_universes_dir()`**, `UNIVERSES_DIR` figé à l'import (insensible à `AXIOM_DATA_DIR`/`configure`) alors que saves/vector le sont → isolation asymétrique | ouvert — QA fs 2026-06-21, archi/cohérence |
| TICKET-099| **Clés Fireworks intégrées expirées (2026-06-30) mais `BUILTIN_KEYS_ENABLED = True`** → un nouvel utilisateur est configuré par défaut sur des clés mortes | ouvert — **décision utilisateur** (couper l'interrupteur ou renouveler le pool) |
| TICKET-100| **Rewind web/CLI ne rembobine pas ChromaDB** + ids `uuid4` → rejouer un tour **ajoute un doublon** (le RAG voit le « futur annulé ») | ✅ résolu (handlers déclarés dans `mod.toml` et implémentés dans `storage.py` pour RAG et illustrations) |
| TICKET-101| **Tour échoué ou annulé → `user_input` orphelin + `turn_id` décalé** (2 messages joueur d'affilée au tour suivant) | ✅ résolu (`resolve_tick` restaure l'état et l'UI Qt décrémente `_turn_id`) |
| TICKET-102| **Job mémoire living web sans verrou** : un rewind pendant l'appel LLM laisse des faits de tours annulés | ✅ résolu (`guarded_write` et vérification d'époque dans `_maybe_auto_canonize`) |
| TICKET-103| **`fork_save --turn` copie `Fired_Scheduled_Events` et `Session_Lore` postérieurs au point de fork** | ✅ résolu (filtrage tour N, `fork_item_instances` isolé du futur au tour 0) |
| TICKET-104| **`regenerate.py` : `.replace` d'une consigne absente** → bloc JSON stocké dans les variantes et renvoyé au LLM | ✅ résolu (strip JSON, prompt sections des mods et format `minimal_chat`) |
| TICKET-105| **`_pending_correction` non remise à zéro au rewind** (indice d'un tour annulé réinjecté une fois) | ✅ résolu (`correction_hint` dans `Event_Log`, rembobinable) |
| TICKET-106| **Audit et alignement de l'encapsulation / détachement total du noyau sur l'ensemble des autres mods officiels** | ✅ résolu (Phase 2 vrai déplacement) |
| TICKET-107| **11 clés de traduction manquantes dans les réglages et éditeurs Qt** (`settings_dialog`, `stat_editor`, `entity_editor`) | ouvert — i18n, repéré audit oct. 2026 |
| TICKET-108| **Robustesse petits LLM (Gemma 4B / KoboldCPP)** : dernier message ignoré (message system trailing) + règle universelle concise d'asymétrie d'information (secrets, lore, mystères) | ouvert — prompt engineering & ergonomie modèles légers |
| TICKET-109| **Export d'univers `.axiom` sans modpack recommandé/requis** (`axiom/package.py`) | ouvert — intégrité des univers moddés |
| TICKET-110| **`axiom.minimal_chat` : violation d'encapsulation via accès à `mod_ctx._registry`** | ✅ résolu (interface publique ModContext utilisée) |
| TICKET-111| **Noyau neutre (K12) : résidus JDR et imports LLM dans `axiom/kernel/`** (`KernelStepContext`, `registry.py`, `context.py`, `llm_creator.py`) | ouvert — découplage architectural |
| TICKET-112| **Harnais Golden : `_canonical_tables` omet les tables déclarées par les mods si appelé isolément** (`golden_harness.py:422`) | ✅ résolu (`_ensure_mod_storage()` appelé au préalable) |
| TICKET-113| **Manifeste de mod : section déclarative `[schema]` du `mod.toml` ignorée au parsing** (`manifest.py`) | ouvert — complétude spec 0e |
| TICKET-114| **Harnais Golden : omission des tables de stockage `custom` (`Observations`, `Mental_Models`, `Item_Instances`, `Active_Modifiers`)** (`golden_harness.py:429`) | ✅ résolu (13 tables peuplées et comparées, fork tour 8, mock 3e réponse, fix CHECK modifiers expirés) |
| TICKET-115| **`Mod_KV` : crash `UNIQUE constraint failed` sur réinsertion après delete + écritures anti-chronologiques permises** (`kv_store.py:46-85`) | ✅ résolu (frontière temporelle max et update sécurisé) |
| TICKET-116| **Tabletop Qt : désynchronisation de l'UI (`_turn_id` incrémenté, historique et chat pollués) en cas de tour échoué** (`tabletop_view.py:760-770`, `1329`) | ✅ résolu (restauration UI dans `_on_worker_error`) |
| TICKET-117| **Tabletop Qt : import inconditionnel de `axiom.help_system` faisant crasher l'app au lancement si le mod est absent** (`main_window.py:94`) | ✅ résolu (pont `help_bridge.py` créé, 27 imports non protégés éliminés, fallback default tr) |
| TICKET-118| **`axiom.minimal_chat` : absence de bascule automatique lors de la désactivation de `axiom.world`** (`minimal_chat/mod.toml`, `loader.py`) | ✅ résolu (promotion automatique de repli, cascade STATE_NEXT_LAUNCH pour mods non-hot) |
| TICKET-119| **Noyau : requêtes SQL directes sur la table `Timeline` d'`axiom.time` dans `axiom/saves.py` et `axiom/db_helpers.py`** | ✅ résolu (time_provider délégué au mod) |
| TICKET-120| **CLI : absence de gestionnaire de sauvegarde automatique (`set_rewind_backup_handler`) lors du rewind** (`play.py`, `saves_cmd.py`) | ouvert — frontière architecturale headless |
| TICKET-121| **UI Web : 100% de code mort dans les routes de mutation de la mémoire vivante (`main_web.py:356-495`)** | ✅ résolu (désindentation hors du except ImportError, tests passants) |
| TICKET-122| **UI Web : `/api/session/inventory/move` échoue systématiquement en HTTP 400 (`main_web.py:1601` vs `web/app.js:1079`)** | ✅ résolu (compatibilité dest_holder_kind / dest_holder_id, test web validé) |
| TICKET-123| **Pipeline du tour : injection des sections de prompt M6 erronée (`pos == "user"` écrase le reminder système, `"system"` collé après le JSON)** | ✅ résolu (ciblage vrai message user, system avant json, positions de prompt complètes) |
| TICKET-124| **UI Qt : widgets des mods ignorés par `continue` dans `settings_dialog.py:312` et `constants_sidebar.py:131`** | ouvert — intégration slots UI |
| TICKET-125| **Providers : `ProvidersService` incomplet pour 5 providers cloud (`claude`, `venice`, `fireworks`, `openai`, `openrouter`)** | ✅ résolu (drivers cloud enregistrés dans ProvidersService) |
| TICKET-126| **Paquet PyPI `export_engine.py` inutilisable sans `mods/` et vulnérabilité Zip Slip dans `store.py:290`** | ouvert — intégrité export/store |

Tickets 100→106 : issus du cadrage du système de mods (`Mods/`). Tickets résolus/clos : voir `DONE.md` (**086, 087, 091, 092→098 clos le 2026-09-22** ; 001→056 sauf 017, 058→060, **071**, **072→082** (lot Hindsight, commités), **+ lot validations GUI du 2026-06-13 : 050, 062 items 1/2/4, 066, 068**).
Réserves portées dans `DONE.md` : TICKET-058 (activer GitHub Pages — droits admin — puis
relancer le job `deploy`). TICKET-054 (i18n) **validé GUI le 2026-06-13**.


---

## TICKET-017 — Temps causal : `major_event_description` ignoré + time-skip Chronicler non implémenté

**⏳ OUVERT — partiellement couvert (2026-06-07).** Depuis TICKET-018, un grand saut temporel franchit
un palier de minutes et **déclenche bien le Chronicler** (le monde évolue pendant un long voyage), ce qui
couvre l'essentiel de l'intention §6.4. **Reste à faire** : le champ `major_event_description` renvoyé par
le Timekeeper n'est toujours **pas consommé** — soit l'exploiter (ex. forcer un World Turn sur événement
majeur explicite, indépendamment du palier), soit le retirer du prompt pour cesser de payer ces tokens.
Constat d'origine ci-dessous.

**Constat (`axiom/prompts.py:898,902-903` ; `axiom/arbitrator.py:300-311`).** Le prompt Timekeeper
demande au LLM un champ `major_event_description` (« Arrived at Hemlock », « Defeated the Goblin King »…),
mais `process_turn` ne lit que `elapsed_minutes` (l.310-311) : le champ est **parsé puis jeté**. On paie
des tokens pour une sortie inutilisée.

En parallèle, l'**edge case spec §6.4 « Time skip narratif »** (« si `elapsed_minutes > 480` (8h),
déclencher le Chronicler **avant** de retourner le résultat, pour que le monde évolue pendant le
voyage ») **n'est pas implémenté**. Les deux pointent vers la même fonctionnalité manquante : un grand
saut temporel devrait faire évoluer le monde.

**Ce qui serait à faire :**
- Soit **implémenter** le time-skip : si `elapsed_minutes` dépasse un seuil (ou si
  `major_event_description` est non-null), forcer un World Turn (`chronicler.force_trigger`) — ce qui
  redonne du sens au champ.
- Soit **retirer** `major_event_description` du prompt Timekeeper pour cesser de payer des tokens inutiles.

**Priorité :** moyenne (fonctionnalité spec manquante + léger gaspillage tokens). Lié à TICKET-018.

---

## TICKET-057 — 📋 Doc intégrée à l'app GUI — **contenu à enrichir**

**Feature planifiée** (décidée le 2026-06-12, cf. mémoire [[project-doc-chantier]]). Rendre l'app
auto-explicative, en **4 briques** :
1. **Tooltips au survol** de chaque élément.
2. **Bouton « explique cette page »** par page (présente chaque élément de la page).
3. **Quick tour** de départ.
4. **Annuaire global cherchable** (référence + explication des éléments de l'app).

**Structure livrée et VALIDÉE en GUI (2026-06-13)** : les 4 briques sont en place et marchent
(registre `ui/help_system.py::PAGES`, dialogues `ui/help_dialogs.py`, 10 langues, toggle tooltips).

**⚠ Reste à faire — le seul point qui rouvre le ticket (retour utilisateur 2026-06-13) :** le
**contenu textuel est jugé trop succinct**. Les explications (tooltips + « expliquer cette page »
+ annuaire) doivent être **étoffées** : phrases plus complètes, contexte/exemples, pourquoi de
chaque réglage, pas juste un libellé reformulé. Travail = ré-écriture des ~242 clés `doc_*` dans
`core/locales/*.toml` (EN d'abord, puis propagation 10 langues), périmètre `core/locales/` (pas de
code). Outil de repérage des trous : `python tools/doc_check.py`.

---

## TICKET-059 — Test threadé flaky : `test_registre_cancel_active_generations`

**Constat (2026-06-12, repéré en finissant TICKET-056).** `tests/test_generation_cancel.py::`
`test_registre_cancel_active_generations` est **non déterministe** : il passe **3/3 en isolation**
mais **flanche par intermittence** quand il tourne dans un lot chargé (ex. 9 suites en série). Le test
n'a **aucun rapport avec TICKET-055/056** (il utilise un fake `BlockingGen(BaseDbTask)` qui lève sa
propre chaîne « annulé » ; il n'exécute pas `populate_entities` ni de code traduit) — la flakiness
**préexiste**.

**Cause probable.** Le test lance un vrai `threading.Thread(target=task.run)`, attend des événements
via `started.wait(timeout=5)` / `worker.join`, et vérifie le **registre global** des générations
actives (`active_generation_count()`, `cancel_active_generations()`) + un signal Qt
`cancelled.connect(got.append, Qt.DirectConnection)`. Sous charge/ordonnancement de threads, une
fenêtre de course fait que l'assertion (`active_generation_count() == 1`, ou `got == ["annulé"]`)
tombe au mauvais instant. Sensible au timing, pas à la logique.

**Pistes :** remplacer les attentes par des `Event`/condition synchronisés plutôt que des `sleep`/
fenêtres implicites ; s'assurer que le registre est bien nettoyé/isolé entre tests (fixture de reset) ;
éventuellement marquer le test pour qu'il tourne sérialisé/isolé. **Ne pas** masquer en augmentant
aveuglément les timeouts.

**Priorité :** basse (n'affecte pas le produit ; gêne seulement la fiabilité de la suite en lot).

---

## TICKET-061 — i18n : placeholders/titres encore en dur dans les éditeurs du Studio

**⏳ OUVERT (2026-06-12, découvert pendant la suite du TICKET-057).** Le balayage des chaînes en dur
de `ui/` a corrigé la vue setup, le Studio (labels temp/top-p), la loading view et le dialogue
persona ; restent des chaînes anglaises en dur **dans les éditeurs internes du Studio** (zone déjà
en « dette assumée » côté doc) :

- `ui/widgets/story_setup_editor.py:53,57` — placeholders "Tag ID (e.g., race)" / "Question Text"
- `ui/widgets/scheduled_events_editor.py:63` — placeholder "Month 1, Month 2, ..."
- `ui/widgets/populate_tab.py:80` — placeholder d'exemple "e.g. 'Add a group of 3 rival merchants...'"
- `ui/widgets/map_editor.py:130` — titre de dialogue "Distance (km)"

À faire : clés i18n ×10 langues + branchement `tr()` (+ retranslate si l'éditeur reste vivant au
changement de langue). Les placeholders purement techniques (URLs, noms de modèles dans les
settings) sont volontairement exclus.

---

## TICKET-063 — Backend `openai` : modèles reasoning (gpt-5 / o-series) incompatibles

**Constat (2026-06-12, en livrant `feature-cloud-text-providers` ; ex-061 renuméroté au merge).**
Le backend `openai` passe par `UniversalClient`, dont le payload utilise `max_tokens` et
`temperature=0.7`. Les modèles « reasoning » d'OpenAI (famille gpt-5, o-series) **refusent ce
payload en 400** : ils exigent `max_completion_tokens` à la place de `max_tokens` et n'acceptent
que `temperature=1` (défaut). Le défaut livré (`gpt-4.1-mini`, paramètres classiques) fonctionne ;
c'est le choix manuel d'un modèle reasoning qui casse.

**Piste.** Détection du préfixe de modèle (`gpt-5`, `o1`/`o3`/`o4`) dans `UniversalClient` ou un
paramètre de construction supplémentaire dans `build_llm_from_config` (comme `max_stop_sequences`) :
basculer `max_tokens`→`max_completion_tokens` et omettre `temperature`/`top_p`.

**Priorité :** basse tant que le défaut documenté reste un modèle classique.

---

## TICKET-064 — Backend d'images Venice AI

**Idée (2026-06-12, sortie du malentendu initial de la session cloud-providers ; ex-062 renuméroté
au merge).** Venice AI expose une API d'images native `POST https://api.venice.ai/api/v1/image/generate`
(Bearer, JSON `{model, prompt, negative_prompt, width≤1280, height≤1280, steps, cfg_scale, format,
return_binary}` → `{"images": ["<base64>"]}`), qui mappe **exactement** les paramètres existants de
la config image (`image_width/height/steps/cfg_scale`). La clé `venice_api_key` existe déjà depuis
`feature-cloud-text-providers`. Ajouter un backend `venice` dans `axiom/image_generator.py` (même
patron que `_generate_gemini` : échec → None, TICKET-045) + entrée combo dans l'onglet Illustration
+ champ modèle (`image_venice_model`, ex. `venice-sd35`, steps max 30).

**Priorité :** moyenne (feature, rend l'illustration utilisable sans GPU local ni clé Google).

---

## TICKET-062 — 🚀 Préparation bêta publique (testeurs app + librairie)

**Décision utilisateur (2026-06-12).** Le projet est jugé assez mûr pour recruter des
bêta-testeurs (app GUI + lib `axiomai-engine`). Chantier de préparation, par sous-items :

1. **Univers par défaut embarqué** — fondé sur **Myria**, la fiction de l'utilisateur.
   **✅ Univers créé (2026-06-12)** : `universes/Myria/` (Universe-as-Code, 40 fichiers, EN),
   adapté du wiki fourni (`myrial_wiki.zip`) — lore book = savoir public seulement, secrets
   (dieux morts, Aléa, Arodan, traque Coalition) dans le global lore côté narrateur ; départ
   jouable à Highport (5 PNJ, carte 18 lieux, 3 questions de setup, 2 événements programmés).
   Compile + pack vérifiés ; `.gitignore` restructuré (`universes/*` + `!universes/Myria/`,
   cache exclu). Noms inventés pour les placeholders du wiki listés dans son README.
   **✅ Câblage premier lancement fait (2026-06-12)** : `core/bundled_universes.py` branché
   dans `main.py` — une offre par univers à vie (`installed_bundles.txt`), jamais
   d'écrasement, cache recompilé par la découverte Hub ; détail dans
   `maintenance/TICKET-062-univers-par-defaut/`.
   **✅ VALIDÉ GUI (2026-06-13).** Reste optionnel : relecture canon fine ; version FR.
2. **Clés Fireworks.ai embarquées dans le repo** — **✅ FAIT (2026-06-12)** : 4 clés fournies
   par l'utilisateur (AXIOMAI-0/1 à 6 $, AXIOMAI-2/3 à 1 $, **expirent le 2026-06-30**),
   embarquées obfusquées (inversion + base64) dans `core/builtin_keys.py`, utilisées seulement
   sans clé utilisateur, **rotation automatique** sur 401/402/403/429
   (`UniversalClient.fallback_api_keys` + registre `axiom.config.register_builtin_keys` — le
   moteur PyPI ne contient aucune clé). 1ᵉʳ lancement sans config → backend `fireworks`,
   modèles plafonnés « pas chers » (≤ 0,30 $ in / ≤ 1,00 $ out par M tokens), bouton
   « Parcourir… » les modèles avec prix dans Réglages → Cloud. Défaut `deepseek-v3p1` mort →
   `gpt-oss-120b`. **Rotation re-vérifiée en réel (2026-06-12, complétion + streaming)** :
   clé morte en tête → bascule sur clé valide → réponse OK. **Kill-switch ajouté** :
   `core/builtin_keys.py::BUILTIN_KEYS_ENABLED = True` → à `False`, l'offre « clés gratuites »
   est retirée d'un geste (register/défaut bêta = no-ops, pool vide, message « add your key »)
   **sans rien supprimer** (clés/prix/rotation conservés). Détail :
   `maintenance/TICKET-062-clefs-fireworks/`.
   **✅ VALIDÉ GUI (2026-06-13).** ⏰ Reste : après le 2026-06-30, flipper
   `BUILTIN_KEYS_ENABLED=False` (ou renouveler le pool).
3. **Vérifier le support Windows** — **✅ AUDIT CODE FAIT (2026-06-13)**, détail dans
   `maintenance/TICKET-062-windows-support/`. Verdict : moteur/workers déjà Windows-safe
   (pathlib, fermeture sqlite avant replace/unlink, sanitisation des noms de fichiers, hardcore
   conçu pour Windows). **Bugs corrigés** : `run.bat` (plancher Python 3.10→3.11), `#`→`REM` +
   emoji dans `run.bat`/`test.bat`, garde-fou UTF-8 stdout dans `tools/diagnostic.py`.
   **Reste (test machine Windows requis, pas corrigeable à l'aveugle)** : audio `.ogg` (Media
   Foundation ne décode pas Vorbis), install torch/chromadb/PySide6, images locales, run.bat
   de bout en bout.
4. **Outil de diagnostic accessible aux utilisateurs** — **✅ CLI + GUI FAITS (2026-06-12/13)** :
   `tools/diagnostic.py` autonome (`python -m tools.diagnostic`) → rapport copiable ✅/⚠️/❌
   (env, versions libs, embedding caché, config, dossiers, **connectivité backend**), drapeaux
   `--tests` (pytest en 2 lots, contourne segfault TICKET-067), `--offline`, `--json`,
   `--output`, code de sortie = sévérité ; reflète le runtime réel (clés bêta enregistrées).
   Brique GUI : Aide → Diagnostic (`ui/diagnostic_dialog.py` + `workers/diagnostic_worker.py`,
   boutons Actualiser/Tests/Copier/Enregistrer, i18n ×10). Détail :
   `maintenance/TICKET-062-outil-diagnostic/`. **✅ VALIDÉ GUI (2026-06-13).**
5. **Assets de com'** : nouvelles captures d'écran (celles du README datent d'avant la doc
   intégrée/les nouveaux onglets) + **un GIF** de ~30 s d'un tour de jeu pour le README et
   les annonces.

**Canaux de recrutement identifiés** (discussion 2026-06-12) : communauté SillyTavern (l'app
importe leurs cartes — feature à mettre en avant dans le README), r/LocalLLaMA, LinuxFr.org,
itch.io (app), Show HN + r/Python (lib). Prérequis conseillés avant annonce : TICKET-050
(fail-fast 429) **✅ fait** et une CI GitHub Actions **✅ faite** (`.github/workflows/tests.yml`,
2 lots, matrice 3.11/3.12 — reste à confirmer verte au 1ᵉʳ push).

**Priorité :** haute (bloque le recrutement de testeurs). Items 1-2 = cœur de l'onboarding.
**État au 2026-06-13 :** items 1, 2, 4 **validés GUI** ; item 3 (Windows) **audit code fait +
bugs scripts corrigés** (reste un test sur vraie machine Windows) ; **reste à produire : item 5
(screens/GIF)** — et le test Windows réel quand une machine sera dispo.

## TICKET-065 — `world_tension_level` : clé en deux casses, curseur Studio sans effet

**Découvert le 2026-06-12** en corrigeant le crash du Studio sur l'univers Myria
(`maintenance/TICKET-062-univers-par-defaut/`).

La même méta existe sous deux clés selon le chemin d'écriture :
- `axiom/db_helpers.py:115` (création wizard) seed **`World_Tension_Level`** = "0.3" ;
- `axiom/chronicler.py:290` (`_fetch_world_tension`) lit **`World_Tension_Level`** ;
- `ui/creator_studio_view.py` (charge/sauve) et `axiom/compile.py` (univers-dossier)
  utilisent **`world_tension_level`** (minuscules).

Conséquences : pour un univers wizard, le Chronicler lit à vie le 0.3 seedé (le Studio
écrit l'autre clé) ; pour un univers-dossier, la clé majuscule n'existe pas → défaut 0.3.
**Le curseur « World Tension » du Studio n'influence donc jamais le Chronicler.**

Piste : normaliser sur une seule clé (minuscules, cohérente avec compile/decompile) +
migration de lecture tolérante (lire les deux, écrire la canonique) dans le Chronicler
et `db_helpers`. Vérifier au passage s'il existe d'autres méta à double casse.

## TICKET-067 — Suite de tests : segfault Qt multimédia + torch/triton

**Découvert le 2026-06-12** en validant TICKET-066 (la grande suite plantait).

`pytest tests/` segfault systématiquement au début de `test_arbitrator.py` :
`Fatal Python error: Segmentation fault` pendant l'import de `triton` (chargé par
`torch._dynamo`, lui-même tiré par un import du chemin arbitrator/TTS). Reproduction
minimale : `pytest tests/test_ambiance_manager.py tests/test_arbitrator.py` —
l'ordre compte, c'est le chargement préalable de PySide6 QtMultimedia qui rend
l'import natif de triton fatal. Chaque fichier passe **seul** ; la suite passe en
deux moitiés (`--ignore=tests/test_ambiance_manager.py` → 710 verts, puis
`test_ambiance_manager.py` seul → 5 verts).

Indépendant du code applicatif (crash dans le module natif triton, venv Python
3.14.5/Fedora). Pistes : épingler/mettre à jour triton, le désinstaller s'il ne sert
pas (dépendance transitive de torch), ou forcer l'ordre/l'isolation des tests
(pytest-forked, marqueur). À recouper avec TICKET-059 (fiabilité de la suite).

**Priorité :** moyenne — bloque la validation « grande suite » en un seul passage.

## TICKET-069 — Validation Windows sur machine réelle (reste de l'audit item 3)

**Ouvert le 2026-06-13.** Suite de l'audit statique TICKET-062 item 3
(`maintenance/TICKET-062-windows-support/`) : le code est jugé Windows-safe et les bugs de
scripts sont corrigés, mais **rien n'a été lancé sur Windows**. Ce ticket regroupe ce qui ne
peut être levé que sur une vraie machine/VM Windows. À dérouler dans l'ordre :

1. **Install des dépendances** (risque n°1). `pip install -r requirements.txt` via `run.bat`.
   ⚠ **Tester avec Python 3.11, 3.12 ou 3.13** — PAS 3.14 : `onnxruntime`/`torch`/`PySide6`
   n'ont pas toujours de wheel `cp314` Windows → l'install tenterait une compilation source et
   échouerait. **Décision à prendre** : recommander 3.11–3.13 dans le README + message `run.bat`
   (voire borne haute), et/ou borner légèrement les versions de deps (non borné = `>=` partout).
2. **Lancement de bout en bout** : `run.bat` (venv, deps, `startup_check.py`, GUI s'ouvre).
3. **1ᵉʳ téléchargement du modèle d'embedding** sur cache vierge (`all-MiniLM-L6-v2`) — le fix
   TICKET-068 (`local_files_only=True`) suppose le modèle déjà caché ; le tout 1ᵉʳ download
   (réseau + cache HF sous `%USERPROFILE%`) n'a jamais été exercé sous Windows.
4. **Audio** : `QtMultimedia` s'importe ? (éditions Windows « N » sans Media Feature Pack =
   échec possible) ; ambiances `.mp3`/`.wav` jouent ; **`.ogg` attendu muet** (Media Foundation
   ne décode pas Vorbis) → si confirmé, privilégier mp3/wav pour les assets ou documenter.
5. **Génération d'images** locale (SD WebUI/ComfyUI sur `localhost`) + backend Gemini.
6. **Un tour de jeu complet** + le Creator Studio + Aide → Diagnostic (le rapport doit être
   parlant ; vérifier qu'il signale correctement l'environnement Windows).

**Priorité :** haute (bloque l'annonce bêta côté Windows). **Prérequis : accès à un Windows**
(VM, ou testeur de confiance). Le diagnostic GUI/CLI (`tools/diagnostic.py`) est l'outil à faire
tourner en premier par un testeur pour remonter un rapport.

---

## TICKET-083 — Croyances : fuite temporelle au rewind (`created_turn_id`)

**Découvert le 2026-06-19** (2ᵉ passe QA du chantier Hindsight).

`axiom/observations.py::apply_consolidation` (branche CREATE) stampe
`created_turn_id = min(tours des sources)`, **pas le tour T où la consolidation a tourné**. Or le
rollback (`rollback_observations`) supprime sur `created_turn_id > target`. Donc une croyance
consolidée au tour T à partir de faits plus anciens **survit à un rembobinage à un tour situé entre
sa plus vieille source et T**, alors que la passe de consolidation n'avait pas encore eu lieu à ce
moment-là → fuite de « connaissance future » vers le passé, bornée à ~l'intervalle de consolidation
(`memory_fact_interval`).

**Piste.** Soit stamper `created_turn_id = turn_id` (le tour de consolidation) — la croyance
disparaît alors proprement si on rembobine avant sa formation ; soit assumer le comportement actuel et
le documenter. Vérifier l'effet sur les sources : les `sources` restent turn-keyed et sont déjà
filtrées correctement au rewind, donc seul le critère de suppression de la croyance entière est en jeu.

**Priorité :** basse-moyenne — incohérence de rewind dans un cas de bord (croyance bâtie sur faits
anciens + rembobinage). Aucun impact hors mode « living » + croyances.

---

## TICKET-084 — Budget de prompt `living` = jusqu'à 3× `rag_chunk_count`

**Découvert le 2026-06-19** (2ᵉ passe QA Hindsight).

`axiom/arbitrator.py` (~l.367-386, mode living) injecte **trois** blocs dimensionnés chacun par
`cfg.rag_chunk_count` : croyances (si activées) + faits + chunks narratifs. L'utilisateur qui règle
`rag_chunk_count` s'attend probablement à un **total**, pas à un triplement du contexte (coût tokens
×3 dans le pire cas, mode « living » + croyances).

**Piste.** Soit un budget partagé (répartir `rag_chunk_count` entre les trois sources), soit des
sous-quotas explicites/configurables (ex. `memory_belief_count`, `memory_fact_count`), soit documenter
clairement que le total grimpe en living. À arbitrer avec la qualité de rappel (les trois niveaux sont
complémentaires : croyances synthétiques → faits atomiques → prose brute).

**Priorité :** basse — coût/clarté, pas un bug. Pertinent seulement en mode « living ».

---

## TICKET-085 — Cache BM25 : `collection.get()` plein corpus encore exécuté au cache-hit

**Découvert le 2026-06-19** (2ᵉ passe QA Hindsight).

`axiom/memory.py::query` : même quand l'index BM25 est réutilisé (cache-hit TICKET-078), le
`self._collection.get(where=where_cond, include=["documents","metadatas"])` recharge **tout** le corpus
filtré à chaque requête (nécessaire aujourd'hui pour calculer l'empreinte d'ids ET pour le backfill des
hits lexicaux-seuls). Seul le coût dominant (tokenisation + IDF dans `build_bm25`) est caché ; la
lecture Chroma plein-corpus, elle, reste par requête.

**Piste (si jamais ça devient chaud).** Mettre aussi `corpus_docs`/`corpus_metas` en cache à côté de
l'index (clé identique), invalidés par la même empreinte — au prix d'un peu de RAM. Gain réel surtout
sur le corpus lore figé ; négligeable sur petits volumes. À ne faire que si un profilage le justifie.

**Priorité :** très basse — micro-optimisation. Le fix TICKET-078 (le vrai poste de coût) tient.

---

## TICKET-088 — `fork_save` ne copie pas la mémoire living ni les snapshots

**Découvert le 2026-06-21** (QA fs, même classe que TICKET-086). `axiom/saves.py::fork_save` copie
Saves/Event_Log/Active_Modifiers/Fired_Scheduled_Events/Items_Inventory/Timeline, et reconstruit le
State_Cache. Il **ne copie pas** : `Facts`, `Observations`, `Mental_Models` (mémoire mode living),
ni `Snapshots`/`Modifier_Snapshots` (snapshots de rewind). Forker une save **embarquée** (via
`duplicate_save` legacy) perd donc les faits/croyances/modèles mentaux accumulés et empêche un rewind
correct dans la copie.

**Portée.** `fork_save` ne sert qu'aux saves embarquées legacy (les saves séparées sont copiées
fichier→fichier et gardent tout). Impact réel : legacy + living + duplication.

**Piste.** Étendre `fork_save` aux tables manquantes (en gérant leur création paresseuse : `Facts`/
`Observations`/`Mental_Models` peuvent être absentes d'une vieille base), ou documenter la limite.

**MAJ 2026-09-22 (TICKET-095).** Le fork prend désormais l'inventaire **au tour du fork** (via
`Inventory_Snapshots`) et copie ces snapshots, avec remappage cohérent des `instance_id` (le contenu
des sacs pointait avant vers des ids de la save source). Restent non copiés : Facts/Observations/
Mental_Models, `Snapshots`, `Modifier_Snapshots`.

**Priorité :** basse-moyenne.

---

## TICKET-089 — `package._RUNTIME_TABLES` omet les tables living

**Découvert le 2026-06-21** (QA fs). `axiom/package.py::_runtime_free_cache_copy` purge les tables
runtime du cache embarqué dans un `.axiom` (« définition seule ») via `_RUNTIME_TABLES`. Cette liste
n'inclut **pas** `Facts`/`Observations`/`Mental_Models`. Si une save embarquée legacy a joué en mode
living, sa mémoire (potentiellement du contenu de partie) pourrait voyager dans une archive censée ne
porter que la définition.

**Piste.** Ajouter les trois tables à `_RUNTIME_TABLES` (purge conditionnelle : déjà gardée par
`SELECT 1 FROM sqlite_master`).

**Priorité :** basse — fuite de données de partie dans un export de définition (cas legacy + living).

**Extension (2026-09-26, arbitrage mods, rang 23).** La liste oublie aussi **`Item_Instances`** et
**`Session_Lore`** (`axiom/package.py:94-105`). La purge tourne sous `PRAGMA foreign_keys=OFF`
(`package.py:123`) : pas de cascade depuis `Saves`, ces lignes restent dans l'archive. À traiter avec
088 ; la vraie correction est le registre unique des données de save (`Mods/DOC.md` §13 phase 0c).

---

## TICKET-090 — `paths` : `UNIVERSES_DIR` figé, pas de `get_universes_dir()`

**Découvert le 2026-06-21** (QA fs). `axiom/paths.py` expose des getters override-aware pour les
saves/vector/assets (`get_saves_dir`/`get_vector_dir`/`get_assets_dir`, sensibles à `AXIOM_DATA_DIR`
et `configure(data_dir=)`), mais **pas pour les univers** : seul le constant `UNIVERSES_DIR` existe,
gelé à l'import sur `~/AxiomAI/universes`. Conséquence : un embarqueur/test qui isole via
`AXIOM_DATA_DIR` déplace saves+vector mais **pas** la bibliothèque d'univers (asymétrie). La fixture
de test `isolated_axiom_data_dir` n'isole d'ailleurs pas les univers — les tests qui écrivent dans la
bibliothèque doivent passer un `library_dir` explicite (ce qu'ils font aujourd'hui).

**Piste.** Ajouter `get_universes_dir()` (= `_data_root()/universes`) et l'utiliser dans
`compile_cmd`/`play`/`bundled_universes`/`hub_view` ; garder `UNIVERSES_DIR` en alias de compat.
Décider si les univers DOIVENT suivre `data_dir` (cohérence) ou rester volontairement machine-globaux.

**Priorité :** basse — cohérence/archi, pas de bug pour l'app (qui n'override jamais `data_dir`).

---

## TICKET-099 — Clés intégrées expirées toujours proposées

**Découvert le 2026-09-22** (mise à jour du site). `core/builtin_keys.py::BUILTIN_KEYS_ENABLED` vaut
encore `True`, alors que le pool Fireworks prépayé a expiré le 2026-06-30 (TICKET-062 item 2). Au premier
lancement, `apply_beta_defaults()` configure donc le backend `fireworks` sur des clés mortes : le premier
tour d'un nouvel utilisateur échoue au lieu d'afficher « ajoute ta clé dans les Réglages ».
La bannière du site qui annonçait ces clés a été retirée le 2026-09-22.

**Options.** (a) passer `BUILTIN_KEYS_ENABLED = False` (le commentaire du module prévoit exactement ce
cas : rien n'est supprimé, réactivable) ; (b) renouveler/recharger le pool.
**Priorité :** haute pour l'expérience d'un nouvel utilisateur — une ligne à changer une fois décidé.

---

> Tickets 100→105 : bugs trouvés par la critique du système de mods (`maintenance/Mods/CRITIQUE.md`)
> et **confirmés** par l'arbitrage (`maintenance/Mods/ARBITRAGE.md`, rangs 3/6/16/21/22/24).
> Décision utilisateur D-1 (2026-09-26) : corriger **tout de suite**, en tickets normaux, hors chantier mods.

## TICKET-100 — Rewind web/CLI : ChromaDB jamais rembobinée, doublons au rejeu

**Découvert le 2026-09-23** (critique mods §3.4, confirmé arbitrage rang 3). `Session.rewind`
(`axiom/session.py:408-437`) n'appelle jamais `VectorMemory.rollback` (`axiom/memory.py:482-501`) ;
le docstring de `CheckpointManager.rewind` laisse ça « au caller » (`checkpoint.py:62-63`) et aucun
caller web/CLI ne le fait (`main_web.py:1815`, `main_web.py:1930` — édition de message —,
`axiom/cli/play.py:185`). Seul le chemin Qt le fait (`ui/tabletop_view.py:1012-1023`, avec backup
auto via `workers/db_tasks.py:151-178`).
**Aggravant :** `embed_chunk` identifie chaque chunk par un `uuid4` (`axiom/memory.py:238`) → rejouer
un tour **ajoute** un second chunk au lieu de remplacer ; le RAG voit le futur annulé **et** le nouveau.

**Piste.** `Session.rewind` appelle `VectorMemory.rollback` (et idéalement le backup auto) → le chemin
Qt n'a plus à le faire lui-même (un seul rewind). Ids de chunks déterministes (ex. `save:turn:idx`)
pour que le rejeu écrase. Préfigure le point d'entrée unique de `Mods/DOC.md` §13 phase 0c.
**Priorité :** haute — touche tous les joueurs web/CLI aujourd'hui.

---

## TICKET-101 — Tour échoué ou annulé : `user_input` orphelin + `turn_id` décalé

**Découvert le 2026-09-23** (critique §3.2), **reproduit en exécution** par l'arbitrage (rang 6) avec un
faux LLM levant `LLMConnectionError` : après l'échec, `turn_id == 1`, l'`Event_Log` contient
`(1, 'user_input')` sans narration, `_load_history()` renvoie le message joueur seul.
**Cause :** `self._turn_id += 1` **avant** `process_turn` (`axiom/session.py:209`) ; l'intent est
commité avant l'appel LLM (`axiom/arbitrator.py:230-236`) ; l'intent pool est vidé (`session.py:212-213`).
Même chemin pour `GenerationCancelled` (bouton stop). Au tour suivant, deux messages joueur d'affilée
partent au LLM. Touche Qt, web et CLI (tous passent par `Session`).

**Piste.** En cas d'échec/annulation : restaurer `_turn_id`, supprimer les events du tour avorté (ou
ne les commiter qu'après le LLM, via le tampon `_pending_events` déjà présent), remettre l'intent dans
le pool. Préfigure le tour transactionnel (`Mods/DOC.md` phase 0d).
**Priorité :** haute.

---

## TICKET-102 — Job mémoire living web sans verrou (course avec le rewind)

**Découvert le 2026-09-23** (critique §3.9, arbitrage rang 16 : **probable**, non reproduit — course).
Le job living web est un `threading.Thread` daemon (`main_web.py:2751`) qui lit `turn`, appelle le LLM
(plusieurs secondes) puis écrit Facts/Observations **sans `ACTIVE_SESSION_LOCK`**
(`main_web.py:2685-2745`). Un rewind pendant ce délai laisse des faits pour des tours annulés, puis des
doublons au rejeu. (Sans rapport avec TICKET-083, contrairement à ce que disait la critique.)

**Piste.** « Époque » de session : le job capture un compteur incrémenté à chaque rewind/fork/
chargement et **refuse d'écrire** s'il a changé (`Mods/DOC.md` §10.4). Vérifier aussi le chemin Qt
(`workers/fact_worker.py`).
**Priorité :** moyenne.

---

## TICKET-103 — `fork_save --turn` copie des données postérieures au point de fork

**Découvert le 2026-09-23** (critique §3.6, confirmé arbitrage rang 21). `axiom/saves.py:947-957`
copie tous les `Fired_Scheduled_Events` sans filtrer `fired_turn_id <= turn_id` (la colonne existe
pour ça, TICKET-075 ; le rewind filtre bien, `checkpoint.py:148-151`). Même défaut pour
`Session_Lore` (copie sans filtre sur `origin_turn`, `saves.py:920-930`). Accessible via
`axiom saves fork --turn N` (`axiom/cli/saves_cmd.py:234`) ; `duplicate_save` forke sans point, pas
d'effet. (Les modifiers copiés « as-is » sont un choix documenté, `saves.py:856`, rattaché à 088.)

**Piste.** Ajouter les deux filtres. **Priorité :** basse.

---

## TICKET-104 — `regenerate.py` : remplacement de consigne sans effet

**Découvert le 2026-09-23** (critique §3.11), **reproduit** par l'arbitrage (rang 22) :
`build_narrative_prompt` ne contient pas la chaîne `"You MUST end your response with a JSON block"`
(la consigne réelle est le bloc `~~~json`, `axiom/prompts.py:57`) → le `.replace` de
`axiom/regenerate.py:73-79` ne fait rien. Le texte régénéré, **JSON compris**, est stocké tel quel
(`regenerate.py:103`) ; masqué à l'affichage (Qt `ui/widgets/chat_display.py:84`, web
`web/app.js:1516`) mais **renvoyé au LLM** dans l'historique (`regenerate.py:36`, `Session._load_history`).
Note : la régénération se fait aussi sans stats, RAG ni lore (`regenerate.py:60-70`).

**Piste.** Cibler la vraie consigne (ou construire le prompt sans le bloc JSON) et retirer tout bloc
JSON du texte avant `append_variant`. **Priorité :** basse-moyenne.

---

## TICKET-105 — `_pending_correction` non remise à zéro au rewind

**Découvert le 2026-09-23** (critique §3.3, confirmé arbitrage rang 24). L'indice « l'action a échoué »
vit sur `self._pending_correction` (`axiom/arbitrator.py:152,450,465,1731-1734`). Au rewind,
`Session.rewind` appelle `invalidate_stats_cache` (`session.py:415`), qui ne le touche pas
(`arbitrator.py:166-176`) → un indice issu d'un tour annulé peut être injecté une fois.

**Piste.** Remettre à `None` au rewind (et au chargement de save). **Priorité :** basse.

---

## TICKET-106 — Audit et alignement de l'encapsulation / détachement total du noyau sur l'ensemble des autres mods officiels

**Besoin identifié le 2026-09-30** (clarification utilisateur lors du chantier `feature-help-system-mod`) :
Un mod officiel ne doit pas seulement masquer des éléments d'interface via un toggle ou des conditions `if is_mod_enabled(...)` dans le code du noyau.
Le mod doit **contenir** l'intégralité de son code fonctionnel, et sa désactivation doit signifier le **détachement total** du code du noyau (zero overhead, aucun listener ou hook résiduel sur l'application hôte).

**Historique et rectification (2026-10-03) :**
- Marqué « RÉSOLU » le 2026-09-30 à tort : le code avait en fait été rapatrié dans `axiom/` avec de faux shims `importlib`, et le noyau continuait d'exécuter l'inventaire, les modificateurs et le temps en dur.
- **RÉELLEMENT RÉSOLU (Phase 2 vrai déplacement — octobre 2026) :**
  - Code fonctionnel extrait intégralement dans `mods/` (`axiom.illustrations`, `axiom.time`, `core.stat_dynamics`, `axiom.inventory`, `axiom.living_memory`).
  - Zéro import de mod dans le noyau (`axiom/`) : `tests/test_engine_headless.py` vérifié avec 0 violation `check_headless`.
  - Politiques `[storage]` `custom` : gestionnaires `rewind` / `fork` / `snapshot` exécutés depuis `storage.py` pour tout mod installé, même décoché, garantissant l'intégrité des sauvegardes.
  - Décoché = zéro hook, zéro slot, zéro prompt exécuté au tour.
  - `axiom.providers` seule source d'IA (safe mode inclus, message clair sans fallback noyau).
  - Suivi : `maintenance/Mods/phase-2-vrai-deplacement/`.

---

## TICKET-107 — 11 clés de traduction manquantes dans les réglages et éditeurs Qt

**Découvert lors de l'audit réel du 2026-10-03** :
Onze clés appelées par `tr("...")` dans l'interface Qt ne figurent pas dans `core/locales/en.toml` (et sont donc absentes dans l'ensemble des 10 langues gérées). Elles s'affichent brutes ou causent des avertissements.

**Clés identifiées (11, vérifiées dans le code le 2026-10-03) :**
- `mods/axiom.ui.qt/ui/settings_dialog.py` (liste des modèles) — **affichées brutes** : `select_model`,
  `filter_models_placeholder`, `model_list_error`, `unknown_error`.
- Avec un texte de repli en dur dans le code (jamais traduites, avertissement au log) :
  `apply_preset_tooltip` (`widgets/stat_definition_editor.py`), `select_stats` (`widgets/entity_editor.py`),
  `dice_box_title` (`widgets/dice_box.py`), `importing_st` / `importing_universe` (`hub_view.py`),
  `question` (`widgets/story_setup_editor.py`), `quantity` (`mods/axiom.inventory/ui/inventory_view.py`).
- Plusieurs manquaient déjà sur `main` (hors chantier mods).

**Action requise :**
Ajouter ces 11 clés avec leurs textes de référence dans `core/locales/en.toml`, puis propager dans les 9 autres langues (`fr.toml`, `de.toml`, `es.toml`, etc.).
**Priorité :** moyenne (qualité visuelle et i18n de l'application Qt).

---

## TICKET-108 — Robustesse des petits modèles (Gemma 4B / KoboldCPP) : message utilisateur ignoré & règle universelle d'asymétrie d'information

**Constat et contexte (remontée utilisateur 2026-10-04) :**
Sur des modèles compacts (ex: `Gemma-4-E4B-Uncensored-HauhauCS-Aggressive-Q5_K_P.gguf` exécuté sous KoboldCPP) avec des univers riches en lore et complexité narrative :
1. **Dernier message du joueur souvent ignoré ou écrasé :**
   - Dans `axiom/prompts.py:807-834`, un message `role: "system"` (`final_instr` : rappels de verbosité, consignes de focalisation) est injecté *après* le message `role: "user"`.
   - Les chat-templates des petits LLMs et des backends comme KoboldCPP gèrent mal les rôles système placés après l'utilisateur. Le modèle subit un effet de récence disproportionné (l'attention se concentre sur les derniers tokens de consignes de sortie et « écrase » l'action du joueur juste avant).
   - De plus, en mode solo, l'enveloppe technique `[SIMULTANEOUS ACTIONS FOR THIS TICK]\n[player] INTENT: ...` dilue l'action dans du métalangage inutile.
2. **Fuite des secrets, mystères et identités cachées (omniscience naïve des petits modèles) :**
   - Lorsqu'une information confidentielle (ex: identité secrète d'un PNJ, complot, vérité cachée) est inscrite dans le `global_lore` ou le `lore_book`, les petits modèles (qui ont une Théorie de l'Esprit limitée) considèrent naïvement que tous les personnages de la scène la connaissent et la divulguent spontanément.
   - Les règles actuelles (`axiom/prompts.py:712-726`) n'imposent aucune barrière épistémique sur les connaissances des PNJ.

**Objectif & Approche architecturale (Directives claires) :**
- **Refus des rustines spécifiques au cas par cas :** Ne PAS alourdir le prompt système avec des règles séparées pour les « identités secrètes », puis pour les « mystères », puis pour les « complots » (ce qui saturerait la fenêtre d'attention des modèles 4B et augmenterait le coût en tokens).
- **Règle universelle et concise :** Formuler **une seule phrase ou directive forte** dans les `NARRATOR RULES` (ou le cadre de narration) couvrant l'asymétrie d'information de manière générale et universelle.
  - *Exemple de principe :* Les PNJ n'agissent et ne s'expriment qu'en fonction de ce qu'ils ont personnellement perçu ou appris directement en jeu ; toute information de fond (secrets, identités cachées, mystères, mobiles dissimulés) reste strictement inconnue d'eux tant qu'elle n'est pas expressément découverte ou révélée dans la scène.
- **Assainissement de la fin de prompt :**
  - Fusionner les rappels finaux de verbosité soit dans le message système initial, soit à la fin du message utilisateur, évitant ainsi le rôle `system` traînant après le `user`.
  - Alléger le gabarit `[SIMULTANEOUS ACTIONS FOR THIS TICK]` en mode solo.

**Priorité :** moyenne (qualité d'expérience majeure pour les modèles légers locaux).

---

## TICKET-109 — Export d'univers `.axiom` sans modpack recommandé/requis (`axiom/package.py`)

**Constat (audit d'octobre 2026) :**
Alors que les sauvegardes (`.axiomsave`) incluent désormais un manifeste d'intégrité `modpack.json` avec les hash SHA-256 et avertissent à l'ouverture en cas de divergence, l'export/import d'univers `.axiom` (`axiom/package.py`) ne sérialise aucun modpack recommandé ou requis dans l'archive.
Un univers conçu pour fonctionner avec des mods de mécanique (ex: `axiom.inventory`, `community.survival`, ou des mods tiers) peut être importé et joué sur une instance où ces mods sont absents ou désactivés, sans avertissement.

**Piste :**
Inclure un fichier optionnel ou une section `[modpack]` dans `universe.toml` / l'archive `.axiom`, et vérifier lors de la sélection ou de la création de partie la présence des mods requis.
**Priorité :** basse-moyenne.

---

## TICKET-110 — `axiom.minimal_chat` : violation d'encapsulation via accès à `mod_ctx._registry`

**Constat (audit d'octobre 2026) :**
Dans `mods/axiom.minimal_chat/main.py:23`, la résolution du LLM backend effectuait :
```python
registry = getattr(mod_ctx, "registry", None) or getattr(mod_ctx, "_registry", None)
```
`ModContext` ne possède pas d'attribut public `registry`, et l'accès à son attribut privé `_registry` violait la règle d'encapsulation et le principe selon lequel les mods officiels doivent consommer la même API publique que les mods tiers (Règle D2).

**Résolution (2026-10-04) :**
`resolve_llm_backend(registry=mod_ctx)` est désormais appelé directement. `ModContext` implémente publiquement `get_slot` et `get_service`, ce qui satisfait l'interface attendue sans aucun accès à l'attribut privé. Validé par `tests/test_minimal_chat_mod.py`.
**Statut :** ✅ résolu.

---

## TICKET-111 — Noyau neutre (K12) : résidus JDR et imports LLM dans `axiom/kernel/`

**Constat (audit d'octobre 2026) :**
Malgré la réussite du déplacement de Phase 2 (zéro import `mods.` dans `axiom/`), le noyau (`axiom/kernel/`) n'est pas encore 100% neutre :
1. `axiom/kernel/registry.py:23` importe `GenerationCancelled` depuis `axiom.backends.base` (un concept propre aux LLM) pour le propager hors des hooks.
2. `axiom/kernel/context.py:15` importe `AppConfig` depuis `axiom.config` (qui porte des clés d'API LLM et réglages JDR).
3. `axiom/kernel/step_context.py:18` (`KernelStepContext`) possède des champs hardcodés spécifiques au JDR narratif (`llm`, `time_llm`, `vector_memory`, `hero_entity_id`, `intents`).
4. `axiom/kernel/llm_creator.py` est toujours situé dans `axiom/kernel/` au lieu d'un mod dédié (`axiom.creator_studio` ou `axiom.mod_creator`).

**Piste :**
- Définir une exception générique de cancellation dans le noyau (ex: `StepCancelled`) et la faire hériter ou mapper.
- Passer un dictionnaire ou une interface de configuration abstraite au `ModContext`.
- Rendre `KernelStepContext` purement agnostique (stocker les données métier dans `payload` ou `extras`).
- Déplacer `llm_creator.py` dans un mod (TICKET-C4).
**Priorité :** moyenne (achèvement de la vision du noyau neutre K12).

---

## TICKET-112 — Harnais Golden : `_canonical_tables` omet les tables déclarées par les mods si appelé isolément (`golden_harness.py:422`)

**Constat (audit d'octobre 2026) :**
Dans `axiom/testing/golden_harness.py:422`, la liste des tables à canonicaliser filtrait `CORE_STORAGE_REGISTRY` directement. Si `canonicalize_save` ou `compare_saves` était exécuté dans un processus de test sans qu'une fonction comme `get_runtime_tables()` ou un bootstrap de modpack n'ait été appelé au préalable, `_ensure_mod_storage()` n'avait pas tourné et les tables déclarées par les mods (`Facts`, `Observations`, `Item_Instances`, etc.) étaient omises.

**Résolution (2026-10-04) :**
Ajout d'un appel explicite à `_ensure_mod_storage()` au début de `_canonical_tables` dans `golden_harness.py`. Validé par `tests/test_golden_step.py`.
**Statut :** ✅ résolu.

---

## TICKET-113 — Manifeste de mod : section déclarative `[schema]` du `mod.toml` ignorée au parsing (`manifest.py`)

**Constat (audit d'octobre 2026) :**
Bien que les migrations de base de données dynamiques fonctionnent via `ctx.register_migrations(...)` et soient appliquées à la création/ouverture de save, le parseur de manifeste `axiom/kernel/manifest.py` ne lit ni ne valide la table déclarative `[schema]` éventuellement spécifiée dans `mod.toml` (contrairement à `[storage]`).

**Piste :**
Ajouter `_parse_schema_section(data.get("schema", {}))` dans `axiom/kernel/manifest.py` et mapper les migrations de versions déclaratives vers le gestionnaire de migrations.
**Priorité :** basse.

---

## TICKET-114 — Harnais Golden : omission des tables de stockage `custom` (`Observations`, `Mental_Models`, `Item_Instances`, `Active_Modifiers`)

**Constat (audit d'octobre 2026) :**
Dans `axiom/testing/golden_harness.py:428-430`, `_canonical_tables` filtre :
```python
specs = [
    s for s in CORE_STORAGE_REGISTRY
    if s.is_runtime and s.save_scoped and not s.external and s.columns
    and s.table_name != "Event_Log"
]
```
Or, toutes les tables enregistrées via `declare_mod_storage` sous la politique `StoragePolicy.CUSTOM` (`Observations`, `Mental_Models` pour `axiom.living_memory` ; `Item_Instances`, `Items_Inventory` pour `axiom.inventory` ; `Active_Modifiers` pour `core.stat_dynamics`) n'ont pas de champ `columns` défini (`columns is None`).
Par conséquent, `s.columns` est falsy et ces tables sont **systématiquement et totalement omises** de la canonicalisation du Golden Harness. Le test golden step ne vérifie donc ni les croyances et modèles mentaux de la mémoire vivante, ni les objets de l'inventaire, ni les modificateurs de statistiques, contredisant l'affirmation de « vérification complète » dans `TODO.md` (0a).

**Piste :**
Pour les tables `custom` ayant une table SQL associée (`save_scoped and not external`), inspecter dynamiquement les colonnes de la table via `PRAGMA table_info` ou définir `columns` dans la déclaration de stockage, afin que le Golden Harness compare réellement l'intégralité de l'état runtime.
**Résolution (2026-10-14) :**
Dans `axiom/testing/golden_harness.py:428-445`, la condition de filtrage a été allégée pour inclure toutes les tables `is_runtime and save_scoped and not external`. Pour les tables sans `spec.columns` explicite, les colonnes disponibles de la table sont lues dynamiquement via `PRAGMA table_info`. Toutes les tables (`Observations`, `Mental_Models`, `Item_Instances`, `Items_Inventory`, `Active_Modifiers`) sont désormais canonicalisées et comparées. Validé par `tests/test_golden_step.py`.
**Statut :** ✅ résolu.

---

## TICKET-115 — `Mod_KV` : crash `UNIQUE constraint failed` sur réinsertion après delete + écritures anti-chronologiques permises

**Constat (audit d'octobre 2026) :**
Dans `axiom/kernel/kv_store.py:46-85`, `_kv_write` recherche la ligne active avec :
```python
active = conn.execute(
    "SELECT from_step FROM Mod_KV "
    "WHERE save_id = ? AND mod_id = ? AND key = ? AND to_step IS NULL;",
    (save_id, mod_id, key),
).fetchone()
```
1. **Crash `UNIQUE constraint failed` :** Si une clé a été supprimée au tour N (ce qui positionne `to_step = N`), `active` devient `None`. Si le mod tente ultérieurement d'écrire une valeur pour cette clé au même step N, le code tente un `INSERT INTO Mod_KV ... VALUES (..., from_step=N, to_step=NULL)`. Comme la clé primaire est `(save_id, mod_id, key, from_step)`, SQLite lève immédiatement `sqlite3.IntegrityError: UNIQUE constraint failed`.
2. **Écritures dans le passé non détectées après suppression :** La vérification `if active is not None and step < active[0]` ne s'applique que si `active` n'est pas None. Si une clé a été supprimée au tour 3, une écriture ultérieure au tour 1 est acceptée sans erreur, insérant `(from_step=1, to_step=NULL)` qui chevauche l'intervalle historique `(from_step=2, to_step=3)`.

**Piste :**
Rechercher le dernier `from_step` existant (actif ou historique : `SELECT MAX(from_step), to_step FROM Mod_KV WHERE save_id = ? AND mod_id = ? AND key = ?`). Vérifier que `step >= max_from_step` et traiter correctement la réactivation/mise à jour sur le même step.
**Résolution (2026-10-14) :**
Dans `axiom/kernel/kv_store.py:45-89`, `_kv_write` vérifie désormais la frontière temporelle maximale `max(from_step, to_step)` sur l'historique complet pour interdire formellement toute écriture anti-chronologique, même après suppression. Si une ligne existe déjà pour le step courant (active ou clôturée par une suppression antérieure au même tour), elle est mise à jour avec `to_step = NULL` évitant le conflit d'unicité. Validé par sondes unitaires et `tests/test_turn_pipeline_b2.py`.
**Statut :** ✅ résolu.

---

## TICKET-116 — Tabletop Qt : désynchronisation de l'UI (`_turn_id` incrémenté, historique et chat pollués) en cas de tour échoué

**Constat (audit d'octobre 2026) :**
Dans `mods/axiom.ui.qt/ui/tabletop_view.py:760-770`, lors de la soumission d'une action joueur :
```python
self._turn_id += 1
self._turn_label.setText(tr("turn_fmt", count=self._turn_id))
self._chat.append_user_message(text, turn_id=self._turn_id)
self._history.append({"turn_id": self._turn_id, "event_type": "user_input", "payload": text})
```
L'état local de l'UI Qt est avancé *avant* l'exécution du tour en arrière-plan.
En cas d'échec du worker (`_on_worker_error` l.1329), la transaction SQL est annulée dans la base de données, mais côté Qt :
- `self._turn_id` n'est jamais décrémenté.
- `_turn_label` n'est pas restauré.
- Le message utilisateur reste dans `self._chat`.
- L'entrée `user_input` orpheline reste dans `self._history`.
À la tentative suivante, `self._turn_id` est de nouveau incrémenté (+2 au total) et deux entrées utilisateur consécutives polluent l'historique UI. Il s'agit du bug exact de TICKET-101 non résolu sur la couche Tabletop Qt.

**Piste :**
Dans `_on_worker_error`, restaurer `self._turn_id -= 1`, retirer la dernière entrée de `self._history` et de `self._chat`, et rafraîchir `_turn_label`.
**Résolution (2026-10-14) :**
Dans `mods/axiom.ui.qt/ui/tabletop_view.py:1335-1345`, `_on_worker_error` retire l'entrée orpheline de `self._history`, décrémente `self._turn_id`, met à jour `_turn_label` et reconstruit l'affichage via `self._chat.rebuild_from_history()`. Validé par `tests/test_turn_pipeline_b2.py::test_qt_worker_shows_llm_unreachable_message`.
**Statut :** ✅ résolu.

---

## TICKET-117 — Tabletop Qt : import inconditionnel de `axiom.help_system` provoquant un crash si le mod est désinstallé

**Constat (audit d'octobre 2026) :**
Dans `mods/axiom.ui.qt/ui/main_window.py:94` :
```python
from mods.axiom.help_system.ui.help_system import install_tooltip_gate
install_tooltip_gate(QApplication.instance())
```
Cet import est inconditionnel et direct. Pourtant, `mods/axiom.ui.qt/mod.toml` déclare explicitement :
`"axiom.help_system" = { version = ">=1.0.0", optional = true }`.
Si le mod `axiom.help_system` n'est pas installé sur la machine ou a été supprimé des dossiers de mods, `MainWindow.__init__` lève un `ModuleNotFoundError` fatal et l'application Qt ne peut pas démarrer.

**Piste :**
Entourer l'import et l'installation du tooltip gate d'un `try/except (ImportError, ModuleNotFoundError)` ou vérifier la présence du service/mod via le registre du noyau avant d'installer la porte de tooltip.
**Résolution (2026-10-14) :**
Dans `mods/axiom.ui.qt/ui/main_window.py:92-98`, l'import et l'appel à `install_tooltip_gate` sont entourés d'un bloc `try/except (ImportError, ModuleNotFoundError)` empêchant tout crash au démarrage si le mod d'aide n'est pas présent.
**Statut :** ✅ résolu.

---

## TICKET-118 — `axiom.minimal_chat` : absence de bascule automatique lors de la désactivation de `axiom.world`

**Constat (audit d'octobre 2026) :**
`mods/axiom.minimal_chat/mod.toml` est configuré avec `enabled_by_default = false`.
Si un utilisateur désactive `axiom.world` dans ses réglages :
1. `axiom.turn` est rejeté par le résolveur car sa dépendance requise `axiom.world` est inactive.
2. `turn_pipeline` n'a plus aucun fournisseur actif (puisque `minimal_chat` est désactivé par défaut).
3. `axiom.ui.qt` est rejeté car sa dépendance `turn_pipeline` est introuvable.
4. L'application Qt/CLI échoue au démarrage avec un message d'erreur bloquant.
Le passage sur `axiom.minimal_chat` ne se produit que si l'utilisateur lance explicitement l'exécutable avec l'argument `--safe-mode`. L'affirmation que « tout décoché » bascule de manière transparente sur le chat minimal en mode normal n'est pas vérifiée.

**Piste :**
Si `axiom.turn` ne peut pas être satisfait mais que l'interface a besoin d'un `turn_pipeline`, le résolveur devrait automatiquement promouvoir un mod de secours compatible fournissant `turn_pipeline` (tel que `axiom.minimal_chat`) ou clarifier l'activation dans l'UI des réglages.
**Résolution (2026-10-14) :**
Dans `axiom/kernel/loader.py:309-335`, `plan_modpack` vérifie si `turn_pipeline` est présent dans le plan d'ordre de chargement. Si absent (ex: `axiom.world` décoché), `axiom.minimal_chat` est automatiquement promu comme repli transparent (sauf si explicitement désactivé par l'utilisateur). `load_mod` supporte `force_enabled=True` pendant le bootstrap pour initialiser le mod promu. Validé par `tests/test_minimal_chat_mod.py`.
**Statut :** ✅ résolu.

---

## TICKET-119 — Noyau : requêtes SQL directes sur la table `Timeline` d'`axiom.time` dans `axiom/saves.py` et `axiom/db_helpers.py`

**Constat (audit d'octobre 2026) :**
Bien que la Phase 2 ait extrait le code des 5 fonctionnalités hors de `axiom/`, `axiom/saves.py` (l.76, 85, 363) et `axiom/db_helpers.py` (l.373) exécutent toujours des requêtes SQL directes sur la table `Timeline` (`SELECT MAX(in_game_time) FROM Timeline`, `INSERT INTO Timeline`, etc.).
Le test de non-régression `test_kernel_holds_no_feature_data_logic` dans `tests/test_engine_headless.py` réussit uniquement parce que `Timeline` a été volontairement omis de son expression régulière de vérification.

**Piste :**
Déléguer la résolution du temps en jeu et l'initialisation de la chronologie aux gestionnaires de stockage déclarés par le mod `axiom.time` via l'interface `[storage]`, sans requête SQL en dur dans le noyau.
**Résolution (2026-10-14) :**
Extraction complète réalisée :
1. Création de `mods/axiom.time/storage.py` implémentant le fournisseur `TimelineStorage` (`get_current_time`, `get_turn_at_minute`, `get_in_game_minutes_at`, `record_initial_time`).
2. Déclaration dans `mods/axiom.time/mod.toml` sous `[storage.timeline]` de `time_provider = "storage:TimelineStorage"`.
3. Support de `time_provider` dans `axiom/kernel/manifest.py`, `axiom/kernel/loader.py` et `axiom/storage_registry.py` (via `TableStorageSpec.time_provider`).
4. Remplacement de toutes les requêtes SQL directes sur `Timeline` dans `axiom/saves.py` (l.76, 85, 363) et `axiom/db_helpers.py` (l.373) par les appels au fournisseur via `axiom.storage_registry`.
5. Ajout de `Timeline` dans l'expression régulière de garde de `test_kernel_holds_no_feature_data_logic` dans `tests/test_engine_headless.py`. 0 violation restante.
**Statut :** ✅ résolu.

---

## TICKET-120 — CLI : absence de gestionnaire de sauvegarde automatique (`set_rewind_backup_handler`) lors du rewind

**Constat (audit d'octobre 2026) :**
Lors d'un rewind via `workers/db_tasks.py` (Qt) ou `main_web.py` (Web), `set_rewind_backup_handler(create_auto_backup)` est configuré, assurant la création d'un point de restauration de secours avant toute modification de la base.
En revanche, les points d'entrée CLI (`axiom/cli/play.py` et `axiom/cli/saves_cmd.py`) n'enregistrent aucun gestionnaire de backup avant d'invoquer `Session.rewind` ou `CheckpointManager.rewind`. Un rewind en CLI s'exécute donc sans filet de sécurité.

**Piste :**
`axiom/cli/` fait partie du package moteur headless `axiom/` vérifié par `export_engine.check_headless` (qui interdit tout import de `database/`, `core/`, `ui/`, `workers/`). Pour disposer de backups automatiques en CLI sans violer la frontière headless, soit déplacer `backup_manager.py` dans le moteur (`axiom/backup.py`) en le rendant agnostique, soit injecter le handler via un lanceur d'application.
**Statut :** ouvert — frontière architecturale headless.

---

## TICKET-121 — UI Web : 100% de code mort dans les routes de mutation de la mémoire vivante (`main_web.py:356-495`)

**Constat (audit d'octobre 2026) :**
Dans `main_web.py:356-408` (`_handle_memory_fact_mutation`), `419-451` (`_handle_memory_belief_mutation`) et `462-494` (`_handle_memory_model_mutation`), les blocs `if action == "create": ...`, `if action == "update": ...` et `if action == "delete": ...` sont tous indentés à l'intérieur du bloc `except ImportError:` après l'instruction `return` :
```python
try:
    from mods.axiom.living_memory.facts import Fact, delete_fact, insert_facts, update_fact
except ImportError:
    self.send_error_json(404, "Living memory mod not loaded")
    return

    if action == "create":  # <-- INDENTÉ DANS LE EXCEPT APRÈS RETURN !
```
Quand le mod `axiom.living_memory` est chargé, l'import réussit, le bloc `except` est sauté, et les méthodes retournent `None` sans rien faire et sans envoyer aucune réponse HTTP. L'édition de la mémoire vivante en Web est 100% inopérante.

**Piste :**
Désindenter le code métier pour qu'il s'exécute normalement après le bloc `try/except ImportError`.
**Priorité :** critique (fonctionnalité web complètement cassée).

---

## TICKET-122 — UI Web : `/api/session/inventory/move` échoue systématiquement en HTTP 400 (`main_web.py:1601` vs `web/app.js:1079`)

**Constat (audit d'octobre 2026) :**
Dans `web/app.js:1078-1081`, le déplacement d'un item envoie :
```javascript
body: JSON.stringify({
  instance_id: n.instance_id,
  dest_holder_kind: parts[0],
  dest_holder_id: parts.slice(1).join(':')
})
```
Or `main_web.py:1601-1604` vérifie :
```python
dest_kind = payload.get("dest_kind")
dest_id = payload.get("dest_id")
if not instance_id or not dest_kind or not dest_id:
    self.send_error_json(400, "Missing required parameters")
```
Les clés ne correspondent pas (`dest_kind` vs `dest_holder_kind`). Tout déplacement d'objet dans l'interface Web est rejeté en erreur 400.

**Piste :**
Accepter `dest_kind or payload.get("dest_holder_kind")` et `dest_id or payload.get("dest_holder_id")` dans `main_web.py`.
**Priorité :** haute (bug UX bloquant).

---

## TICKET-123 — Pipeline du tour : injection des sections de prompt M6 erronée (`mods/axiom.turn/main.py:191-206`)

**Constat (audit d'octobre 2026) :**
1. Pour `pos == "user"` (l.200-201), `messages[-1]["content"] += f"\n\n{text}"` injecte la section dans le dernier message qui est le message `system` `CRITICAL REMINDER` (`axiom/prompts.py:834`), au lieu du message `user` (`messages[-2]`).
2. Pour `pos == "system"`, le texte est concaténé à la fin de `messages[0]["content"]`, après le bloc de schéma `~~~json` final.
3. Les positions `after_lore`, `pre_history`, `post_history` définies par la spécification M6 manquent dans `SECTION_POSITIONS` (l.86) et lèvent `PromptSectionError`.

**Piste :**
Cibler le message d'index -2 pour `user` (ou chercher le dernier message `role == "user"`), insérer les sections `system` avant le bloc JSON, et ajouter les positions manquantes.
**Priorité :** haute (qualité d'assemblage du prompt LLM).

---

## TICKET-124 — UI Qt : widgets des mods ignorés par `continue` dans `settings_dialog.py:312` et `constants_sidebar.py:131`

**Constat (audit d'octobre 2026) :**
Cinq widgets développés dans les mods (`InventoryTreeView`, `TimelineView`, `UniversalLLMSettingsTab`, `CloudSettingsTab`, `ImageSettingsTab`, `MemorySettingsTab`) sont enregistrés dans les slots d'interface Qt `axiom.ui.qt:sidebar_widget` et `axiom.ui.qt:settings_tab`.
Cependant, l'UI Qt filtre explicitement ces identifiants par un `continue` pour conserver ses propres vues codées en dur, laissant le code extrait dans les mods à l'état de code mort.

**Piste :**
Supprimer le contournement ou intégrer harmonieusement les widgets contribués pour honorer l'architecture de slots.
**Priorité :** moyenne.

---

## TICKET-125 — Providers : `ProvidersService` incomplet pour 5 providers cloud (`mods/axiom.providers/main.py:150-156`)

**Constat (audit d'octobre 2026) :**
`ProvidersService` n'enregistre que 3 drivers (`gemini`, `ollama`, `universal`). Pour `claude`, `venice`, `fireworks`, `openai`, `openrouter`, `get_driver()` renvoie `None`, ce qui fait que `test_connection()` renvoie `True` sans rien tester, et `list_models()` renvoie `[]`. De plus, `SettingsDialog` contourne le service et appelle directement `build_llm_from_config`.

**Piste :**
Enregistrer des drivers pour les 5 backends cloud dans `ProvidersService` et router les tests de connexion et listes de modèles via le service.
**Priorité :** moyenne.

---

## TICKET-126 — Paquet PyPI `export_engine.py` inutilisable sans `mods/` et vulnérabilité Zip Slip dans `store.py:290`

**Constat (audit d'octobre 2026) :**
1. `export_engine.py` exclut `mods/`, mais `Session.take_turn()`, `resolve_llm_backend()` et `axiom play` exigent respectivement `axiom.turn`, `axiom.providers` et `axiom.cli`. Sans ces composants, le paquet wheel exporté crashe à chaque tentative d'utilisation.
2. Dans `axiom/kernel/store.py:289-290`, `zf.extractall(staging_extract)` extrait une archive `.axmod` sans vérifier si les noms des fichiers contiennent des séquences `../` (vulnérabilité Zip Slip / Path Traversal).

**Piste :**
Valider les membres ZIP avec `_safe_relative_path` avant extraction dans `store.py`, et fournir une solution headless autonome (ex: repli de pipeline ou inclusion des mods officiels de base dans le wheel).
**Priorité :** haute (sécurité et viabilité de la distribution PyPI).

