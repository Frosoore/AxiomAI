# CHANGELOG — QA Hindsight

## 2026-06-19 (2ᵉ passe) — Re-revue + correctif #1 + nouveaux findings

Seconde passe de contrôle qualité du chantier Hindsight. **Verdict reconfirmé : aucun bug bloquant.**
- **Corrigé** : `axiom/observations.py::compute_trend` — variable morte `old_cutoff` (calculée, jamais
  utilisée ; la fenêtre « ancienne » n'a en fait pas de borne basse). Retrait + commentaires rendus
  honnêtes sur la normalisation des bandes. Comportement inchangé (`old_turns` toujours utilisé pour la
  période de densité), `test_observations.py` 18 verts.
- **Loggés en PENDING** (non corrigés) : TICKET-083 (fuite temporelle `created_turn_id` au rewind),
  TICKET-084 (budget prompt living = 3× `rag_chunk_count`), TICKET-085 (`collection.get()` plein corpus
  au cache-hit BM25). #4 (lecture plein-table par tour dans `_fetch_relevant_facts/_beliefs`) **non
  loggé** : déjà connu/assumé par TICKET-079.

## 2026-06-19 — Audit qualité + correctifs (TICKET-077→080) + feature Trend (081)

Contrôle qualité du chantier Hindsight (recherche hybride + faits + croyances + lore).
**Verdict : code de très haute qualité, aucun bug de correction franc.** Les findings sont des
problèmes de coût/scaling du mode « living » sur longues parties + robustesse. 6 findings consignés
dans `PENDING.md` (077→082) ; les 4 actionnables corrigés ici.

### TICKET-080 — Alignement fiable fait↔id (robustesse)
- `axiom/facts.py::insert_facts` renseigne désormais `fact_id`/`turn_id` **sur place** sur chaque `Fact`
  réellement inséré (les sautés/vides gardent `fact_id=None`). Retour `list[int]` inchangé.
- `workers/fact_worker.py` n'a plus à reconstruire l'alignement par `zip(facts, new_ids)` (couplage
  fragile supprimé) : il filtre `[f for f in facts if f.fact_id is not None]`.

### TICKET-077 — Prompt de consolidation borné
- `axiom/consolidate.py::_scope_existing` : les croyances montrées au LLM sont scopées aux **sujets
  cités par le batch de faits** puis complétées par les **plus récentes**, plafonnées à
  `max_existing` (défaut 24). Param `consolidate(..., max_existing=...)`. Sur longue campagne le prompt
  ne grossit plus en O(total croyances). Le filtre `known_obs` final reste sur l'ensemble complet
  (un update/delete peut viser n'importe quelle croyance existante).

### TICKET-079 — Lectures plein-table réduites
- `axiom/facts.py::get_facts` + `axiom/observations.py::get_observations` : `LIMIT` poussé en **SQL**
  quand il n'y a pas de filtre entité/sujet (plus de matérialisation complète pour slicer).
- `axiom/arbitrator.py::_fetch_relevant_facts/_fetch_relevant_beliefs` : **une seule** lecture
  (bornée `max_turn_id`) puis priorisation on-scene→récents **en mémoire**, au lieu d'une requête
  plein-table par perso en scène (M+1 → 1).

### TICKET-078 — Cache d'index BM25
- `axiom/retrieval/lexical.py` : `build_bm25()` / `rank_with_bm25()` séparés (construction vs scoring) ;
  `rank_by_bm25()` conservé comme wrapper.
- `axiom/memory.py::query` : cache d'index BM25 par signature de `where_cond`, invalidé par
  l'**empreinte d'ids du corpus** (sûr : tout changement de contenu = nouvel uuid de chunk). Le corpus
  lore (figé après sync) ne reconstruit plus son index à chaque tour ; le corpus narratif (qui grossit)
  reconstruit correctement. Ids alignés mis en cache (l'ordre de `get()` n'est pas garanti stable).
  Garde-fou de taille (clear au-delà de 8 entrées).

### Tests
- `tests/test_consolidate.py` : `_scope_existing` (no-op dans le budget, désactivé à 0, priorité
  sujets→récents) + `consolidate` ne montre que les croyances scopées (capture du prompt).
- `tests/test_facts.py` : `insert_facts` stampe `fact_id`/`turn_id` en place.
- `tests/test_vector_memory.py::TestBM25Cache` : réutilisation sur corpus stable (1 build pour 2
  requêtes) + reconstruction quand le corpus change.
- Périmètre touché vert : **192 passed** (consolidate, factextract, facts, observations, retrieval,
  missions, lore, fact_worker, vector_memory, arbitrator, checkpoint) — inclut la feature Trend (081).

### TICKET-081 — Feature : Trend déterministe sur les croyances
- `axiom/observations.py` : `compute_trend(source_turns, now_turn)` + constantes `TREND_STABLE/
  STRENGTHENING/WEAKENING/NEW/STALE` + méthode `Observation.trend(now_turn)`. Algorithme adapté de
  Hindsight (`reflect/observations.py`) : densité de preuves récentes vs anciennes, transposé de l'axe
  jours → **axe `turn_id`** (fenêtres 15/45 tours, ratio 1:3 ; correct au rewind car turn-keyed).
  **Zéro coût LLM, calcul à la volée, aucun changement de schéma.**
- `axiom/arbitrator.py::_fetch_relevant_beliefs` : annote les croyances au **signal directionnel**
  (`strengthening`/`weakening`/`stale` → « statement (trend) ») ; `new`/`stable` laissées nues (prompt
  léger). Dédup toujours sur le `statement` brut.
- Tests : `tests/test_observations.py::TestComputeTrend` (5 cas : stable/new/stale/strengthening/
  weakening + méthode) + `TestArbitratorBeliefInjection::test_annotates_directional_trend`.

### TICKET-081 (suite) — Vue GUI « Explorer la mémoire »
- `ui/memory_browser.py` : `MemoryBrowserDialog` en **lecture seule** — deux onglets **Croyances**
  (Sujet / Croyance / Tendance colorée / Preuves / Tour) et **Faits** (Tour / Type / Fait / Entités),
  bornés au tour courant ; messages « rien encore » / « charger une partie » en dégradé. Tendance via
  `Observation.trend(now_turn)`.
- Câblage : bouton « Explorer la mémoire… » dans l'onglet Mémoire des réglages (`settings_dialog.py`,
  signal `view_memory_requested`) → `main_window` → `tabletop_view.open_memory_browser()` (a
  `save_id`/`turn_id`). Élément documenté ajouté au registre `ui/help_system.py`.
- **Gating corrigé (retour user)** : la mémoire est **par save**, pas par univers. Le bouton n'est activé
  que lorsqu'une **vraie partie est en cours** (page tabletop + `save_id` actif), via le paramètre
  `SettingsDialog(can_browse_memory=…)` calculé dans `main_window._show_settings`. Avant, il s'activait
  sur le seul `db_path` (univers) → dans le Creator Studio / Hub il aurait ouvert la **dernière partie
  jouée** (mauvais contexte ; jamais de fuite de données — tout est filtré par `save_id`, mais contexte
  trompeur). Le dialog garde son garde-fou « charger une partie » si `db_path`/`save_id` vides. +1 test.
- i18n : **24 clés × 10 langues** (`memory_browser_*`, `trend_*`, doc du bouton). `i18n_check` OK (725
  clés), `doc_check` OK (285 clés).
- Tests : `tests/test_memory_browser.py` (no-session, croyances+trend+faits, libellé monde). GUI vert.

### Doc Sphinx du moteur (EN + FR, hors notes d'API auto)
- `docs/guides/memory.md` (EN) : nouvelle section **Belief trends** (`compute_trend`/`Observation.trend`,
  les 5 valeurs, annotation des tendances directionnelles dans le prompt) ; + mention du **cache d'index
  BM25** (search layer) et du **scoping de consolidation** (`max_existing`).
- Traduction **FR** via gettext : `docs/locales/fr/LC_MESSAGES/guides/memory.po` régénéré
  (`sphinx-build -b gettext` + `sphinx-intl update`), nouvelles entrées traduites (0 entrée de contenu non
  traduite), `.mo` recompilés (gitignorés). **Notes d'API non touchées** (auto-générées, EN).

### Laissé ouvert (PENDING)
- TICKET-082 (modèles mentaux §7.8 / directives §7.9 / extraction temporelle §7.5 — gros périmètre).

⚠ **Non commité** — attente feu vert utilisateur.
