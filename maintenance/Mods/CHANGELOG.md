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

## 2026-10-16 — Audit Code-First Sans Pitié et Corrections Massives Réalisées
- **Audit approfondi** : confrontation sans pitié du code aux affirmations de `ETAT_REEL.md`, `TODO.md` et `PENDING.md`. Identification de faux positifs, tests sur tables vides, failles d'étanchéité et code mort.
- **Chantier 1 (Web)** :
  - Désindentation du corps des méthodes `_handle_memory_fact_mutation`, `_handle_memory_belief_mutation`, `_handle_memory_model_mutation` dans `main_web.py:356-495` qui étaient piégées dans `except ImportError:` après `return` (TICKET-121).
  - Correction de `/api/session/inventory/move` dans `main_web.py` pour supporter `dest_holder_kind` / `dest_holder_id` envoyés par `web/app.js` (TICKET-122).
  - Ajout du endpoint `POST /api/mods/toggle` dans `main_web.py` pour le pilotage des mods depuis l'interface Web.
  - Suite `test_web_server.py` 100% passante (50/50).
- **Chantier 2 (Résilience Qt & TICKET-117/107)** :
  - Création de `mods/axiom.ui.qt/ui/help_bridge.py` avec pont gracieusement dégradé et élimination des 27 imports directs et non protégés de `help_system` dans l'interface Qt (TICKET-117).
  - Ajout d'un repli par défaut `default=` sur `tr()` dans `tabletop_view.py` et ajout de la clé `no_narrative_to_illustrate` dans les 10 fichiers de locales (`core/locales/*.toml`).
  - Remplacement de `bootstrap_all_mods()` par `get_kernel_registry()` dans `main_window.py`.
- **Chantier 3 (Noyau, Résolveur & Repli)** :
  - Correction de la désactivation en cascade dans `LoadState.disable` (`axiom/kernel/loader.py`) : propagation de `STATE_NEXT_LAUNCH` pour les dépendants d'un mod non désactivable à chaud (au lieu d'un déchargement à chaud illégal).
  - Promotion automatique et transparente de `axiom.minimal_chat` dans `bootstrap_all_mods` si `axiom.turn` ou le pipeline principal échoue lors de `init()`.
  - Respect de l'ordre utilisateur `mod_order` pour les emplacements exclusifs (`compute_exclusive_conflicts`) et les patches.
  - Vérification de version sur les dépendances virtuelles (`provides`) et correction du repli d'inégalité `~=1` dans `axiom/kernel/api.py`.
- **Chantier 4 (Sauvegardes, Fork, Rewind & Époques)** :
  - Correction de `mods/axiom.inventory/storage.py` : isolation stricte contre la fuite d'items futurs lors d'un fork à `at_turn=0` ou tour N, et calcul du tour actuel basé sur `MAX(turn_id) FROM Event_Log`.
  - Correction de `mods/axiom.living_memory/storage.py` : nettoyage des IDs d'observations supprimées dans `obs_map` lors d'un fork.
  - Correction de `mods/axiom.living_memory/mental_models.py` : suppression des sources d'observations mortes dans les modèles mentaux survivants.
  - Création des modules `storage.py` et déclaration des handlers `rewind`/`fork` dans `mod.toml` pour `axiom.rag` et `axiom.illustrations`. Rapprochement dynamique de `RagService.base_dir`.
  - `duplicate_save` dans `axiom/savestore.py` appelle désormais `execute_external_fork(save_id, new_id, cur_turn)` sur les sauvegardes séparées.
  - Protection d'époque dans `axiom/canonize.py` et `axiom/session.py` : avortement immédiat si l'époque a changé pendant l'appel LLM de canonisation.
  - Inclusion de `commit_all` dans le bloc d'exception restaurant `_turn_id` dans `Session.resolve_tick`.
  - Normalisation des clés de statistiques issues de `Entity_Stats` dans `TurnWriteBatch` via `resolve_stat_key`.
  - Injection des `prompt_sections` des mods actifs et support du format `minimal_chat` dans `axiom/regenerate.py`.
- **Chantier 5 (Pipeline du tour & Fournisseurs)** :
  - Support des positions `after_lore`, `pre_history`, `post_history` dans `SECTION_POSITIONS`.
  - Correction du ciblage du message `user` et insertion des sections `system` avant le bloc `~~~json` dans `mods/axiom.turn/main.py`.
  - Intégration de `session_lore` et conditionnement de `state_changes` à l'état actif d'`axiom.world` dans `build_dynamic_tool_call_schema`.
  - Enregistrement des 5 drivers cloud (`claude`, `venice`, `fireworks`, `openai`, `openrouter`) dans `ProvidersService`.
- **Chantier 6 (Harnais Golden & Intégrité du moteur)** :
  - Réalignement des clés du scénario dans `tests/test_golden_step.py` (`"modifiers"`, `"session_lore"`) et peuplement des 13 tables de données runtime.
  - Test du fork à mi-parcours (tour 8) avant rembobinage et fourniture d'une 3e réponse de mock LLM pour tester la garde d'époque sans épuisement.
  - **Correction d'un bug critique découvert dans `mods/core.stat_dynamics/main.py`** : violation de contrainte `CHECK(minutes_remaining >= 0)` sur `Active_Modifiers` lors d'un tick dépassant la durée restante.
  - Harnais Golden (`test_golden_step.py`) 100% passant (5/5).

