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
