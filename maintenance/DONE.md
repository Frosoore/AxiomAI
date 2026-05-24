# DONE — tickets clos

Récapitulatifs des tickets traités. Les tickets restent numérotés dans
`PENDING.md` (liste des tickets ouverts) pour préserver la numérotation.

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
