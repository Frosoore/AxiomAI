# Hindsight follow-ups — TICKET-073 / 074 / 075 / 076

Cluster de tickets issus du chantier Hindsight (Phases 1→4, commit `2965279`). Objectif :
clore proprement les aspérités repérées en chemin. Périmètre validé par l'utilisateur le 2026-06-19.

## TICKET-073 — Focus boost : noms des persos en scène
**But.** La recherche mémoire (`VectorMemory.query`) accepte des `focus_terms` qui donnent un petit
bonus additif (+0.2) aux souvenirs mentionnant la scène courante. Aujourd'hui seul le **lieu** du
joueur est passé (câblé en Phase 1). On ajoute les **noms des personnages présents** dans la même
scène, pour que les souvenirs parlant d'eux remontent.

**Contrainte.** La map `id→nom` des entités était construite *après* la requête RAG dans
`arbitrator.process_turn`. Solution = **réordonnancement maîtrisé** : remonter la lecture
noms/types + persona (une seule connexion, pas de round-trip ajouté) avant la requête, et construire
`focus_terms = [lieu] + noms des entités partageant le lieu` (lu depuis `all_stats`, borné).

## TICKET-074 — Rewind n'annule pas les `Active_Modifiers`
**But.** `checkpoint.rewind` purge par `turn_id > N`, mais `Active_Modifiers` est clé par
`minutes_remaining` (pas de `turn_id`) → les buffs/débuffs ne reviennent pas à l'état du tour N.

## TICKET-075 — Rewind ne « dé-tire » pas les `Fired_Scheduled_Events`
**But.** Table clé `(save_id, event_id)`, jamais purgée au rewind → un événement programmé tiré
reste marqué tiré même après rembobinage en deçà de sa minute.

## TICKET-076 — Résidu legacy `config.chronicler_interval`
**But.** Champ mort (en tours) depuis TICKET-018 (déclenchement passé en minutes via
`chronicler_minutes_interval`). À retirer ou documenter après grep confirmant que rien ne le lit.

## Règles
- Pas de superpowers, docs = TODO+CHANGELOG, pas de commit sans feu vert, ne rien supprimer (tests)
  sans accord. Vérifier chaque réf `fichier:ligne` par grep avant de coder.
