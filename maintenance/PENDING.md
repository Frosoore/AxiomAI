# PENDING — tickets à étudier

## Index des tickets

| N°        | Titre                                                          | Statut    |
|-----------|----------------------------------------------------------------|-----------|
| TICKET-001| Rework tests : lisibilité, couverture et organisation          | ✅ résolu (code, sans suppression) → voir `DONE.md`, attente feu vert commit |
| TICKET-002| State_Cache jamais mis à jour entre les tours                  | ✅ résolu (code) → voir `DONE.md`, attente feu vert commit |
| TICKET-003| Supprimer les modules engine dépréciés (post-Pilier 1)        | ✅ résolu (2026-06-04) — 21 modules + 3 DEPRECATED.md supprimés, 236 tests verts |
| TICKET-004| Réviser le doc d'upgrade : §5.3 Étape 3 (abstraction Qt/paths) | ✅ clos → voir `DONE.md` |
| TICKET-005| Finir l'injection de chemins (`data_dir`) du Pilier 1                | ✅ clos (absorbé) → voir `DONE.md` |
| TICKET-006| Chronicler : `chronicler_update` ignoré par `_apply_event`     | ouvert    |
| TICKET-007| Bugs backend Gemini (extraction_model 404 + >5 stop_sequences) | ✅ résolu (code) → attente feu vert commit |
| TICKET-008| Segfault torch+Qt au 1er tour (dlopen libtriton.so hors thread principal) | ✅ résolu (code) → attente feu vert commit |
| TICKET-009| Split physique `axiom-engine/` + `pyproject.toml` (pip-installable)        | ⏸ différé (handover + dev parallèle) |
| TICKET-010| Temps causal : l'horloge in-game persistée n'avance JAMAIS                 | 🔴 ouvert (critique) — review Pilier 5 |
| TICKET-011| Temps causal : avancement temps + trigger Chronicler bloqués dans la GUI (headless time-blind) | 🟠 ouvert (majeur) — review Pilier 5 |
| TICKET-012| Temps causal : design inversé vs spec §6.2/6.3 (double appel LLM/tour)     | 🟠 ouvert (majeur, à arbitrer) — review Pilier 5 |
| TICKET-013| Temps causal : `chronicler_interval` interprété en minutes mais libellé/défaut en tours | 🟠 ouvert (majeur) — review Pilier 5 |
| TICKET-014| Temps causal : `TimekeeperWorker` mort + signature cassée + écarts spec (TODO faux) | 🟡 ouvert (mineur/ménage) — review Pilier 5 |

---

## TICKET-009 — Split physique `axiom-engine/` + `pyproject.toml` (pip-installable)

**⏸ DIFFÉRÉ (décision 2026-06-04).** Le code va être rendu au possesseur originel, qui ajoute des
features côté GUI (via Gemini CLI) sans se soucier de l'archi, en **parallèle** du travail moteur.
Dans ce contexte, le split physique sert le mauvais besoin (distribution, pas coordination) et
aggrave les risques : il n'empêche pas l'éparpillement de logique côté app, ajoute une frontière
deux-packages + install editable qu'un dev non-archi (et Gemini CLI) cassera, et crée un churn de
merge maximal pendant le dev parallèle. **Décision : rester en mono-repo** avec la séparation
*logique* `axiom/` (déjà en place) — 90 % du bénéfice, zéro du danger. Le split (et le `pip install`)
se fera **plus tard**, quand le repo sera repris en solo et que les features auront été migrées dans
l'engine. La migration des features app→engine est un chantier à part (piliers), cf. ci-dessous.

**Contexte :** le Pilier 1 a extrait le moteur dans `axiom/` (zéro Qt) et l'a rendu pilotable hors
GUI (API `Session`, CLI `axiom play`, étapes 1-8). C'est l'extraction **fonctionnelle**. Reste
l'objectif **packaging** du plan (§5.2, §5.4) : faire de `axiom-engine` un package **pip-installable**
distinct de l'app UI. Le `pyproject.toml` était reporté dès l'étape 1 (« étape de split physique »).

**Ce qui resterait à faire (à ordonnancer, non planifié dans les étapes 1-8) :**
- Déplacer `axiom/` sous un dossier racine dédié `axiom-engine/axiom/` (le nom de package reste
  `axiom` → les imports `from axiom...` ne changent pas, CLI inclus puisqu'il vit dans `axiom/cli/`).
- Écrire `axiom-engine/pyproject.toml` (deps moteur : chromadb, sentence-transformers, google-genai,
  etc. ; **zéro Qt**) + `console_script` `axiom = axiom.cli:main`. README package.
- `axiom-app/pyproject.toml` (l'app actuelle réduite à l'UI) **dépend de** `axiom-engine`.
- Pré-requis : **TICKET-003** (supprimer les anciens modules `core/`/`database/`/`llm_engine/`
  dépréciés, sinon doublons à l'install). Conditions de TICKET-003 désormais réunies côté run réel.

**Finitions de propreté §5.2 (non bloquantes, regroupables ici ou à part) :**
- Splitter `axiom/prompts.py` en sous-modules (`prompts/narrative.py`, `chronicler.py`, `mini_dico.py`,
  `populate.py`). N'impacte que les consommateurs internes (arbitrator/session/chronicler/db_tasks),
  **pas** le CLI ni l'API publique.
- Passer `VectorMemory` en `Protocol` (abstraction d'embedding injectable). Additif.

**Priorité :** moyenne — c'est le dernier cran du Pilier 1, mais l'extraction fonctionnelle (le gros
de la valeur : moteur headless + CLI) est déjà acquise. À faire avant tout projet voulant
`pip install axiom-engine` (mods, UI web, notebooks).

---

## TICKET-008 — Segfault torch+Qt au premier tour narratif

**Contexte :** remonté par l'utilisateur en run réel GUI (import carte SillyTavern → envoi
message → `Erreur de segmentation`). Reproduit en headless avec Qt (`QT_QPA_PLATFORM=offscreen`),
backtrace `faulthandler` à l'appui. **Pré-existant**, indépendant de l'étape 7 (l'ancien et le
nouveau worker font tourner les ops vectorielles sur un QThread à l'identique).

**Cause racine :** le premier *encode* du modèle d'embedding (sentence-transformers) tourne sur un
QThread (VectorInitWorker puis NarrativeWorker). Il importe paresseusement `torch._dynamo` → `triton`,
qui `dlopen()` `libtriton.so`. Ce `dlopen` **depuis un thread secondaire**, Qt actif, segfault
(crash natif, pas de traceback Python). C-stack sans ambiguïté : `dlopen → libtriton.so → SIGSEGV`.
Explique le timing : le modèle se charge à l'entrée (OK), mais le 1er encode (donc le dlopen triton)
n'arrive qu'au 1er tour, au clic Envoyer.

**Fix :** `axiom/memory.py::preload_embedding_runtime()` (import `torch` + `torch._dynamo` sur le
thread courant) appelé sur le **thread principal** au démarrage (`main.py`, avant tout worker) →
le `dlopen` triton a lieu sur le thread principal, l'usage cross-thread ensuite est sûr.

**Test :** `tests/test_vector_threading.py` (+ payload `tests/_vector_qthread_scenario.py`) — rejoue
en sous-process le threading exact d'un tour GUI sous Qt offscreen ; `nopreload` → segfault (139),
`preload` → exit 0. À dents (vérifié).

**Reste :** validation en GUI réelle par l'utilisateur (le run headless prouve le câblage ; ne couvre
pas le rendu Qt). Léger surcoût au démarrage : torch est front-loadé (qq s), au lieu d'être chargé
paresseusement par le worker.

---

## TICKET-003 — Supprimer les modules engine dépréciés (post-Pilier 1)

**✅ RÉSOLU (2026-06-04).** Conditions remplies (parité + run réel GUI validé + 236 tests verts).
Vérifié par grep que le sous-graphe déprécié n'était référencé QUE par lui-même (aucun code vivant).
Supprimés : `core/{arbitrator,chronicler,config,localization,logger,paths,rules_engine,time_system}.py`,
`database/{checkpoint,event_sourcing,modifier_processor,presets,schema}.py`, tout `llm_engine/`,
`workers/db_helpers.py`, + les 3 `DEPRECATED.md`. **Conservés** (vivants, non dépréciés) :
`core/{__init__,st_parser,multiplayer_queue}.py`, `database/{__init__,backup_manager}.py`.
Label d'affichage obsolète corrigé dans `debug/startup_check.py`. Restent quelques en-têtes de
docstrings dans `axiom/` mentionnant l'ancien chemin (provenance, cosmétique — laissés tels quels).

**Contexte (historique) :** Pilier 1 (étape B1) a extrait le moteur dans le package `axiom/`. Les anciens
modules ont été copiés, et tous les imports (app + tests + debug) basculés vers `axiom.*`.
Les anciennes copies ne sont donc plus importées nulle part, mais **conservées volontairement**
pour validation. Marqueurs : `core/DEPRECATED.md`, `database/DEPRECATED.md`, `llm_engine/DEPRECATED.md`.

**Fichiers à supprimer (après confirmation) :**
- `core/` : `arbitrator.py`, `chronicler.py`, `rules_engine.py`, `time_system.py`, `config.py`, `paths.py`, `logger.py`, `localization.py`
- `database/` : `event_sourcing.py`, `checkpoint.py`, `modifier_processor.py`, `schema.py`, `presets.py`
- `llm_engine/` : `base.py`, `prompt_builder.py`, `vector_memory.py`, `universal_client.py`, `gemini_client.py`, `ollama_client.py`
- `workers/db_helpers.py`
- (+ les 3 fichiers `DEPRECATED.md` une fois la suppression faite)

**Conditions de suppression (toutes requises) :**
1. La nouvelle solution `axiom/` est au moins équivalente à l'ancienne (parité fonctionnelle).
2. L'app démarre et tourne parfaitement (run réel, pas seulement imports).
3. Aucune perte de fonctionnalité constatée.
4. Suite de tests verte sur le périmètre engine (hors échecs pré-existants déjà identifiés :
   pytest-qt absent, segfault torch+Qt sur run complet, test_persona_global, 6 tests test_phase6
   `_sync_current_form` inexistant).

**Priorité :** moyenne — à faire une fois les étapes 3-4 du Pilier 1 terminées et l'app éprouvée.

---

## TICKET-006 — Chronicler : `chronicler_update` ignoré par `_apply_event`

**Contexte :** Découvert en traitant TICKET-002. Le Chronicler (simulation du monde)
écrit ses changements de stats via `EventSourcer.append_event(..., "chronicler_update", ...)`
avec un payload `{entity_id, stat_key, delta|value}` (`axiom/chronicler.py:198-218`).
Or `EventSourcer._apply_event` ne gère que `entity_create` / `stat_change` / `stat_set` :
les events `chronicler_update` sont donc **silencieusement ignorés** et ne matérialisent
jamais dans `State_Cache`, **même sur `rebuild_state_cache`**. Les changements de monde
du Chronicler n'ont donc aucun effet sur les stats réelles.

**Ce qui serait à faire (à valider) :**
- Soit faire émettre au Chronicler des `stat_change`/`stat_set` standards (en gardant
  une trace « chronicler » dans le payload, ex. `source: "chronicler"`),
- Soit ajouter `chronicler_update` à la liste traitée par `_apply_event`.
- Vérifier qu'aucun autre `event_type` porteur de stats n'est dans le même cas.

**Priorité :** à confirmer — potentiellement haute (perte de fonctionnalité Chronicler),
mais vérifier d'abord si c'était intentionnel (events purement narratifs ?).

---

## TICKET-007 — Bugs backend Gemini (découverts en validant B1 Étape 7)

**Contexte :** la validation live headless de l'Étape 7 (`debug/run_step7_live.py`) sur un setup
Gemini-only (carte AMD, pas de LLM local) a fait remonter deux bugs **pré-existants** du backend
Gemini, indépendants de l'extraction du moteur — l'app était de fait inutilisable en Gemini.

**Bug 1 — `extraction_model` envoyé à Gemini → 404.** `extraction_model` ("llama3.1:8b") est un nom
de modèle Ollama local, passé en `model_override` à `build_llm_from_config` pour les appels
auxiliaires (décision héros Companion + 7 tâches d'extraction/Populate dans `workers/db_tasks.py`).
Sur le backend Gemini, ce nom est inconnu → `404 NOT_FOUND`.
**Fix :** `axiom/config.py::resolve_extraction_model(cfg)` (gemini → `gemini_model`, sinon
`extraction_model`). Adopté par `axiom/session.py::_get_hero_decision` et les 7 sites de `db_tasks.py`.

**Bug 2 — >5 `stop_sequences` → 400 INVALID_ARGUMENT.** L'arbitrator construit 6 stop sequences
(backend-agnostique) ; l'API Gemini en plafonne 5. Cassait **tout** tour narratif en Gemini.
**Fix :** `axiom/backends/gemini.py::_clamp_stop_sequences` (plafond 5) appliqué dans `complete()`
et `stream_tokens()`. C'est au backend de respecter sa propre limite (l'arbitrator reste agnostique).

**Tests :** `tests/test_config.py::TestResolveExtractionModel` (2), `tests/test_gemini_client.py`
(clamp, 2). Suite complète 359 passed (set d'échecs pré-existant inchangé).

**Reste / non couvert :** après ces fix, la requête Gemini est bien formée mais le **quota free-tier**
du compte est épuisé (429, `limit: 0`) → la génération narrative réelle n'a pas pu être observée ici.
À confirmer par l'utilisateur (quota régénéré, facturation, ou Ollama). Priorité : haute (bloquant Gemini).

---

## TICKET-001 — Rework tests : lisibilité, couverture et organisation

**Contexte :** Audit A1-1.10. Les `debug/test_*.py` sont conservés mais hors portée pytest. Les `tests/` couvrent bien l'engine mais manquent d'explicité (noms, docstrings, output verbose) et certains cas utiles existent en double (debug/ vs tests/).

**Ce qui serait à faire :**
- Rendre les noms de tests auto-documentants (ce qu'on teste, sous quelle condition, résultat attendu)
- Migrer les `debug/test_*.py` de type `unittest.TestCase` vers `tests/` une fois complétés/nettoyés, supprimer les doublons debug/
- S'assurer que tout ce qui sera ajouté (Piliers 1–7) a une couverture pytest dès le départ
- Évaluer pytest `--verbose` / `--tb=short` comme standard de run pour lisibilité output

**Priorité :** basse — à faire après stabilisation Phase A/B.

---

# Review Pilier 5 (Temps causal) — 2026-06-06

Revue de code demandée : la partie « temps causal » est marquée terminée mais a été implémentée par
un autre dev. Constat : la mécanique de base **ne fonctionne pas de bout en bout**. Cinq tickets
ci-dessous, du plus grave au plus mineur. Tous vérifiés par lecture du code (refs `fichier:ligne`),
aucun fix appliqué (review only).

**Cause commune** : la « Étape finale (Optimisation) » mentionnée dans
`maintenance/pilier5_temps_causal/CHANGELOG.md` a (a) retiré `elapsed_minutes` du schéma du LLM
principal et (b) désactivé le `TimekeeperWorker`. Or **c'est ce worker qui écrivait l'avancée du
temps en base** (`INSERT Timeline ... new_time`). Son remplacement inline dans l'arbitrator calcule
bien `elapsed_minutes`, mais **ne persiste plus l'horloge**. Le reste en découle.

---

## TICKET-010 — Temps causal : l'horloge in-game persistée n'avance jamais 🔴 CRITIQUE

**Constat.** L'horloge de jeu = `get_current_time()` = `SELECT MAX(in_game_time) FROM Timeline`
(`axiom/db_helpers.py:306-324`). **Aucun code n'insère de ligne `Timeline` avec l'heure avancée**
(`total_mins + elapsed_minutes`). Conséquence : la valeur retournée par `get_current_time` est
**figée** pour toute la partie.

Détail des chemins d'écriture `Timeline` (tous les INSERT recensés) :
- `axiom/arbitrator.py:358-363` (voyage) : insère `in_game_time = total_mins` — **l'ANCIENNE** valeur,
  inchangée. N'avance pas l'horloge.
- `axiom/chronicler.py:228-235` : insère `in_game_time = current_minute = get_current_time(...)` —
  inchangé lui aussi.
- `workers/timekeeper_worker.py:94-106` : **le seul** qui faisait `new_time = current_time + elapsed`
  puis l'insérait… mais ce worker est **mort** (voir TICKET-014).

L'arbitrator (`axiom/arbitrator.py:292-323`) calcule `elapsed_minutes`, s'en sert pour
`tick_modifiers` (l.453) et le renvoie dans `ArbitratorResult` (l.490), mais **ne l'écrit jamais en
base**. Seul `ui/tabletop_view.py:578` fait `self._current_time += elapsed_minutes` — un compteur
**en mémoire, côté GUI uniquement**.

**Conséquences (toutes vérifiées par lecture) :**
1. **Temps réinitialisé au rechargement.** `_resume_turn_id` (`ui/tabletop_view.py:799-802`) refait
   `self._current_time = get_current_time(db)` → relit l'horloge figée → **tout le temps écoulé dans
   la session est perdu** au reload.
2. **Contexte temporel figé pour le LLM.** `axiom/arbitrator.py:227-228` :
   `total_mins = get_current_time(...)` → `get_time_of_day_context(total_mins)` envoyé au LLM est
   bloqué à la valeur initiale (« Day 1 » à vie). Casse la promesse §6.5 « Topbar affichage cohérent »
   et le feed temps→LLM.
3. **`Scheduled_Events` ne se déclenchent jamais.** `_fetch_triggered_events(save_id, total_mins)`
   (l.238) compare à `total_mins` qui n'augmente pas → aucun event « Jour 7, 10h00 » ne pourra jamais
   tomber. Casse §6.5 « Scheduled events fiables » (alors que la TODO étape 6 est cochée).
4. Seuls les **modifiers** ticquent correctement (ils reçoivent `elapsed_minutes` en direct, l.453) —
   d'où une incohérence : les buffs expirent mais l'horloge globale, elle, ne bouge pas.

**Piste de fix.** L'arbitrator (source de vérité headless) doit, après calcul d'`elapsed_minutes`,
insérer/maj une ligne `Timeline` avec `in_game_time = total_mins + elapsed_minutes` (et corriger
l'INSERT voyage l.360 pour utiliser l'heure avancée). À coordonner avec TICKET-011 (déplacer
l'avancement hors GUI) — c'est le même chantier.

**Priorité : critique.** C'est le cœur du Pilier 5 ; en l'état la feature est non fonctionnelle
au-delà des modifiers.

---

## TICKET-011 — Temps causal : avancement + Chronicler bloqués dans la GUI 🟠 MAJEUR

**Constat.** Toute la logique « avancer l'horloge + décider de déclencher le Chronicler » vit dans
`ui/tabletop_view.py:577-629` (`_on_turn_complete`). Le moteur headless ne la fait **pas** :
- `axiom/session.py::take_turn` (l.162-178) appelle `process_turn` et renvoie le résultat **sans
  rien faire** d'`elapsed_minutes` ni du Chronicler.
- `axiom/cli/play.py` (boucle via `session.take_turn`) : **zéro** référence à `elapsed`,
  `current_time`, `Timeline` ou `chronicler` (grep à blanc).

Donc `axiom play` (et tout consommateur de l'API `Session`) est **aveugle au temps** : pas
d'avancement, pas de Chronicler, pas de Scheduled_Events. Cela viole directement la stratégie
moteur/app (`memory/project_engine_split_strategy.md` : la logique de simulation doit être dans
`axiom/`, le worker/GUI = coquille fine). Ici une brique de simulation centrale est **restée dans la
GUI** — exactement le « churn » redouté par `memory/project_parallel_dev_handover.md` (le possesseur
a câblé côté `ui/` via Gemini CLI).

**Piste de fix.** Remonter l'avancement du temps + le `should_trigger`/run du Chronicler dans le
moteur (arbitrator ou Session), la GUI ne faisant que lire l'horloge pour l'afficher. Recouvre
TICKET-010 (la persistance de l'horloge est la première étape de ce déplacement).

**Priorité : majeure** — conditionne la cohérence headless et corrige TICKET-010 par construction.

---

## TICKET-012 — Temps causal : design inversé vs spec §6.2/6.3 (double appel LLM/tour) 🟠 À ARBITRER

**Constat.** La spec (§6.2, §6.3 Étape 7) veut que **le LLM narratif déclare `elapsed_minutes`** dans
son tool_call, le `TimekeeperWorker` n'étant qu'un **fallback** quand le champ est absent. L'implémentation
fait l'**inverse** :
- `elapsed_minutes` a été **retiré** du schéma narratif (`axiom/prompts.py:48-67`,
  `NARRATIVE_TOOL_CALL_SCHEMA` ne contient plus que `scene_pace`/`game_state_tag`).
- L'arbitrator fait **systématiquement** un **second appel LLM** par tour (le Timekeeper inline,
  `axiom/arbitrator.py:292-309`, commentaire « Always use Timekeeper logic »).

**Impact.** Chaque tour = **2 round-trips LLM** au lieu d'1 (latence + coût ~×2). La justification
notée au CHANGELOG (« alléger le prompt et améliorer la fiabilité ») est discutable : on allège le
prompt principal mais on ajoute un appel réseau complet. C'est une **déviation d'une spec validée**,
décidée par un autre dev sans arbitrage.

**À décider (toi).** Soit (a) revenir à la spec : `elapsed_minutes` dans le schéma narratif +
Timekeeper en fallback only (1 appel/tour nominal, conforme §6.3) ; soit (b) assumer le double appel
et acter la déviation (mettre à jour la spec §6.2/6.3 en conséquence). Je n'ai rien changé.

**Priorité : majeure** mais c'est un **choix d'archi**, pas un bug pur — d'où « à arbitrer ».

---

## TICKET-013 — Temps causal : `chronicler_interval` minutes vs tours 🟠 MAJEUR

**Constat.** `ChroniclerEngine.should_trigger` compare désormais des **minutes** :
`(current_time - last_chronicle_time) >= self._trigger_interval` (`axiom/chronicler.py:106`). Or
`trigger_interval = cfg.chronicler_interval` (`ui/tabletop_view.py:615`), dont la sémantique est
restée « **tours** » partout :
- `axiom/config.py:56` docstring « Player turns between Chronicler runs », défaut **50** (l.69).
- Libellé UI « Chronicler interval (turns): » dans toutes les langues (`axiom/localization.py:219,455,…`).

**Impact.** Avec le défaut 50, le Chronicler se déclenche tous les **50 minutes in-game** au lieu de
tous les **50 tours**. Comme un tour avance souvent de 15–60 min, le Chronicler **sur-déclenche**
(toutes les ~1–4 tours) → coût LLM et bruit de simulation très supérieurs à l'intention, + libellé UI
désormais mensonger. (NB : effet masqué tant que TICKET-010 fige l'horloge côté DB ; mais côté GUI le
compteur `_current_time` avance, donc le sur-déclenchement est réel en GUI.)

**Piste de fix.** Choisir une unité et la rendre cohérente : soit reconvertir le réglage en minutes
(et corriger libellés + défaut + migration de `settings.json`), soit garder un trigger en tours.
La spec §6.3 Étape 5 supposait « minutes » — mais alors le défaut/libellé doivent suivre.

**Priorité : majeure** (comportement + coût), fix simple une fois l'unité tranchée.

---

## TICKET-014 — Temps causal : `TimekeeperWorker` mort + signature cassée + écarts spec 🟡 MÉNAGE

Résidus et petits écarts relevés pendant la review (regroupés, faible criticité) :

1. **`TimekeeperWorker` mort et cassé.** `workers/timekeeper_worker.py` n'est instancié **nulle part**
   (grep : seule sa propre définition). De plus il appelle `build_timekeeper_prompt(self.narrative_text)`
   (l.67) avec **1 argument**, alors que la fonction en exige **2** désormais
   (`build_timekeeper_prompt(player_action, narrative_text)`, `axiom/prompts.py:883`) → `TypeError`
   s'il était jamais lancé. ⇒ La TODO **étape 7 « Réactiver TimekeeperWorker comme fallback » est
   cochée à tort** (`maintenance/pilier5_temps_causal/TODO.md:9`) : le worker n'est ni réactivé ni
   fonctionnel. À décider : supprimer le worker (logique inline dans l'arbitrator) ou le réparer si on
   reveut un vrai fallback Qt (cf. TICKET-012).
2. **Vocabulaire `scene_pace` incohérent.** Spec §6.2 : `combat|conversation|travel|deliberate|montage`.
   Code : `pace_defaults` = `combat|dialogue|exploration|travel|deliberate|tension`
   (`axiom/arbitrator.py:315-322`) ; et le schéma narratif ne liste **aucune** énumération pour
   `scene_pace` (`axiom/prompts.py:62`, juste un exemple). `conversation`/`montage` de la spec ne
   mappent sur rien → défaut 15. Impact faible (le fallback pace n'est quasi jamais atteint puisque le
   Timekeeper tourne toujours), mais à aligner.
3. **Edge cases §6.4 non implémentés.** (a) Validation voyage : cohérence `elapsed_minutes` vs
   `Location_Connections.distance_km` — non fait (l'INSERT voyage `axiom/arbitrator.py:355-362` logge
   la distance avec un commentaire « le LLM/Rules interprétera », mais rien ne l'interprète).
   (b) Time-skip narratif : `elapsed_minutes > 480` → déclencher le Chronicler **avant** de retourner —
   non fait. À acter comme « différé » ou à planifier.

**Priorité : mineure** — ménage + alignement spec ; à traiter après 010/011.
