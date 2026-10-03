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

## 2026-10-03 — Revue et Finalisation (branche `mods`)
- Revue par 4 agents → `review-2026-10-03/` (synthèse `0-SYNTHESE.md`).
- `ETAT_REEL.md` créé : état réel phase par phase.
- Lots A (tests hermétiques, CI) et C (noyau, résolveur, cycles, ordre, patches réentrants) validés.
- Lot B (B1 persistance/rewind, B2 isolation du tour, boucle de correction M4 rembobinable) finalisé et vérifié.
- Lot E (découplage UI/Web/Headless, export_engine vérifié sans fuite) finalisé et vérifié.
- Stockage par politiques déclaratives [K9] : table noyau `Mod_KV`, `ctx.store` avec requêtes temporelles/historiques, rewind/fork/cleanup intégrés au registre.
- Modpack dans les saves [K10] : métadonnées `active_modpack` persistées dans `Save_Meta`, packaging dans `.axiomsave`, avertissements de compatibilité au chargement de session.
- Sorties structurées et sections de prompt [M5, M6] : `build_dynamic_tool_call_schema` (omission automatique de l'inventaire si désactivé), gestionnaire d'emplacements flexible (tuples 2..5 éléments, dicts, callables, tri stable par ordre/profondeur).
- Mod de chat minimal [M3] : création de `axiom.minimal_chat` (`provides = ["turn_pipeline"]`, pipeline textuel pur sans JDR), découplage des interfaces (`axiom.ui.qt`, `axiom.ui.web`, `axiom.cli`) pour dépendre du provider virtuel `turn_pipeline`.
- Points `@patchable` dans le moteur [P2] : décoration de `axiom.prompts:build_narrative_prompt`, `build_timekeeper_prompt`, `axiom.regenerate:regenerate_variant`, `axiom.db_helpers:get_spatial_context`, `get_time_of_day_context`.
- Documentation canonique [DOC2] : modèle canonique `main.py` aligné sur des cibles réelles dans `README.md`, `docs/guides/mods.md`, `maintenance/Mods/SYNTHESE_ARCHITECTURE.md` ; test d'acceptation `tests/test_canonical_mod_example.py` 100% passant.
- TICKET-104 : `regenerate.py` stripping de fenced JSON et suppression de consigne de tool-call en régénération.
