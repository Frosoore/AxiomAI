# Phase 3 — Croyances / consolidation (Mode Vivant, étage 2)

> Étape de code du chantier Hindsight Mining. Cible : faire émerger, par-dessus les **faits**
> (Phase 2), des **croyances qui évoluent** (observations à la Hindsight) — un PNJ se souvient
> d'une trahison 200 tours plus tard et révise son opinion. **Strictement turn-keyed** (le rapport
> temps causal du 2026-06-18 a confirmé que `turn_id` est l'axe sûr du rewind ; on n'effleure pas les
> sous-systèmes en minutes — Active_Modifiers/Scheduled_Events, cf. TICKET-074/075).

## Garde-fous (rappel cahier des charges)
- **Mode Léger inchangé** : zéro LLM, zéro réseau. Les croyances ne vivent qu'en `living`.
- **Rollback d'abord** (§8 du DOC de reconnaissance) : `created_turn_id > N` → suppression ;
  sinon on filtre les sources `turn_id ≤ N`, recompute `proof_count`, marque `stale`. Test
  d'acceptation = « croyances sur 20 tours, rewind au 10, ne reflètent que ≤ 10 ».
- **Déterminisme des tests** : le consolidateur LLM est testé via `LLMBackend` mocké.
- **Dégradation gracieuse** : LLM HS → aucune croyance créée, le jeu continue.

## Modèle de données (`Observations`)
Une observation = une croyance synthétique. Colonnes clés :
- `subject` : l'entité concernée/porteuse ('' = monde).
- `statement` : la croyance canonique (1 phrase).
- `proof_count` : nb de faits qui la soutiennent (cache de `len(sources)`).
- `sources` : JSON `[{"fact_id","turn_id"}]` — **la clé de rollback** (`source_memory_ids` de Hindsight).
- `history` : JSON des changements (CREATE/UPDATE/DELETE) dans le temps.
- `created_turn_id` / `updated_turn_id`, `stale`.

## Plan d'items
1. **Table + stockage + rollback (déterministe, zéro LLM)** — `axiom/observations.py`, schema, intégration
   `checkpoint.rewind`, config `memory_beliefs_enabled`. Test d'acceptation rollback.
2. **Consolidateur LLM** (`axiom/consolidate.py`) — CREATE/UPDATE/DELETE sur un lot de faits récents,
   prompt adapté de `consolidation/prompts.py` (pas d'arithmétique, une facette/observation, conservatisme
   DELETE), via `LLMBackend`. Job de fond app-layer (suite du worker faits).
3. **Recherche** — `proof_count_boost` (Phase 1 §7.3, neutre en Léger) + injection des croyances en tête de
   contexte Arbitrator (hiérarchie observations → faits).
4. **(option) Modèles mentaux** — fiche perso/monde résumée (Phase 4 plutôt).

## Refs
- Reconnaissance : `maintenance/hindsight-mining/DOC.md` §4.2, §7.7, §8, §9 (Phase 3).
- Phase 2 (faits) : `maintenance/hindsight-phase2-faits/` (patron facts.py/factextract.py).
- Rapport temps causal (turn vs minutes) : investigation 2026-06-18 (chat) → TICKET-074/075/076.
