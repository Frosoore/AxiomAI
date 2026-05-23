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
