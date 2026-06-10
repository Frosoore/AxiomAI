# DONE — tickets clos

Récapitulatifs des tickets traités. Les tickets restent numérotés dans
`PENDING.md` (liste des tickets ouverts) pour préserver la numérotation.

> **Note numérotation (2026-06-07, TICKET-022).** Le lot « temps causal » du
> 2026-06-06 avait réutilisé les numéros TICKET-010/011/012, déjà pris par le lot
> « Save Management » du même jour. Pour lever l'ambiguïté, les cinq tickets temps
> causal ont été renumérotés **TICKET-TC1 → TC5** (le contenu est inchangé). Les
> tickets TICKET-010/011/012 désignent désormais sans ambiguïté le lot Save
> Management. Plusieurs de ces tickets TC ont été révisés par la review du
> 2026-06-07 (cf. `PENDING.md`, lot TICKET-015→022).

---

## TICKET-026 — `parse_tool_call` : résilience confirmée

**Statut :** clos le 2026-06-09, décision utilisateur. Le comportement **résilient** est conservé :
sur un bloc JSON de tool-call malformé/tronqué, `axiom/backends/base.py::parse_tool_call` renvoie
`(texte, None)` au lieu de lever `LLMParseError` — un tour narratif n'est jamais interrompu par un
JSON cassé (adapté au setup Gemini réel). Les tests `tests/test_llm_base.py` étaient déjà alignés.
**Aucun changement de code.**

---

## TICKET-027 — Creator Studio sur univers-dossier : sync db → source

**Statut :** résolu le 2026-06-09 (Pilier 2, Phase 8).

**Problème :** depuis Universe-as-Code, un univers importé/installé vit en dossier source
(`universe.toml` + cache `.axiom-cache/universe.db`) et le Hub fait éditer le **cache** au Creator
Studio. Les modifs Studio ne remontaient pas dans l'arbo texte (« le texte est la vérité » violé) et
auraient été écrasées au prochain refresh de définition.

**Fix :** `axiom/library.py::sync_source_from_db` — après chaque écriture de définition côté app
(`save_full_universe`, `save_universe_meta`, les 7 `Populate*Task`, `DeleteEntityTask`), l'arbo
texte est réécrite en miroir depuis le `.db` : décompilation vers un dossier temporaire puis
copie + purge des fichiers orphelins (`.axiom-cache/` et `.git/` jamais touchés), entités
`origin='runtime'` exclues de l'export, hash de cache mis à jour (pas de recompilation parasite).
Non bloquant : un échec de sync logge un warning sans faire échouer la sauvegarde Studio.

**Tests :** `tests/test_dev_hotreload.py::TestStudioSyncSource` (5, dont un bout-en-bout worker Qt
offscreen et un round-trip compile(source resynchronisée) == définition du db).

---

## TICKET-004 — Réviser le doc d'upgrade : §5.3 Étape 3 (abstraction Qt/paths)

**Statut :** clos le 2026-05-23. Révision purement documentaire (aucun code modifié).

**Problème :** la prémisse de l'Étape 3 du Pilier 1 (§5.3 de
`AXIOM_AI_UPGRADE_DETAILS.md`) était erronée — elle décrivait `core/paths.py`
comme « Qt-friendly » et préconisait un split `EngineConfig`/`AppConfig`.

**Vérifications faites (grep, 2026-05-23) :**
- `axiom/paths.py`, `axiom/logger.py`, `axiom/config.py` : pur stdlib, **zéro Qt**,
  déjà importables headless (config.py le dit dans son docstring).
- Chemins **codés en dur à l'import** : `~/.config/AxiomAI`, `~/.cache/AxiomAI`,
  `~/AxiomAI` (`axiom/paths.py`).
- `AppConfig` mélange champs moteur + UI mais reste 100 % Python.
- `axiom.config.GLOBAL_DB_FILE` importé comme **constante** par `ui/hub_view.py`,
  `ui/setup_view.py`, `ui/settings_dialog.py`.
- `tests/test_config.py` patche `axiom.config._CONFIG_FILE` / `_CONFIG_DIR`.

**Corrections apportées à `AXIOM_AI_UPGRADE_DETAILS.md` :**
1. §5.1 — suppression de la puce fausse « paths Qt-friendly » + note de révision
   expliquant le vrai constat (chemins codés en dur).
2. §5.2 — commentaire de l'arbre cible sur `config.py` mis à jour (split abandonné).
3. §5.3 Étape 3 — réécrite : constat corrigé, justification de l'abandon du split,
   décision validée (injection des chemins via `Session(..., data_dir=...)` en
   Étape 4) ; prémisse d'origine conservée en `<details>` pour historique.
4. Tableau récap (§16) — ligne `core/config.py` « Split EngineConfig/AppConfig »
   barrée + marquée abandonnée.

**Décision actée :** l'Étape 3 ne bloque pas l'Étape 4 ; le split de config est
reporté/abandonné sauf besoin avéré ; l'injection des chemins est portée par
l'API `Session`.

---

## TICKET-005 — Finir l'injection de chemins (`data_dir`) du Pilier 1

**Statut :** clos le 2026-05-23 — **absorbé** dans le plan (pas d'action directe restante).

**Problème :** suite de TICKET-004. `Session(data_dir=...)` était censé porter
l'injection des chemins, mais lecture intégrale du code (`session.py`, `arbitrator.py`,
`memory.py`, `config.py`, `paths.py`, `logger.py`, `narrative_worker.py`,
`tabletop_view.py`, `test_session.py`) a montré que le sujet recouvre **deux**
problèmes distincts :
- **P — rangement des fichiers** : chemins gelés à l'import ; `data_dir` ne couvre
  que la VectorMemory et n'est jamais exercé (l'app lit `VECTOR_DIR` en direct).
- **U — deux « machines à jouer un tour » en parallèle** : `Session.take_turn` est
  débranchée ET plus pauvre que le `NarrativeWorker` (pas de décision héros
  Companion, source d'historique différente). Le « simple wrapper worker→Session »
  du plan d'origine n'est donc pas simple.

**Résolution :** redécoupé en plan révisé `AXIOM_AI_UPGRADE_DETAILS.md` **§5.3-bis,
Étapes 5→8** :
- Étape 5 — injection des chemins (P), risque bas + test ;
- Étape 6 — parité de `Session` (héros Companion, historique unifié) ;
- Étape 7 — adoption par le worker (U), run-testé ;
- Étape 8 — CLI sur `Session`.

**Décision de design actée (Étape 5) :** hybride pour `settings.json` + `global.db`
— machine-globaux par défaut (GUI inchangée, clé API saisie une fois), surcharge
explicite (`config_dir` distinct de `data_dir`) pour l'isolement total (tests,
embedders). Note : sandboxer ≠ éphémère.

→ Le travail concret se poursuit donc dans `B1-pilier1-engine-headless/` (Étape 5).

---

## TICKET-002 — State_Cache jamais mis à jour entre les tours

**Statut :** résolu (code) le 2026-05-23 — attente feu vert pour commit.
Détail complet : `maintenance/TICKET-002-state-cache-sync/`.

**Diagnostic :** l'`ArbitratorEngine` écrit les events dans `Event_Log` mais jamais
dans la table `State_Cache`, qui n'est rafraîchie que par `rebuild_state_cache`
(load de session / rewind). La sidebar lit `State_Cache` → stats figées au load.
Snapshots jamais pris dans l'app (`take_snapshot_async` sans site d'appel) → un
rebuild par tour serait O(historique²).

**Fix :** `EventSourcer.update_state_cache(save_id, events)` — UPSERT incrémental des
events stat du tour sur les entités touchées (sémantique identique à un rebuild,
modifiers toujours appliqués à la lecture). Appelé dans l'arbitrator juste après
`append_events_batch`. Tests : `tests/test_event_sourcing.py::TestUpdateStateCache`
(4 cas dont parité avec `rebuild_state_cache(force_full=True)`). 55 tests verts
(event_sourcing + arbitrator + checkpoint + modifier).

**Découverte connexe → TICKET-006 :** les events `chronicler_update` ne sont pas
matérialisés par `_apply_event` (bug distinct).

---

## TICKET-001 — Rework tests : lisibilité, couverture, organisation

**Statut :** résolu (code, SANS suppression) le 2026-05-23 — attente feu vert commit.
Détail complet : `maintenance/TICKET-001-rework-tests/`.

**Décision utilisateur :** option 1 sans suppression — docstrings + noms
auto-documentants sur `tests/`, migration des `debug/test_*.py` utiles (copie),
DEPRECATED.md sur les doublons, **rien supprimé** (suppression → TICKET-003).

**Lot A :** docstrings (condition → résultat) ajoutées sur les 22 fichiers de
`tests/` (~330 tests), quelques renommages ciblés, 1 ligne morte retirée dans
`test_chronicler.py`. Noms déjà majoritairement auto-documentants.

**Lot B :** audit des 8 `debug/test_*.py` (→ `debug/DEPRECATED.md`). Couverture
unique migrée en pytest : `tests/test_localization.py` (la localisation n'avait
aucune couverture) et `tests/test_universe_meta.py` (round-trip params LLM).

**Vérif :** `pytest tests/` → **347 passed**, 7 failed + 5 errors **tous
pré-existants connus** (persona_global ; 6× phase6 `_sync_current_form` ; 5×
ambiance pytest-qt absent). Zéro régression.

---

## TICKET-010 — UI/UX Save Management (Multisélection, Raccourcis, Menu Contextuel)

**Statut :** clos le 2026-06-06.

**Réalisations :**
- **Multisélection :** Activation de `QAbstractItemView.ExtendedSelection` sur la liste des sauvegardes dans `setup_view.py`.
- **Raccourcis clavier :** Ajout de la gestion de Ctrl+A (sélection de tout), des touches directionnelles (Ctrl+Up/Down) pour l'extension de la sélection, et de la touche "Delete" pour la suppression multiple.
- **Correction du bug de suppression multiple :** La suppression nécessitait auparavant deux confirmations car la liste était modifiée de manière asynchrone sans attendre la fin des tâches de base de données. Corrigé en s'assurant de la synchronisation via les signaux.
- **Interaction Souris :** Double-clic pour lancer une sauvegarde ("Play"), et ajout d'un menu contextuel (clic droit) offrant les actions "Play", "Rename" et "Delete".

---

## TICKET-011 — Bug persistance des variantes & Condition de course LoadFullUniverseTask

**Statut :** clos le 2026-06-06.

**Problème :** Le jeu générait des choix de premiers messages aléatoires ou affichait le même message sur toutes les sauvegardes après une tentative de rustine via `Universe_Meta`. Le problème racine était une condition de course lors du chargement d'une sauvegarde :
- `TabletopView` appelait en parallèle `load_session_history(save_id)` et `load_full_universe()`.
- L'ancienne tâche `LoadFullUniverseTask` sélectionnait *automatiquement* la sauvegarde la plus récente si `save_id` n'était pas fourni.
- Cela écrasait l'historique correct chargé par `load_session_history` avec l'historique d'une potentielle autre sauvegarde (ou un historique vide), forçant `TabletopView` à recréer et réinsérer un nouveau premier message à chaque rechargement.

**Fix :** `load_full_universe` accepte désormais le `save_id` explicite et ne tente plus de deviner la sauvegarde la plus récente quand l'identifiant est fourni. L'historique n'est plus écrasé à tort, le premier message n'est pas réécrit, et les choix de variantes de l'utilisateur sont persistés nativement dans l'Event Log pour chaque sauvegarde individuellement.

---

## TICKET-012 — Bug d'enregistrement de la réponse de l'IA (AttributeError)

**Statut :** clos le 2026-06-06.

**Problème :** Les messages générés par l'IA s'affichaient bien à l'écran grâce au streaming, mais disparaissaient définitivement après un rechargement de la sauvegarde.
L'erreur provenait d'un crash silencieux (intercepté mais entravant la logique) lors de l'enregistrement dans la base de données au sein de `process_turn`. 
L'arbitrator tentait d'accéder à `user_message.content` alors que `user_message` est transmis sous forme de chaîne de caractères (`str`). Ce crash empêchait l'appel à `append_events_batch()`.

**Fix :** Remplacement de `user_message.content` par `user_message` lors de l'appel au `Timekeeper` dans `axiom/arbitrator.py`. L'historique complet, incluant la réponse générée, est maintenant enregistré correctement dans la base de données.

---

## TICKET-TC1 — Temps causal : Persistance de l'horloge in-game

**Statut :** clos le 2026-06-06. *(révisé 2026-06-07 — TICKET-019 : les deux insertions `Timeline` par tour de voyage ont été fusionnées en une seule.)*

**Réalisations :**
- L'arbitrator enregistre désormais l'heure avancée dans la table `Timeline` immédiatement après avoir calculé les `elapsed_minutes` via le modèle de temps ou le fallback (`scene_pace`).
- Les insertions liées aux voyages spatiaux utilisent désormais cette heure actualisée pour enregistrer l'entrée dans la chronologie.

---

## TICKET-TC2 — Temps causal : Avancement + Chronicler dans le Moteur

**Statut :** clos le 2026-06-06.

**Réalisations :**
- La vue `TabletopView` ne maintient plus un compteur de temps factice local (`self._current_time += elapsed_minutes`).
- Elle relit simplement l'heure depuis la base de données.
- L'instanciation et le déclenchement du `ChroniclerEngine` ont été déplacés de l'interface graphique (`_on_turn_complete`) vers le moteur headless, directement à la fin de `Session.take_turn`.

---

## TICKET-TC3 — Temps causal : Modèle Temps Spécifique (Time Model)

**Statut :** clos le 2026-06-06. *(révisé 2026-06-07 — TICKET-016 : le réglage était mort, `Session._time_llm` n'était jamais câblé ; il est désormais construit depuis `resolve_time_model`.)*

**Réalisations :**
- Ajout de l'option `Time Model` dans les paramètres (sous `Extraction Model`) via `config.py` et `settings_dialog.py`.
- L'appel spécifique au `Timekeeper` dans l'arbitrator utilise dorénavant ce modèle, ce qui permet de conserver la fiabilité du double appel LLM sans surcharger le modèle principal de narration avec des requêtes chronophages.

---

## TICKET-TC4 — Temps causal : Rythme du Chronicler (Tours)

**Statut :** clos le 2026-06-06. *(⚠️ REMPLACÉ le 2026-06-07 — TICKET-018 : le déclenchement en tours est revenu à un déclenchement basé sur les **minutes in-game** par franchissement de palier, pour restaurer le bénéfice « un long voyage déclenche le Chronicler ». L'approche « tours » décrite ici n'est donc plus en vigueur.)*

**Réalisations (historiques) :**
- Changement de la logique interne du `ChroniclerEngine`.
- Au lieu de comparer l'heure locale (minutes) avec un seuil en tours (provoquant un déclenchement quasi à chaque tour), il s'appuie désormais directement sur le numéro du tour (`turn_id % interval`).

---

## TICKET-TC5 — Temps causal : Nettoyage et Cohérence

**Statut :** clos le 2026-06-06.

**Réalisations :**
- Le fichier mort `workers/timekeeper_worker.py` a été définitivement supprimé.
- Alignement du `scene_pace` du Timekeeper fallback dans `arbitrator.py` avec la spec (ajout de `conversation` et `montage`).

---

## TICKET-015/016/018/019/020/021 — Temps causal : correctifs issus de la review du 2026-06-07

**Statut :** clos le 2026-06-07. Issus de la grosse review du Pilier 5 (cf. `PENDING.md`).
Vérifié : suite de tests ciblée **215 passed** (arbitrator, chronicler, config, modifier,
session, localization, event_sourcing, checkpoint, cli_play, narrative_worker, db_worker_timeline…),
zéro régression. La suite *complète* segfault toujours sur le TICKET-008 pré-existant (torch+Qt
hors `main.py`), sans rapport.

- **TICKET-016 (bug) — réglage « Time Model » câblé.** `Session._time_llm` est désormais construit
  en lazy depuis `resolve_time_model(cfg)` quand aucun `time_llm` explicite n'est fourni (patron
  identique au `hero_llm`), avec repli sur le backend principal en cas d'erreur. Le Timekeeper utilise
  enfin le modèle configuré (`axiom/session.py::_resolve_time_llm`).
- **TICKET-015 (design) — Timekeeper rendu désactivable.** Nouveau réglage booléen
  `timekeeper_enabled` (défaut `True`). Quand il est décoché, l'arbitrator **saute le 2ᵉ appel LLM**
  et estime le temps depuis `scene_pace` (table `pace_defaults`). Toggle exposé dans **Fichier →
  Réglages → onglet Général**, case « Horloger IA (temps précis) » (`ui/settings_dialog.py`,
  `axiom/config.py`, libellés `axiom/localization.py` en/fr).
- **TICKET-018 (régression) — Chronicler repassé en minutes in-game.** `should_trigger(current_time,
  previous_time)` redevient à 2 arguments et déclenche par **franchissement d'un palier de
  `chronicler_minutes_interval` minutes** (nouveau réglage, défaut 720 = 12 h, exposé en minutes dans
  l'UI). `Session.take_turn` calcule `previous_time = current_time - result.elapsed_minutes`. Un long
  time-skip déclenche donc une simulation off-screen (bénéfice clé du pilier restauré). `chronicler_interval`
  (tours) conservé en champ legacy pour compat.
- **TICKET-019 (bug) — une seule ligne `Timeline` par tour.** L'insertion `Timeline` est désormais
  unique et placée après la boucle de state-changes ; un tour de voyage enrichit sa description
  (« Traveled to … (km) ») au lieu d'écrire une 2ᵉ ligne.
- **TICKET-020 (propreté) — scaffolding mort retiré.** Commentaire de brouillon + import `get_current_time`
  inutilisé dans `session.py` (l'import est désormais réellement utilisé), et imports morts
  `ChroniclerWorker`/`ChroniclerEngine`/`EventSourcer` dans `tabletop_view._on_turn_complete`.
- **TICKET-021 (tests) — couverture ajoutée + tests cassés réparés.** Les 6 assertions
  `should_trigger` (TypeError 2-args) repassent vertes via la nouvelle signature ; 2 tests arbitrator
  cassés par le 2ᵉ appel LLM réparés (backend Timekeeper distinct dans les helpers) ; 6 nouveaux tests :
  `TestCausalTime` (elapsed→Timeline, toggle off→pas de 2ᵉ appel, ligne Timeline unique au voyage) et
  3 tests de franchissement de palier du Chronicler. `pytest` installé dans le `.venv`.

**Reste ouvert :** TICKET-017 (`major_event_description` inutilisé ; le time-skip §6.4 est partiellement
couvert par TICKET-018 mais le champ reste non consommé) — voir `PENDING.md`.

---

## Lot 2026-06-09 — Pilier 2 (Universe-as-Code) + correctifs tickets

> Session Claude (branche dev). Détail complet : `maintenance/B2-pilier2-universe-as-code/`.

### TICKET-006 — Chronicler : `chronicler_update` matérialisé
`EventSourcer._apply_event` (+ filtre `update_state_cache`) traite désormais `chronicler_update`
(payload `delta|value`, provenance conservée dans le journal) ; `Session.take_turn` rematérialise
`State_Cache` (+`invalidate_stats_cache`) après le run du Chronicler → ses changements de monde
prennent effet. Avant : events silencieusement ignorés, même au `rebuild_state_cache`.
Tests : `tests/test_ticket_fixes.py`.

### TICKET-023 — `Universe.load` lit `universe_name`
`axiom/universe.py` : `meta.get("universe_name") or meta.get("name") or stem`. Le cache compilé
s'appelant toujours `universe.db`, l'ancien code affichait « universe ». Validé sur `ST_Aglae.db`
(« Aglae »). Tests : `tests/test_ticket_fixes.py`.

### TICKET-024 — `Active_Modifiers` isolé par `save_id`
Colonne `save_id` (DDL + FK `Saves` ON DELETE CASCADE pour DB neuves ;
`migrate_active_modifiers_table` = `ALTER ADD COLUMN` pour DB existantes, branchée
`create_new_save`/`load_saves`). Filtrage par save partout : `modifiers.py`
(`add/tick/apply/_fetch`), `arbitrator._fetch_effective_stats`, `hardcore_worker`. Modifiers
réintégrés à l'éditeur de saves. Avant : buffs/debuffs partagés entre toutes les parties d'un univers.
Tests : `tests/test_ticket_fixes.py`, `tests/test_saves_editing.py`, `test_modifier_processor` adapté.

### TICKET-025 — `save_global_personas` ne dispatchait jamais sa tâche
`workers/db_worker.py::save_global_personas` créait la `QRunnable` et connectait son signal mais
oubliait `self._setup_task(task)` (présent dans toutes les autres méthodes) → personas globales
**jamais sauvegardées** (en jeu comme en test). 1 ligne ajoutée. C'est le vrai bug que
`tests/test_persona_global.py` captait (faussement étiqueté « pré-existant connu » depuis TICKET-001).

### TICKET-001 — Rework tests : **réellement complété** (suite verte)
La 1ʳᵉ passe (2026-05-23) avait documenté 3 groupes d'échecs comme « pré-existants connus » au lieu
de les résoudre. Ils le sont maintenant :
- **persona_global** : vrai bug applicatif corrigé (TICKET-025).
- **ambiance** (5) : `pytest-qt` (déjà dans `requirements-dev.txt`) installé dans le `.venv` ; fixture
  corrigée (`AmbianceManager` est un `QObject`, pas un `QWidget` → suppression du `qtbot.addWidget`) ;
  comparaisons de volume en `pytest.approx` (float32).
- **phase6** (6) : tests périmés réécrits sur de **vrais widgets** (API réelle `_sync_stats_from_ui`/
  `_on_row_selected` au lieu de `_sync_current_form`/`_on_entity_selected`), vérifient le vrai
  comportement anti-perte de données (flush UI→données au changement de ligne / collect).
- **test_llm_base** (2, découvert en chemin) : `parse_tool_call` est devenu résilient (renvoie `None`
  au lieu de lever) ; tests alignés sur ce contrat → cf. **TICKET-026** (choix de design à valider).
Vérification : **31/31 fichiers de tests verts** (lancés par fichier ; le run de toute la suite en un
seul process reste le segfault torch+Qt de TICKET-008, limite de harnais, pas une régression).

### Nettoyage `debug/` (2026-06-09, feu vert utilisateur)
Audit reconfirmé : aucune couverture unique à porter (localisation → `tests/test_localization.py`,
params `Universe_Meta` → `tests/test_universe_meta.py`, déjà migrés en TICKET-001). **Supprimés**
(doublons / tests sur mocks ne touchant pas le vrai code / checks filesystem fragiles) :
`debug/test_translations.py`, `test_db_logic.py`, `test_rules_logic.py`, `test_populate.py`,
`test_populate_async.py`, `test_llm_logic.py`, `test_audio_logic.py`, + `debug/DEPRECATED.md`.
**Conservés** (ce ne sont pas des tests automatisés) : `startup_check.py` (garde-fou du contrat
collab), `run_step7_live.py` (harnais live), `db_integrity.py`, `llm_test.py` et
`test_audio_crossfade.py` (outils interactifs manuels).

### TICKET-032 — `llm_verbosity` stocké localisé (bug i18n)
Le Creator Studio écrivait dans `Universe_Meta` le **texte affiché** du combo de verbosité
(`currentText().lower()` → « équilibré » en FR) au lieu de la valeur canonique
(`short`/`balanced`/`talkative`) — d'où le `WARNING: Localization key missing: 'équilibré'`
au tabletop et une logique de verbosité (max_tokens, guidance du prompt) retombant
silencieusement en défaut dès que l'UI n'était pas en anglais. Corrigé (2026-06-10) :
- combo du Studio : valeur canonique en `itemData`, texte = traduction (`retranslate_ui`
  rafraîchit les libellés sans toucher la donnée) ; écriture via `currentData()` ;
- `axiom.localization.canonical_verbosity()` : **migration douce** des univers déjà
  enregistrés — accepte la valeur canonique ou n'importe quel texte localisé (recherche
  inverse dans toutes les langues), inconnu → `balanced` ;
- lecture normalisée dans le Studio (`findData`) et le tabletop (slider + état session).
Tests : `tests/test_localization.py` (+3, dont valeurs historiques FR/ES/DE), smoke
offscreen Studio + tabletop avec un univers legacy « équilibré ».

## Archivage PENDING → DONE (2026-06-10)

Nettoyage demandé par l'utilisateur : les tickets terminés quittent PENDING (index compris)
et laissent leur trace condensée ici. Les quatre entrées ci-dessous n'existaient pas encore
dans DONE ; les autres tickets retirés de PENDING (001, 006, 015/016/018→021, 023→027, 032,
TC1→TC5…) étaient déjà documentés plus haut. Les mentions « attente feu vert commit » de
l'époque sont caduques : l'utilisateur gère git lui-même.

### TICKET-003 — Suppression des modules engine dépréciés (post-Pilier 1)
**✅ Résolu (2026-06-04).** Conditions remplies (parité fonctionnelle + run réel GUI + 236 tests
verts) ; vérifié par grep que le sous-graphe déprécié n'était référencé que par lui-même.
Supprimés : `core/{arbitrator,chronicler,config,localization,logger,paths,rules_engine,
time_system}.py`, `database/{checkpoint,event_sourcing,modifier_processor,presets,schema}.py`,
tout `llm_engine/`, `workers/db_helpers.py`, + les 3 `DEPRECATED.md`. Conservés (vivants) :
`core/{__init__,st_parser,multiplayer_queue}.py`, `database/{__init__,backup_manager}.py`.

### TICKET-007 — Bugs backend Gemini (extraction_model 404 + >5 stop_sequences)
**✅ Résolu.** Deux bugs pré-existants rendant l'app inutilisable en Gemini-only :
(1) `extraction_model` (nom Ollama local) envoyé à l'API Gemini → 404 ; fix
`axiom/config.py::resolve_extraction_model` (gemini → `gemini_model`), adopté par la décision
héros et les 7 sites Populate. (2) 6 stop sequences envoyées alors que Gemini en plafonne 5 →
400 sur tout tour narratif ; fix `_clamp_stop_sequences` dans `complete()`/`stream_tokens()`.
Tests : `test_config.py::TestResolveExtractionModel`, `test_gemini_client.py` (clamp).
Le « reste » de l'époque (quota 429 free tier) est traité depuis par **TICKET-031**
(retry au délai suggéré + ralentisseur + modèle de secours).

### TICKET-008 — Segfault torch+Qt au premier tour narratif
**✅ Résolu.** Cause racine : le 1er encode sentence-transformers sur un QThread importait
paresseusement `torch._dynamo` → `dlopen(libtriton.so)` depuis un thread secondaire sous Qt
→ crash natif. Fix : `axiom/memory.py::preload_embedding_runtime()` appelé sur le thread
principal au démarrage (`main.py`) — le dlopen a lieu sur le main thread, l'usage cross-thread
ensuite est sûr. Test à dents : `tests/test_vector_threading.py` (+ scénario sous-process Qt
offscreen : `nopreload` → 139, `preload` → 0). L'app a depuis tourné en GUI réelle (validations
Pilier 2, 2026-06-09) sans récidive. Séquelle de harnais connue : la suite pytest monolithique
en un seul process segfaulte toujours (limite torch+Qt, d'où les runs par fichier).

### TICKET-022 — Doc : collision de numérotation des tickets dans DONE.md
**✅ Résolu (2026-06-07).** TICKET-010/011/012 désignaient deux lots sans rapport (Save
Management ET temps causal). Les cinq tickets temps causal ont été renumérotés **TC1 → TC5**
(contenu inchangé), note explicative en tête de DONE.md ; 010/011/012 désignent désormais sans
ambiguïté le lot Save Management.

## TICKET-028/029/030/031 — UX Pilier 2 + résilience quota : validés GUI (2026-06-10)

Implémentés les 2026-06-09/10, **validés en GUI réelle par l'utilisateur le 2026-06-10**.
Détail complet dans les dossiers d'étape (TODO/CHANGELOG/DOC) :
- **TICKET-028** (`maintenance/TICKET-028-gui-saves/`) — panneau de gestion des saves dans le
  Setup : Exporter/Importer `.axiomsave`, Dupliquer (= save manuelle), Renommer, Éditer
  (save_state.toml, diff appliqué en `manual_edit`), Supprimer ; fix latent Delete/Rename
  no-op sur saves séparées ; backups `auto_backups/` en un seul fichier.
- **TICKET-029** (`maintenance/TICKET-029-studio-fichiers/`) — onglet « Fichiers » du Creator
  Studio (arbo TOML/MD éditable, save → `refresh_definition` + reload) ; conversion .db plat
  → univers-dossier (`convert_flat_db_to_folder`, saves embarquées migrées, original en .bak).
- **TICKET-030** (`maintenance/TICKET-030-populate-uac/`) — Populate ciblé + prévisualisation
  du diff texte (sandbox, rien d'écrit avant validation) + canonisation in-game (bouton
  « Canoniser… » avec preview, toggle « Canon auto » OFF par défaut).
- **TICKET-031** (`maintenance/TICKET-031-quota-llm/`) — résilience 429 : retry au délai
  suggéré par l'API, ralentisseur req/min, modèle de secours, Populate commité par chunk
  (relance = reprise). Suite directe : TICKET-033 (visibilité des retries + annulation).

## TICKET-033 — Retries visibles + annulation des générations : validé GUI (2026-06-10)

Implémenté puis **validé en GUI réelle par l'utilisateur le 2026-06-10**. Détail complet
dans `maintenance/TICKET-033-annulation-generation/` (TODO/CHANGELOG/DOC).
- **Compte à rebours des retries 429** dans la barre de statut (« Quota exhausted (model)
  — attempt 1/3 — retry in 27s », rafraîchi ~5 s), bascule sur le modèle de secours annoncée.
- **Bouton « ✖ Annuler la génération »** dans la barre de statut, visible seulement quand
  une génération LLM tourne (registre process-wide dans `workers/db_tasks.py`, poll 500 ms
  côté MainWindow — aucune vue à câbler). Annulation **coopérative** : immédiate pendant
  une attente, sinon à la prochaine frontière de chunk ; le travail déjà commité reste
  (cohérent avec la reprise TICKET-031), une preview annulée supprime sa sandbox.
- Mécanique : `GenerationCancelled` + hooks neutres `on_status`/`cancel_event` sur
  `LLMBackend` (zéro Qt), signal Qt `cancelled` distinct d'`error` (pas de popup).

---

## TICKET-034 → 042 — lot QA du 2026-06-10 : tous corrigés le jour même

Bugs trouvés par la revue qualité des features récentes (Pilier 2 / B3 / B4), corrigés en lot
(étape `maintenance/QA-fixes-034-042/`, détail fichier par fichier dans son CHANGELOG).
Constats d'origine complets : voir l'historique git de `PENDING.md` (ajout puis retrait le
2026-06-10). Aucun changement d'architecture — uniquement des bugs contenus.

- **TICKET-034** — `fork_save` ne copiait ni `Active_Modifiers` ni `Fired_Scheduled_Events`
  (buffs perdus, événements re-déclenchés). → copie ajoutée (modifier_id régénéré) + test.
- **TICKET-035** — `populate_events`/`populate_stats` crashaient en IntegrityError sur
  collision d'id (PK). → skip idempotent (events) / désambiguïsation (stats) + tests.
- **TICKET-036** — `unpack_save` gardait le `Save_Meta` de l'exportateur : save importée
  jamais resynchronisée avec la source locale, canonisation cassée. → Save_Meta re-lié à
  l'univers de destination (`definition_hash` vidé → resync au premier lancement) + test.
- **TICKET-037** — la conversion .db plat → dossier exportait le joueur dans la définition.
  → entités `player` (hors héros compagnon) marquées `origin='runtime'` avant conversion,
  purge runtime partagée avec la sync Studio + test (le joueur survit à la resync).
- **TICKET-038** — `with sqlite3.connect()` ne ferme pas la connexion : unlink sous Windows
  cassé (`delete_save`), fuites de handles. → `closing(...)` sur tout le périmètre récent.
- **TICKET-039** — l'export `.axiom` d'un univers-dossier embarquait saves embarquées,
  sidecars WAL et `.git/`. → exclusions + cache purgé des 8 tables runtime + test.
- **TICKET-040** — « Canoniser… » crashait sur les payloads legacy en chaîne brute.
  → garde `isinstance` dans `_recent_narrative`.
- **TICKET-041** — noms d'entités 100 % non-latins silencieusement sautés (`_safe_id` vide).
  → `entity_id_for()` : fallback déterministe `ent_<sha1[:12]>` (idempotence préservée),
  partagé Populate/canonisation + test.
- **TICKET-042** (mineurs regroupés) — cache mtime sur `load_config` (perf `tr()`) ;
  garde « canonisation déjà en cours » + réutilisation des DbWorker existants (Studio) ;
  annulation couvrant les tâches encore en file (registre à la construction) ; i18n
  (court-circuit populate_tab, contaminations fr/es/de) ; suppression d'univers emporte
  sidecars WAL + dossiers vector des saves ; resync au lancement déportée hors main thread
  (`PrepareSaveTask`/`save_prepared`) ; collisions `_safe_filename` du decompiler
  désambiguïsées ; manifest `.axiomsave` échappé ; sidecars debug orphelins supprimés.
  Non traité (volontaire) : retraduction complète des langues secondaires (contenu, pas un bug).
