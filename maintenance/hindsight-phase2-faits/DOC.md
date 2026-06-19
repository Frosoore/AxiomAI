# Phase 2 — Infra deux modes + extraction de faits (Mode Vivant, étage 1)

Étape de code du chantier **Hindsight Mining** (cf. `../hindsight-mining/DOC.md`). Objectif : introduire
le **toggle deux modes** (Léger / Vivant) et, en mode Vivant, **extraire des faits structurés** du
narratif par LLM, en **tâche de fond** (jamais bloquant), indexés par `turn_id` (rollback trivial).

## Architecture deux modes
- `axiom/config.py::memory_mode: "lite" | "living"` (défaut **`lite`** — décidé 2026-06-18).
- **`lite`** : aucun appel LLM côté mémoire (extraction court-circuitée). La recherche hybride de la
  Phase 1 tourne dans les deux modes.
- **`living`** : après chaque tour, le narratif est envoyé à un LLM (notre `LLMBackend`) qui en extrait
  des **faits** (who/what/when/where/why + `fact_type` + entités), stockés en SQLite, indexés `turn_id`.

## Modèle de fait (adapté de Hindsight, schéma allégé sans causal pour l'instant)
Table `Facts` (même DB qu'`Event_Log`/`State_Cache`, clé `save_id`+`turn_id`) :
`fact_id, save_id, turn_id, fact_type, who, what, fact_when, fact_where, why, entities(JSON), statement`.
- `fact_type` : `world` (sur le monde) | `experience` (vécu du joueur) | `assistant` (dit/narré).
- `statement` : la phrase canonique du fait (sert au rappel / futur embedding).
- **Causal différé** : les `CausalRelation` de Hindsight (synergie Pilier 5) sont **hors Phase 2**
  (colonne ajoutable plus tard via `ALTER TABLE`). Voir DOC chantier §B-1.

## Items
1. **Toggle `memory_mode`** (config) + court-circuit `lite`. [GUI + i18n : sous-item, panneau « Mémoire »
   qui exposera aussi le cross-encoder de la Phase 1.]
2. **Table `Facts` + couche stockage** (`axiom/facts.py`) + **rollback** (dans `CheckpointManager.rewind`)
   — déterministe, **zéro LLM**, entièrement testable.
3. **Extraction LLM** (`axiom/factextract.py`) : prompt adapté de Hindsight branché sur `LLMBackend`,
   sortie JSON → `list[Fact]`. Tests via `LLMBackend` mocké.
4. **Job de fond** (`workers/`) : lance l'extraction hors du tour (modèle `vector_worker.py`).
5. **Arme « faits »** dans la recherche : les faits du tour enrichissent le rappel.

## Invariants (re-testés à chaque item)
Rollback par `turn_id` (faits inclus) · `lite` 100 % offline/déterministe · `living` testé via LLM mocké ·
dégradation gracieuse (LLM indispo → pas de faits, jamais de crash) · moteur léger (SQLite, pas de Postgres).

## Décisions encore à confirmer avec l'utilisateur (avant les items LLM 3-4)
- **Cadence d'extraction** : chaque tour / tous les N tours / à la demande (coût LLM).
- **Clé LLM** : réutiliser le backend texte déjà configuré (défaut) vs clé dédiée.
- Schéma causal maintenant ou plus tard (défaut : plus tard).
</content>
