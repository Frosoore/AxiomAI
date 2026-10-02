# CHANGELOG — Système de mods

## 2026-09-23
- Discussion de cadrage avec l'utilisateur ; vision validée et formalisée dans `DOC.md` (aucun code).
- Lancement de la critique puis de l'arbitrage par agents.
- Critique rendue (`CRITIQUE.md`) ; arbitrage lancé.
- Arbitrage rendu (`ARBITRAGE.md`) : 36 points retenus (14 pertinents, 22 partiels), 8 écartés, 7 bugs hors-mods confirmés, 9 décisions pour l'utilisateur.

## 2026-09-26
- Décisions utilisateur D-1 → D-9 : toutes les recommandations de l'arbitrage acceptées (D-8 : on garde `axiomai-engine` + bump majeur, à revérifier à la release).
- `DOC.md` réécrit : objectif long terme détaillé (§1), **garde-fous contre les dérives D1→D17** (§2), noyau précisé (step générique + journal générique, `ModContext`, époques, config/migrations, safe mode CLI), manifeste déclaratif, patches par trampolines + secours `__code__`, précisions d'API sur les emplacements (sortie structurée routée, filtre de flux vs final, prompt en sections), politiques de stockage, feuille de route réordonnée (phase 0 « assainir » avant le noyau), registre des décisions.
- `TODO.md` : feuille de route par phases.
- Bugs confirmés ouverts dans `PENDING.md` : TICKET-100 → 105 ; TICKET-089 étendu (`Item_Instances`, `Session_Lore`).
- `ARCHITECTURE.md` : renvoi vers la vision cible.

## 2026-10-03 — Revue de l'implémentation de Frosoore (branche `mods`)
- Revue par 4 agents → `review-2026-10-03/` (synthèse `0-SYNTHESE.md`).
- `ETAT_REEL.md` créé : état réel phase par phase (fait / partiel / mal fait / absent), pourquoi, comment bien faire, ordre des corrections.
- `TODO.md` révisé : cases non prouvées décochées.
- Décisions prises sans le propriétaire annulées : clause de licence retirée de `NOTICE` ; README, guides et `docs/licensing_mods.md` marqués « question ouverte / brouillon » ; `DOC.md` restauré à la version validée (+ ligne d'état), §15/§16 déplacés dans `BILAN_AGENT_FROSOORE_NON_VALIDE.md` ; bandeau « non fiable » sur `SYNTHESE_ARCHITECTURE*.md` et `TODO.en.md`.
- Corrections lancées (lots A tests/CI, C noyau) → `corrections-2026-10/`.
- Lots A et C terminés, B1/B2 arrêtés en cours (budget) ; point d'arrêt et reste à faire : `ETAT_REEL.md` §8. Rien n'est commité.
