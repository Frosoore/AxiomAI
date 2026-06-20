# TODO — Hindsight Mining

> Étape de **préparation/reconnaissance** (no code). Voir `DOC.md` pour le détail technique, les ancres
> `fichier:ligne`, l'architecture cible deux modes et le plan par phases.

## Fait (reconnaissance + cible, 2026-06-17)
- [x] Cartographier la mémoire actuelle d'Axiom (vecteur + structuré) et ses points d'intégration.
- [x] Cartographier le code serveur de Hindsight (`engine/`) : recherche + cognition.
- [x] Comprendre le modèle de connaissance à 3 niveaux (faits → observations → modèles mentaux + directives).
- [x] Lire les algos clés (fusion RRF, scoring multiplicatif modulé, fallback passthrough, boosts) et les
  **prompts** (consolidation CREATE/UPDATE/DELETE, extraction de faits who/what/when/where/why + causal).
- [x] Catalogue d'extraction technique par module (DOC §7) avec verdict + cible + impact + mode.
- [x] Concevoir l'**architecture cible deux modes** (Léger sans LLM / Vivant avec LLM) — validée par leurs
  flags `ENABLE_OBSERVATIONS`/`ENABLE_AUTO_CONSOLIDATION`/`llm_provider="none"` (DOC §6).
- [x] **Résoudre le rollback des croyances** : mécanisme `source_memory_ids` + `_filter_live_source_memories`
  + recalcul (DOC §8).
- [x] Repérer la synergie Pilier 5 (relations causales entre faits, DOC §4.1).
- [x] Statuer sur le filtre lore : vraie casse déjà corrigée (audit 2026-06-14, B1) ; reste expression morte.

## Questions résiduelles à confirmer en chemin (DOC §11)
- [ ] Lib lexicale `rank_bm25` vs maison ? Cross-encoder : modèle + activé par défaut ou opt-in ?
- [ ] Mode par défaut à l'install (Léger recommandé) + proposer Vivant à l'onboarding ?
- [ ] Granularité « mission » des croyances : par univers / par perso / les deux ?
- [ ] Fréquence du job de consolidation (chaque tour / tous les N / à la demande) ?
- [ ] Clés partagées vs clé perso de l'utilisateur pour le Mode Vivant (coût) ?

## Phase 1 — couche recherche (Mode Léger, sans LLM) — quand feu vert
- [ ] Refondre scoring `memory.py:query` (multiplicatif modulé + récence en `turn_id` + passthrough).
- [ ] Nettoyer le filtre mort résiduel (§5.2).
- [ ] Arme lexicale (`rank_bm25`) + fusion RRF (`axiom/retrieval/`).
- [ ] Cross-encoder optionnel + fallback Windows.
- [ ] (option) boosts de stratégie (lieu/perso en scène).
- [ ] Vérifs : rollback intact · tests déterministes verts · gain qualitatif en jeu réel.

## Phase 2 — infra deux modes + extraction de faits (Mode Vivant étage 1)
- [ ] Toggle `memory_mode` (config + GUI + i18n) + court-circuit LLM en `lite`.
- [ ] Table `Facts` + extraction LLM en job de fond, indexée `turn_id`.
- [ ] Étendre `rollback` aux faits ; tests via `LLMBackend` mocké.
- [ ] Brancher l'arme « faits » dans la recherche.

## Phase 3 — croyances / consolidation (Mode Vivant étage 2) — l'objectif « cool »
- [ ] **D'abord** : étendre `rollback` aux observations (§8) + test d'acceptation (rewind cohérent).
- [ ] Table `Observations` + consolidateur (job de fond), mission par perso/univers.
- [ ] Activer `proof_count_boost` ; hiérarchie de rappel observations → faits.
- [ ] (option) modèles mentaux : fiche perso/monde résumée réinjectée.

## Phase 4 — raffinements
- [ ] Directives/persona, extraction temporelle (turn_id), prompt caching Gemini (coût), modèles mentaux avancés.
