# TICKET-072 — Lore Book : recherche sémantique + link expansion

Dernier follow-up du chantier Hindsight. Choix utilisateur (2026-06-19) :
**sémantique + link expansion**, **requête lore dédiée**.

## Problème
`arbitrator._fetch_relevant_lore` lit `Lore_Book` et score par **recouvrement de mots-clés**
(`keywords` + `name`). « trahison » ne ramène pas une entrée qui parle de « complot ». Pas de
synonymes ni de proximité de sens.

## Cible (2 couches)
1. **Sémantique** : vectoriser les entrées `Lore_Book` (chunk_type="lore", turn_id=0 → survit au rewind)
   dans le store par save, idempotent (resync par session / hot reload). Récupération par **requête
   vectorielle hybride dédiée** (filtrée chunk_type="lore", k propre), réutilisant le pipeline Phase 1.
2. **Link expansion** (idée Hindsight `link_expansion_retrieval.py`, adaptée) : depuis les « graines »
   sémantiques, élargir aux entrées **liées** — même `category` ou tokens `keywords` partagés —
   calculé **à la volée** en SQL sur la petite table (pas de graphe kNN pré-calculé, inutile ici).

## Garde-fous
- **Repli mots-clés** conservé quand l'embedding est indisponible (Windows sans torch,
  `VectorMemory._disabled`) ou aucun lore embeddé → l'impl SQL actuelle.
- Forme de retour inchangée pour le prompt builder : `[{category, name, content}]`.
- La requête narrative **exclut** désormais le lore (chunk_type) pour ne pas gaspiller le budget k.
- Coût : +1 requête ANN/tour sur une collection minuscule (justifié, contrairement à la requête morte
  retirée à l'audit du 14/06).

## Règles : pas de superpowers, docs = TODO+CHANGELOG, pas de commit sans feu vert.
