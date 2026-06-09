# PENDING — tickets à étudier

## Index des tickets

| N°        | Titre                                                          | Statut    |
|-----------|----------------------------------------------------------------|-----------|
| TICKET-001| Rework tests : lisibilité, couverture et organisation          | ✅ résolu (code, sans suppression) → voir `DONE.md`, attente feu vert commit |
| TICKET-002| State_Cache jamais mis à jour entre les tours                  | ✅ résolu (code) → voir `DONE.md`, attente feu vert commit |
| TICKET-003| Supprimer les modules engine dépréciés (post-Pilier 1)        | ✅ résolu (2026-06-04) — 21 modules + 3 DEPRECATED.md supprimés, 236 tests verts |
| TICKET-004| Réviser le doc d'upgrade : §5.3 Étape 3 (abstraction Qt/paths) | ✅ clos → voir `DONE.md` |
| TICKET-005| Finir l'injection de chemins (`data_dir`) du Pilier 1                | ✅ clos (absorbé) → voir `DONE.md` |
| TICKET-006| Chronicler : `chronicler_update` ignoré par `_apply_event`     | ✅ résolu (2026-06-09) — `_apply_event`/`update_state_cache` gèrent `chronicler_update` + rebuild après run chronicler |
| TICKET-007| Bugs backend Gemini (extraction_model 404 + >5 stop_sequences) | ✅ résolu (code) → attente feu vert commit |
| TICKET-008| Segfault torch+Qt au 1er tour (dlopen libtriton.so hors thread principal) | ✅ résolu (code) → attente feu vert commit |
| TICKET-009| Split physique `axiom-engine/` + `pyproject.toml` (pip-installable)        | ⏸ différé (handover + dev parallèle) |
| TICKET-015| Temps causal : Timekeeper primaire — **rendu désactivable** (toggle `timekeeper_enabled`) | ✅ résolu (2026-06-07) → `DONE.md` |
| TICKET-016| Temps causal : réglage **« Time Model » mort** — `Session._time_llm` désormais câblé | ✅ résolu (2026-06-07) → `DONE.md` |
| TICKET-017| Temps causal : `major_event_description` ignoré + **time-skip Chronicler** (spec §6.4) | ouvert (partiellement couvert par TICKET-018) |
| TICKET-018| Temps causal : Chronicler **repassé en minutes in-game** (franchissement de palier) | ✅ résolu (2026-06-07) → `DONE.md` |
| TICKET-019| Temps causal : **une seule ligne `Timeline`** par tour (doublon voyage supprimé) | ✅ résolu (2026-06-07) → `DONE.md` |
| TICKET-020| Temps causal : **scaffolding mort** retiré (commentaire brouillon + imports) | ✅ résolu (2026-06-07) → `DONE.md` |
| TICKET-021| Temps causal : **tests réparés + couverture ajoutée** (pytest installé) | ✅ résolu (2026-06-07) → `DONE.md` |
| TICKET-022| Doc : **collision de numérotation** corrigée (temps causal → TICKET-TC1→TC5) | ✅ résolu (2026-06-07) → `DONE.md` |
| TICKET-023| `Universe.load` lit la clé `name` au lieu de `universe_name` (canonique) → nom = stem du fichier | ✅ résolu (2026-06-09) — `universe_name` prioritaire, repli `name`/stem |
| TICKET-024| `Active_Modifiers` n'a pas de colonne `save_id` → table globale à l'univers, partagée entre saves (probable bug d'isolation) | ✅ résolu (2026-06-09) — colonne `save_id` + FK + migration + filtrage partout + réintégré à l'éditeur de saves |


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

**✅ RÉSOLU (2026-06-09).** `EventSourcer._apply_event` traite désormais `chronicler_update`
(même payload `delta|value` que `stat_change`/`stat_set`, provenance « chronicler » conservée dans
le journal) ; ajouté aussi au filtre incrémental `update_state_cache`. `Session.take_turn`
rematérialise `State_Cache` (+`invalidate_stats_cache`) après le run du Chronicler pour que ses
changements de monde prennent effet en jeu. Tests : `tests/test_ticket_fixes.py` (rebuild,
incrémental, `state_at`). Le Chronicler continue d'émettre `event_type="chronicler_update"` (provenance).

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

> **Lot temps causal (TICKET-015→022).** Issus d'une review de code complète du Pilier 5
> (B2-pilier5-temps-causal), demandée le 2026-06-07 parce que la partie a été développée par un
> autre contributeur. Le pilier *fonctionne* (le temps avance, le Chronicler tourne), mais
> l'implémentation livrée **inverse la cible de la spec** (`AXIOM_AI_UPGRADE_DETAILS.md §6`) :
> la spec voulait que le **LLM de narration déclare `elapsed_minutes` inline** dans son tool_call,
> avec un Timekeeper en *fallback* ; le code a retiré `elapsed_minutes` du schéma narratif et fait
> un **second appel LLM systématique** (Timekeeper). Plusieurs sous-systèmes câblés mais inertes.
> Chaque point ci-dessous a été vérifié par lecture du code (réf `fichier:ligne`), pas seulement au doc.

---

## TICKET-015 — Temps causal : Timekeeper devenu primaire au lieu de fallback

**✅ RÉSOLU (2026-06-07)** — décision : on **garde** le Timekeeper primaire mais on le rend
**désactivable** via le réglage `timekeeper_enabled` (Fichier → Réglages → Général, case « Horloger IA
(temps précis) »). Décoché → l'arbitrator saute le 2ᵉ appel LLM et estime via `scene_pace`. Détail
dans `DONE.md`. Constat d'origine conservé ci-dessous.

**Constat (`axiom/arbitrator.py:293-313`, `axiom/prompts.py:48-67`, `883-913`).** La spec §6.2/6.3
(Étapes 1-2) prévoit que le LLM principal renvoie `elapsed_minutes` dans `NARRATIVE_TOOL_CALL_SCHEMA`,
et que le `TimekeeperWorker` ne serve que de **fallback** quand le champ est absent (Étape 7). Le code
livré fait l'inverse :
- `elapsed_minutes` a été **retiré** de `NARRATIVE_TOOL_CALL_SCHEMA` (il ne reste que `scene_pace`) ;
- chaque `process_turn` fait un **deuxième appel LLM inconditionnel** (`build_timekeeper_prompt` →
  `time_llm.complete(...)`) pour déduire le temps écoulé, puis retombe sur une table `pace_defaults`
  si l'appel échoue ou ne parse pas.

**Impact :**
- **×2 appels LLM par tour narratif** → double la latence et **double la consommation de quota**.
  C'est critique sur le setup réel de l'utilisateur (Gemini free-tier, quota déjà identifié comme
  goulot — cf. TICKET-007 / `project-test-env`).
- Le sens du rythme propre au modèle de narration (qui vient d'écrire la scène) est **jeté** au profit
  d'un re-parse a posteriori du même texte par un autre prompt.
- Le rationnel invoqué dans le CHANGELOG (« alléger le prompt principal, fiabiliser ») est défendable,
  mais **non documenté comme déviation** et le `TODO.md`/`DOC.md` du pilier affirment toujours
  « le LLM décide du temps écoulé » → doc trompeuse.

**Décision à prendre (utilisateur) :**
- **Option A — assumer la déviation** : garder le Timekeeper primaire, mais (1) mettre à jour la spec §6
  + la doc du pilier, (2) le rendre conditionnel/désactivable pour économiser le quota (cf. TICKET-016).
- **Option B — revenir à la spec** : ré-ajouter `elapsed_minutes` au schéma narratif (1 appel/tour),
  Timekeeper réduit au fallback quand le champ manque.

**Priorité :** haute (coût quota direct + écart spec). À trancher avant d'optimiser le reste du lot.

---

## TICKET-016 — Temps causal : réglage « Time Model » mort (`_time_llm` jamais câblé)

**✅ RÉSOLU (2026-06-07)** — `Session._resolve_time_llm` construit le backend du Timekeeper depuis
`resolve_time_model(cfg)` quand aucun `time_llm` explicite n'est passé (patron du `hero_llm`), repli
sur le backend principal si la construction échoue. Détail dans `DONE.md`. Constat d'origine ci-dessous.

**Constat (`axiom/session.py:76,81,148` ; `axiom/cli/play.py:288` ; `ui/tabletop_view.py:528`).**
`Session.__init__` fait `self._time_llm = time_llm if time_llm else llm`. **Aucun appelant de
production ne passe `time_llm`** (ni le CLI, ni la GUI), et — contrairement à `hero_llm` qui se
construit en lazy depuis la config (`session.py:329-333`, via `resolve_extraction_model`) — il n'existe
**aucun build lazy** de `_time_llm` depuis `resolve_time_model(cfg)` (`axiom/config.py:151-159`).

**Conséquence :** le Timekeeper tourne **toujours sur le modèle de narration principal**. L'option
« Time Model » ajoutée aux réglages (TICKET-012 de `DONE.md`, `config.py:69` + `settings_dialog.py`)
est **morte** : la changer n'a aucun effet. Tout l'argument de TICKET-012 (« double appel LLM sans
surcharger le modèle principal ») tombe.

**Fix proposé :** dans `Session`, construire `_time_llm` en lazy depuis `resolve_time_model(cfg)` quand
`time_llm is None` (mirror exact du patron `hero_llm`), via `build_llm_from_config(cfg, model_override=…)`.
Alternative : passer explicitement `time_llm` aux deux sites de construction. À traiter avec TICKET-015
(si on garde le Timekeeper, autant qu'il utilise vraiment un petit modèle dédié).

**Priorité :** haute (bug fonctionnel silencieux — un réglage exposé à l'utilisateur ne fait rien).

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

## TICKET-018 — Temps causal : Chronicler repassé en tours (régression vs spec §6.3 Étape 5)

**✅ RÉSOLU (2026-06-07)** — `should_trigger(current_time, previous_time)` redevient à 2 arguments et
déclenche par **franchissement d'un palier de `chronicler_minutes_interval` minutes in-game** (défaut
720 = 12 h, exposé en minutes dans l'UI). Un long time-skip déclenche donc une simulation off-screen.
`chronicler_interval` (tours) gardé en champ legacy. Détail dans `DONE.md`. Constat d'origine ci-dessous.

**Constat (`axiom/chronicler.py:90-106` ; `axiom/session.py:184-198`).** La spec voulait un déclenchement
du Chronicler **basé sur les minutes in-game** (`should_trigger(current_time, last_chronicle_time)`),
pour qu'« un long voyage déclenche plusieurs World Turns successifs ». Le code livré (TICKET-013 de
`DONE.md`) est repassé à `should_trigger(turn_id)` ≡ `turn_id % interval == 0`.

La raison invoquée (CHANGELOG TICKET-013) : l'implémentation minutes d'origine comparait des **minutes
à un seuil exprimé en tours** (`chronicler_interval`, défaut 50) → conflit d'unités → déclenchement
quasi à chaque tour. Le revert « corrige » le symptôme mais **jette le bénéfice clé du Pilier 5** :
un tour de combat (5 min) et un tour de voyage (8 h) déclenchent désormais le Chronicler à l'identique.

**⚠️ Effet de bord — tests cassés (vérifié).** La signature de `should_trigger` est passée de
`(current_time, last_chronicle_time)` à **`(turn_id)` (1 seul argument)** sans mettre à jour les tests.
`tests/test_chronicler.py::TestShouldTrigger` l'appelle encore avec **2 arguments** (l.113, 119, 125,
131-132, 138-139 : `should_trigger(50, 0)`, `should_trigger(100, 50)`, …) → **`TypeError` à l'exécution**.
Ces 7 assertions sont donc **rouges** : le pilier marqué « ✅ terminé » a en réalité une suite de tests
en échec sur le Chronicler. (cf. TICKET-021.)

**Fix propre proposé :** garder le déclenchement minutes mais avec une **config en minutes** dédiée
(ex. `chronicler_minutes_interval`) et comparer `current_time - last_chronicle_time >= interval`
(persister `last_chronicle_time`). On peut conserver *en plus* un plafond en tours comme garde-fou.
Lié à TICKET-017 (le time-skip est une autre voie pour déclencher le monde sur les grands sauts).

**Priorité :** moyenne — décision design ; le comportement actuel est « correct mais appauvri ».

---

## TICKET-019 — Temps causal : doublons `Timeline` au voyage + inserts hors transaction

**✅ RÉSOLU (2026-06-07)** — une **seule** ligne `Timeline` par tour, écrite après la boucle de
state-changes ; un tour de voyage enrichit sa description (« Traveled to … (km) ») au lieu d'une 2ᵉ
ligne. Test `TestCausalTime::test_single_timeline_row_when_player_travels`. *(Le point secondaire
« inserts hors transaction batch » n'a pas été modifié — l'écriture reste sur sa propre connexion
mais déplacée après application des changements ; jugé non bloquant.)* Constat d'origine ci-dessous.

**Constat (`axiom/arbitrator.py:329-339` puis `366-379`).** Chaque tour insère une ligne `Timeline`
« Turn advanced by X mins » (l.333). Puis, si le joueur change de `Location` et qu'une
`Location_Connections.distance_km` existe, une **seconde** ligne `Timeline` « Traveled to X (km) » est
insérée **avec le même `new_time`** (l.374-377). Résultat : deux lignes `Timeline` au même timestamp
pour un tour de voyage — `get_current_time` lit le `MAX` donc l'horloge reste juste, mais le panneau
Timeline de la GUI (`LoadTimelineTask`) se retrouve **encombré de doublons**.

Secondaire : ces deux inserts ouvrent **leur propre connexion + commit** (l.332-337, 374-379), **hors**
de la transaction batch finale (`append_events_batch`, l.483). Si le tour lève une exception après
l'insert, le temps est **déjà avancé** et persisté (incohérence partielle possible). Idem pour le commit
du Chronicler.

**Ce qui serait à faire :** n'écrire qu'**une** ligne Timeline par tour (enrichir la description si
voyage : « +X mins — Traveled to Y (Z km) »), et idéalement intégrer l'avancée de temps dans la même
unité transactionnelle que les events du tour.

**Priorité :** basse-moyenne (cosmétique GUI + robustesse). Sans impact sur l'horloge.

---

## TICKET-020 — Temps causal : scaffolding mort laissé en production

**✅ RÉSOLU (2026-06-07)** — commentaire de brouillon + import `get_current_time` (désormais réellement
utilisé par TICKET-018) nettoyés dans `session.py` ; imports morts `ChroniclerWorker`/`ChroniclerEngine`/
`EventSourcer` retirés de `tabletop_view._on_turn_complete`. Constat d'origine ci-dessous.

**Constat :**
- `axiom/session.py:185-187` — commentaire de **brouillon** laissé tel quel en prod :
  « *We need the last_chronicle_time to compare, but wait, TICKET-013 says we should trigger on
  turn_id, not minutes!* ». À remplacer par un commentaire propre (ou supprimer).
- `axiom/session.py:180` — `from axiom.db_helpers import get_current_time` **importé mais inutilisé**
  dans `take_turn` (le temps est désormais lu côté GUI / persisté dans l'arbitrator).
- `ui/tabletop_view.py:567-569` — `_on_turn_complete` importe `ChroniclerWorker`, `ChroniclerEngine`,
  `EventSourcer` mais **n'en utilise aucun** (le Chronicler est passé dans `Session.take_turn`). Vérifier
  au passage si `self._chronicler` (l.100) / `self._chronicler_worker` (l.104) sont devenus morts eux aussi.

**Priorité :** basse (propreté). Regroupable avec un nettoyage app-side.

---

## TICKET-021 — Temps causal : aucune couverture de tests

**✅ RÉSOLU (2026-06-07)** — `pytest` installé dans le `.venv` ; les 6 tests `should_trigger` cassés
(TypeError) repassent verts via la nouvelle signature ; 2 tests arbitrator cassés par le 2ᵉ appel LLM
réparés (backend Timekeeper distinct) ; 6 nouveaux tests (`TestCausalTime` + franchissement de palier).
**215 tests ciblés verts**, zéro régression. Détail dans `DONE.md`. Constat d'origine ci-dessous.

**Constat (`tests/test_arbitrator.py`, `tests/test_chronicler.py`).** Le Pilier 5 a été livré **sans
aucun test dédié** : rien n'assert `elapsed_minutes`, le second appel Timekeeper, la table de fallback
`pace_defaults`, ni la persistance `Timeline`. Pire, comme `process_turn` fait maintenant un **second
appel LLM** (`time_llm.complete`), tous les tests `process_turn` existants exercent **silencieusement**
le chemin de fallback du mock (le mock ne renvoie pas de JSON Timekeeper parsable) — un changement de
comportement non couvert.

**⚠️ Tests déjà cassés (vérifié, lié à TICKET-018).** `tests/test_chronicler.py::TestShouldTrigger`
(7 assertions, l.113-139) appelle `should_trigger(turn_id, last_time)` avec **2 arguments** alors que la
signature a été réduite à **1** → **`TypeError`**. Ces tests sont rouges aujourd'hui. À corriger en même
temps que la décision TICKET-018 (le bon comportement détermine ce qu'on doit tester).

**Note env :** `pytest` n'est **pas** installé dans le `.venv/` du projet (`No module named pytest`,
constaté le 2026-06-07). Impossible de faire tourner la suite en l'état sans l'ajouter — à voir avec
l'utilisateur (cf. `project-test-env`).

**Ce qui serait à faire :**
- Tests arbitrator : mock LLM renvoyant un JSON Timekeeper `{"elapsed_minutes": N}` → assert que
  `result.elapsed_minutes == N`, que `tick_modifiers` reçoit `N`, et qu'une ligne `Timeline` est créée.
- Test du fallback `pace_defaults` (Timekeeper qui échoue/ne parse pas → défaut par `scene_pace`).
- Test `should_trigger` aligné sur la décision finale TICKET-018.

**Priorité :** moyenne — à recâbler en même temps que les correctifs du lot (sinon on teste un
comportement qu'on va changer).

---

## TICKET-022 — Doc : collision de numérotation des tickets dans `DONE.md`

**✅ RÉSOLU (2026-06-07)** — les cinq tickets temps causal de `DONE.md` ont été renumérotés
**TICKET-TC1 → TC5** (contenu inchangé) ; TICKET-010/011/012 désignent désormais sans ambiguïté le lot
Save Management. Note explicative ajoutée en tête de `DONE.md`. Constat d'origine ci-dessous.

**Constat.** `DONE.md` réutilise **TICKET-010, -011, -012** pour **deux lots distincts** :
- lot « UI/UX Save Management / variantes / AttributeError » (clos 2026-06-06) ;
- lot « temps causal » (010 persistance horloge, 011 avancement+Chronicler, 012 Time Model).

Trois numéros désignent donc chacun **deux tickets sans rapport**, ce qui casse la référence croisée
(« voir TICKET-011 » est ambigu). L'index de `PENDING.md` ne va lui que jusqu'à TICKET-009.

**Ce qui serait à faire :** renuméroter les tickets temps causal de `DONE.md` sur une plage libre
(p. ex. en alignant sur la suite réelle) **sans toucher** aux numéros déjà référencés ailleurs, ou au
minimum les préfixer (`TICKET-T01…` pour le temps). Les nouveaux tickets de review ci-dessus partent
volontairement à **015** pour ne pas aggraver la collision. À trancher avec l'utilisateur (lui seul
sait quelles refs externes existent).

**Priorité :** basse (hygiène doc), mais utile avant que d'autres tickets ne s'empilent.

---

## TICKET-023 — `Universe.load` lit `name` au lieu de `universe_name`

**✅ RÉSOLU (2026-06-09).** `axiom/universe.py::Universe.load` →
`meta.get("universe_name") or meta.get("name") or Path(path).stem`. Vérifié sur `ST_Aglae.db`
réel (« Aglae » au lieu de « ST_Aglae ») et sur univers compilé (« Drakthar » au lieu de
« universe »). Tests : `tests/test_ticket_fixes.py`.

**Constat (2026-06-09, repéré pendant le Pilier 2).** `axiom/universe.py::Universe.load`
fait `name = meta.get("name") or Path(path).stem`. Or la clé canonique de `Universe_Meta`
(écrite par `db_helpers.provision_blank_universe`, le Creator Studio et `axiom/compile.py`)
est **`universe_name`**, pas `name`. Conséquence : `Universe.load` retombe toujours sur le
**stem du fichier**. Avec Universe-as-Code, le cache compilé s'appelle toujours `universe.db`
→ le nom affiché devient « universe ».

**Fix proposé :** `name = meta.get("universe_name") or meta.get("name") or Path(path).stem`.
Une ligne, mais touche le **chemin de chargement partagé** (`Universe`) → zone de collision
potentielle (cf. collab). À traiter isolément, avec garde-fous (`test_engine_headless`,
`test_cli_play`) + idéalement un test sur `Universe.load`.

**Priorité :** moyenne (cosmétique mais visible dès qu'on joue un univers compilé).

---

## TICKET-024 — `Active_Modifiers` sans `save_id` (modifiers globaux à l'univers)

**✅ RÉSOLU (2026-06-09).** Colonne `save_id` ajoutée à `Active_Modifiers` (DDL + FK `Saves`
ON DELETE CASCADE pour les DBs neuves ; migration `migrate_active_modifiers_table` = `ALTER ADD
COLUMN` pour les DBs existantes, branchée dans `create_new_save`/`load_saves`). Filtrage par
`save_id` partout : `modifiers.py` (`add_modifier`/`tick_modifiers`/`apply_modifiers`/`_fetch_modifiers`),
`arbitrator.py::_fetch_effective_stats`, `hardcore_worker.py`. Modifiers réintégrés à l'éditeur de
saves (`axiom/saves.py`). Tests : `tests/test_ticket_fixes.py` (isolation entre saves, tick scopé,
migration) + `tests/test_saves_editing.py` (round-trip). Les rows héritées (save_id='') sont
orphelines et ignorées.

**Constat (2026-06-09, repéré pendant le Pilier 2 / éditeur de saves).** Le schéma
`Active_Modifiers` (`axiom/schema.py`) = `modifier_id, entity_id, stat_key, delta,
minutes_remaining` + FK `entity_id`→`Entities`. **Pas de colonne `save_id`.** Donc les
modifiers temporaires ne sont **pas isolés par sauvegarde** : ils sont partagés par toutes les
parties d'un même univers. Or `_fetch_effective_stats` (arbitrator) les applique par entité, et
`TickModifiersTask` les fait décrémenter — sans distinction de save.

**Impact :** deux parties du même univers se partagent les buffs/debuffs actifs. Probable bug
d'isolation. Conséquence pratique pour l'éditeur de saves (Phase 6) : les modifiers ont été
**exclus** du format `save_state.toml` (les inclure suggérerait une isolation inexistante).

**Fix proposé :** ajouter `save_id` à `Active_Modifiers` (+ FK `Saves` ON DELETE CASCADE, +
migration), et filtrer par `save_id` partout (arbitrator `_fetch_effective_stats`, `modifiers.py`,
`TickModifiersTask`). Zone sensible (touche le calcul de stats + le temps causal Pilier 5) → ticket
dédié, à séquencer avec le pote (collision possible). Une fois fait, réintégrer les modifiers dans
l'éditeur de saves.

**Priorité :** moyenne (bug réel mais d'impact limité tant qu'on joue une partie à la fois par univers).
