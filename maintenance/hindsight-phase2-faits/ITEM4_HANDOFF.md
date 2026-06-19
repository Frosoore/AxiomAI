# Item 4 — Handoff (couche APP : job de fond + GUI + i18n)

> Phase 2, dernier item. **Tout le moteur est prêt** (items 1,2,3,5 faits). Il ne reste que la plomberie
> app-layer pour que le Mode Vivant *tourne en jeu*. Cette page dit **quoi lire, quoi faire, quelles
> décisions sont déjà prises**. Aucune décision moteur ne manque.

## En une phrase
En mode `living`, après chaque tour, un **worker QThread** distille le narratif en faits (via l'API
moteur déjà écrite) **tous les N tours**, avec un **bouton « extraire maintenant »** ; et un **panneau
GUI « Mémoire »** expose les réglages (+ les 10 traductions).

## API moteur déjà disponible (rien à réécrire)
- `axiom.factextract.extract_facts(llm, narrative_text, *, known_entities=None, when_hint=None, max_facts=8) -> list[Fact]`
  — dégradation gracieuse (LLM HS → `[]`), jamais bloquant. **C'est l'appel coûteux → à faire dans le thread du worker.**
- `axiom.facts.insert_facts(db_path, save_id, turn_id, facts) -> list[int]` — persiste les faits du tour.
- `axiom.facts.get_facts / count_facts / rollback_facts` — lecture / purge (`rollback_facts` supprime
  `turn_id > target` ; déjà appelé par `checkpoint.rewind`).
- `axiom.config` : `memory_mode` (`lite`/`living`), `memory_mode_is_living(cfg)`, `memory_fact_interval`
  (N, 0 = manuel seul), `memory_fact_model` (override, vide = backend principal),
  `memory_reranker_enabled` (cross-encoder Phase 1, à exposer aussi).
- `axiom.config.build_llm_from_config(cfg, model_override=...)` — construire le LLM d'extraction
  (override = `memory_fact_model` s'il est non vide, sinon `None`).

## Décisions déjà prises (ne pas re-trancher)
- Défaut = **`lite`** (offline, déterministe). Mode **par save**.
- Extraction **tous les N tours**, N **réglable et désactivable** (`memory_fact_interval`, 0 = off).
- **Bouton « extraire maintenant »** → lance l'extraction immédiatement **et réinitialise le compteur N**.
- Modèle = **backend configuré** par défaut, surchargeable (`memory_fact_model`).
- **Causal différé** (hors Phase 2).

## Quoi lire (fichiers + points d'accroche)
1. **Worker à copier** : `workers/vector_worker.py` (`VectorEmbedWorker`, l.90+) — même patron QThread
   (signals `*_complete`/`error_occurred`/`status_update`, `run()` qui appelle le moteur hors thread UI).
   → créer `workers/fact_worker.py::FactExtractWorker` qui, dans `run()`, fait
   `extract_facts(...)` puis `insert_facts(...)`.
2. **Point de déclenchement post-tour** : `ui/tabletop_view.py:594` `turn_complete.connect(self._on_turn_complete)`
   et `_on_turn_complete` (l.608). C'est **exactement** là qu'est déjà branché l'embedding vectoriel du
   tour → brancher l'extraction de faits au même endroit, **gardée par `memory_mode_is_living(cfg)`** et
   par le compteur N. Le narratif du tour = `result` (ArbitratorResult) / `narrative_text`.
3. **Compteur N** : le plus simple = un compteur d'instance dans `tabletop_view` (incrémenté à chaque
   `_on_turn_complete`, déclenche quand `>= memory_fact_interval`, remis à 0 au déclenchement **et** au
   clic du bouton manuel). Pas besoin de le persister (au pire on ré-extrait un tour, idempotent si on
   purge le tour avant — voir « à prévoir »).
4. **Panneau GUI** : `ui/settings_dialog.py` (patron d'onglet : `addTab(widget, tr("tab_…"))`, champs
   `QComboBox`/`QSpinBox`/`QCheckBox`, sauvegarde via `setattr` sur le `cfg`). Ajouter un onglet/section
   **« Mémoire »** :
   - menu déroulant **Mode** (Léger/Vivant) → `cfg.memory_mode`,
   - **N** (`QSpinBox`, 0 = désactivé, `setSpecialValueText`) → `cfg.memory_fact_interval`,
   - **Modèle d'extraction** (champ texte, vide = défaut) → `cfg.memory_fact_model`,
   - **Reranking neuronal** (`QCheckBox`, Phase 1) → `cfg.memory_reranker_enabled`,
   - **bouton « extraire maintenant »** (déclenche le worker, reset N).
5. **i18n** : `core/localization.py::tr` + `core/locales/<lang>.toml` (10 langues : de/en/es/fr/it/ja/ko/pt/ru/zh).
   Ajouter les clés `tab_memory`, `memory_mode`, `memory_mode_lite`, `memory_mode_living`,
   `memory_fact_interval`, `memory_fact_model`, `memory_reranker`, `extract_now`, … **dans les 10 .toml**
   (EN d'abord), puis `python tools/i18n_check.py` pour vérifier la couverture. (Cf. patron `tab_cloud`,
   ajouté récemment dans `feature-cloud-text-providers`.)
6. **Doc intégrée** (optionnel mais cohérent) : `ui/help_system.py` (registre `PAGES`) + clés `doc_*`
   pour les nouveaux réglages (cf. chantier TICKET-057).

## À prévoir / petites décisions de la prochaine passe
- **Batch vs dernier tour** : extraire **le narratif des N derniers tours** (les events `narrative_text`
  du `Event_Log`, cf. `workers/db_tasks.py:231`) pour ne pas « sauter » de tours entre deux extractions,
  plutôt que le seul dernier tour. Recommandé : passer à `extract_facts` le narratif concaténé des tours
  depuis la dernière extraction, et `insert_facts(..., turn_id=<tour courant>)`.
- **Ré-extraction idempotente** : si on veut pouvoir relancer un même tour, ajouter un petit
  `facts.delete_turn_facts(db_path, save_id, turn_id)` (purge `turn_id == n`) avant `insert_facts`.
  Aujourd'hui seul `rollback_facts` (`> target`) existe. **Helper moteur trivial à ajouter** si besoin.
- **Statut UI** : afficher discrètement « mémoire : N faits » ou un témoin pendant l'extraction (les
  signals du worker s'y prêtent).
- **Tests app** : worker mocké (LLM mock comme `tests/test_factextract.py::_FakeLLM`) ; vérifier que `lite`
  ne déclenche jamais le worker.

## Garde-fous (rappels du cahier des charges)
- `lite` = **zéro réseau, déterministe** → le worker ne doit **jamais** démarrer en `lite`.
- LLM HS / pas de clé → `extract_facts` rend `[]` (déjà géré) : aucune popup d'erreur, le jeu continue.
- Le worker tourne **hors du thread UI** (QThread) et **après** le tour (non bloquant).
</content>
