# TODO — QA Hindsight (correctifs)

Contrôle qualité du chantier Hindsight (recherche + faits + croyances + lore).
Findings consignés dans `PENDING.md` (TICKET-077→082).

## Correctifs (cette étape)
- [x] **TICKET-080** — `insert_facts` stampe `fact_id`/`turn_id` en place ; `fact_worker` n'aligne plus par `zip`.
- [x] **TICKET-079** — `get_facts`/`get_observations` : `LIMIT` SQL quand pas de filtre ; arbitrator charge une fois, priorise en mémoire.
- [x] **TICKET-077** — `consolidate(..., max_existing=N)` : croyances scopées (sujets du batch + récentes), plafonné.
- [x] **TICKET-078** — cache d'index BM25 par signature de corpus (invalidé par empreinte d'ids).

## Feature suivie (demandée ensuite)
- [x] **TICKET-081** — `Trend` déterministe sur croyances (moteur `compute_trend` + injection prompt).
- [x] **TICKET-081 GUI** — `ui/memory_browser.py` (onglets Croyances+trend / Faits), bouton dans les
      réglages, i18n ×10, tests. doc_check + i18n_check OK.
- [x] **Doc Sphinx moteur** (EN + FR, hors API auto) — guide mémoire : Belief trends + cache BM25 +
      scoping consolidation ; FR via gettext (.po traduit, .mo recompilés).

## Hors périmètre (laissés ouverts dans PENDING)
- TICKET-082 (modèles mentaux / directives / temporel).

## Validation
- [x] suite ciblée verte : **192 passed** (consolidate, factextract, facts, observations, retrieval,
      missions, lore, fact_worker, vector_memory, arbitrator, checkpoint) — feature Trend incluse.
- [ ] suite complète (selon dispo, segfault Qt connu = TICKET-067)
