# CHANGELOG — Hindsight Mining

## 2026-06-17 — Reconnaissance & handoff (no code)
- Investigation du système de mémoire d'Axiom (vecteur `axiom/memory.py` + structuré SQLite) et de
  ses points d'intégration (arbitrator/session/config/schema).
- Exploration du clone Hindsight (`/home/garen/coding/hindsight/`, MIT, commit `55f70e1d`) ; lecture
  ciblée du dossier `engine/` (search/fusion, search/reranking, search/recall_boost, retrieval,
  temporal_extraction ; survol retain/consolidation/reflect/entity_resolver/providers).
- Rédaction de `DOC.md` : objectifs/ambitions, contraintes non négociables, catalogue d'extraction
  technique par module (transférabilité + cible Axiom + impact rollback/LLM/déterminisme), plan par
  phases, problème rollback × mémoire dérivée, méthode pour l'agent suivant, index des fichiers à lire.
- `TODO.md` : décisions en attente + checklist Phase 1.

## 2026-06-17 (bis) — Cadrage utilisateur & refonte ambitieuse de la doc
- Cadrage tranché par l'utilisateur : viser **le meilleur système possible** (recherche + faits +
  croyances tous prioritaires), **dépendances autorisées**, **deux modes togglables** (Léger sans LLM /
  Vivant avec LLM).
- Exploration approfondie de la **couche cognitive** de Hindsight : extraction de faits
  (who/what/when/where/why + `fact_type` + entités + **relations causales** → synergie Pilier 5),
  consolidation (prompt CREATE/UPDATE/DELETE, `proof_count`, `source_memory_ids`, `history`, dédup +
  adjudication LLM, **mission personnalisable par banque**), hiérarchie reflect (modèles mentaux →
  observations → faits), directives, flags de config (`ENABLE_OBSERVATIONS`, `ENABLE_AUTO_CONSOLIDATION`,
  `llm_provider="none"`).
- **Découverte structurante** : Hindsight se dégrade nativement sans LLM (`llm_provider="none"`) →
  valide architecturalement le **toggle deux modes** (Léger = couche recherche ; Vivant = + cognition).
- **Rollback des croyances résolu** sur le papier via `source_memory_ids` + `_filter_live_source_memories`
  + recalcul paresseux (DOC §8) — c'est le critère d'acceptation de la Phase 3.
- `DOC.md` réécrit en version ambitieuse : modèle de connaissance pédagogique (§4), architecture cible
  deux modes (§6), catalogue scindé recherche/cognition (§7), section rollback dédiée (§8), plan en 4
  phases (§9). `TODO.md` aligné. **Toujours aucune modification de code.**
- **Ancres précisées** : §12 transformé en **table d'ancres `fichier:ligne`** (relevées par grep,
  commit `55f70e1d`) vers chaque code exemple — recherche (fusion/scoring/passthrough/boosts/CE),
  cognition (schéma de faits + causal, prompt d'extraction, **prompt de consolidation**, `_dedup_adjudicate`,
  `_filter_live_source_memories`, reflect, directives), données/infra (modèle alembic, flags de mode,
  providers), et points d'intégration côté Axiom. Avertissement explicite : revérifier par grep (amont mouvant).
- **Aucune modification de code.** Filtre lore inopérant (`arbitrator.py:229` / `session.py:661`)
  revérifié : la vraie casse était **déjà corrigée** par l'audit moteur du 2026-06-14 (B1, lore en SQL
  direct) ; il ne subsiste qu'une expression morte inoffensive sur les chunks vectoriels, à nettoyer
  lors du refactor de scoring (Phase 1).
