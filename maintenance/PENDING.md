# PENDING — tickets à étudier

## Index des tickets

| N°        | Titre                                                          | Statut    |
|-----------|----------------------------------------------------------------|-----------|
| TICKET-001| Rework tests : lisibilité, couverture et organisation          | ✅ résolu (code, sans suppression) → voir `DONE.md`, attente feu vert commit |
| TICKET-002| State_Cache jamais mis à jour entre les tours                  | ✅ résolu (code) → voir `DONE.md`, attente feu vert commit |
| TICKET-003| Supprimer les modules engine dépréciés (post-Pilier 1)        | ouvert    |
| TICKET-004| Réviser le doc d'upgrade : §5.3 Étape 3 (abstraction Qt/paths) | ✅ clos → voir `DONE.md` |
| TICKET-005| Finir l'injection de chemins (`data_dir`) du Pilier 1                | ✅ clos (absorbé) → voir `DONE.md` |
| TICKET-006| Chronicler : `chronicler_update` ignoré par `_apply_event`     | ouvert    |
| TICKET-007| Bugs backend Gemini (extraction_model 404 + >5 stop_sequences) | ✅ résolu (code) → attente feu vert commit |
| TICKET-008| Segfault torch+Qt au 1er tour (dlopen libtriton.so hors thread principal) | ✅ résolu (code) → attente feu vert commit |
| TICKET-009| Split physique `axiom-engine/` + `pyproject.toml` (pip-installable)        | ouvert    |

---

## TICKET-009 — Split physique `axiom-engine/` + `pyproject.toml` (pip-installable)

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

**Contexte :** Pilier 1 (étape B1) a extrait le moteur dans le package `axiom/`. Les anciens
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
