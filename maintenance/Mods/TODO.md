# TODO — Système de mods

> Référence : `DOC.md` (vision, garde-fous §2, feuille de route §13). **État réel détaillé et
> justification de chaque case : `ETAT_REEL.md`** (identifiants entre crochets).
> Révisé le 2026-10-03 après la revue de la branche `mods` : les cases cochées par Frosoore sans
> comportement vérifié ont été **décochées**. Règle désormais : **une case ne se coche qu'avec un test
> qui prouve le comportement promis par la vision.**
> Légende : `[x]` fait et vérifié · `[~]` partiel (voir ETAT_REEL) · `[ ]` à faire.
> Revérifié dans le code le 2026-10-03 (soir) après les travaux Claude + Gemini : voir `audit-reel-2026-10-03/` et `phase-2-vrai-deplacement/`.

## Cadrage
- [x] Vision validée → `DOC.md`
- [x] Critique → `CRITIQUE.md` ; arbitrage → `ARBITRAGE.md`
- [x] Décisions D-1 → D-9 (2026-09-26)
- [x] Revue de l'implémentation (2026-10-03) → `review-2026-10-03/`, `ETAT_REEL.md`

## Préalable — bugs confirmés (D-1)
- [x] TICKET-100 — ids Chroma déterministes (`chunk_id` + upsert) ; stockages externes rembobinés **après** le commit SQL (`test_external_store_untouched_when_the_sql_rewind_fails`)
- [x] TICKET-101 — tour échoué/annulé : plus de message orphelin (vérifié en exécutant)
- [x] TICKET-102 — un seul chemin de rewind (Qt compris) : époque, backup, SQL puis stockages externes (`test_rewind_task_uses_engine_rewind_path`)
- [x] TICKET-103 — fork filtré au tour N (`Session_Lore`, `Fired_Scheduled_Events`) (`test_mid_game_fork_vs_source_at_turn_n`)
- [x] TICKET-104 — `regenerate.py` schéma de tool-call retiré, strip JSON robuste (tests/test_ticket_104_and_exports.py)
- [x] TICKET-105 — boucle de correction de l'Arbitre rétablie et persistée dans l'Event_Log (rembobinable) [M4]
- [x] TICKET-088 — le fork garde faits/croyances/modèles, sources remappées (`test_fork_keeps_living_memory_with_remapped_sources`)
- [x] TICKET-089 (étendu)

## Coordination (D-6)
- [ ] Propriétaire unique de `arbitrator.py`/`session.py` formalisé dans `maintenance/collab/`
- [ ] Statut de `Multiplayer/` (fini ou gelé)

## Corrections d'octobre (voir `ETAT_REEL.md` §7)
- [x] Lot A — tests hermétiques (config, `dist/`, Ollama, Quick Tour) + CI adaptée + import web
- [x] Lot C — noyau (conflits, statut, ordre, versions, isolation, à chaud, safe mode, découverte, `.axmod`, patches, créateur LLM)
- [x] Décisions prises sans le propriétaire annulées (clause `NOTICE`, en-tête/bilan du DOC, licence = question ouverte)
- [x] Lot B (B1 saves/rewind, B2 tour) — finalisé et testé (test_turn_pipeline_b2, test_session, test_golden_step)
- [x] Lot E — **vrai déplacement** des 5 fonctionnalités et de leurs satellites (`phase-2-vrai-deplacement/`) ; la première version (code remis dans `axiom/`) a été annulée
- [x] Doc (exemple de mod canonique qui marche, README, GUIDES, test_canonical_mod_example)

## Phase 0 — Assainir le moteur (≈ 75 %)
- [x] 0a. Harnais golden — fork à mi-partie, config hermétique, vérification complète
- [x] 0b. Fin de tour unique — post-commit Session unique (`_post_turn_pipeline`, `_maybe_auto_canonize`), UI assainies
- [x] 0c. Rewind unique + registre — registre OK ; fork amnésique résolu ; Mod_KV supporté
- [x] 0d. Tour transactionnel + époques — TurnWriteBatch atomique, gardes d'époques, stage_event
- [~] 0e. Config/schéma ouverts — migrations par mod appliquées à la création et à l'ouverture d'une save (`test_mod_migrations_applied_on_create_and_on_open`) ; reste : `[schema]` du manifeste non lu
- [x] 0f. Découpage du tour — orchestration unique via `axiom.turn`, suppression des branches dupliquées

## Phase 1 — Noyau (squelette)
- [x] Chargeur + manifeste — manifeste, tri des dépendances OK, virtual providers [K1–K4]
- [x] Registre exclusif / chaîne / collecte — collecte/chaîne OK, exclusif avec arbitrage d'ordre [K3]
- [x] Hooks — appelés, isolation par mod fautif [K5, K6]
- [x] `ModContext` — `cleanup` fonctionnel, cycle de vie hermétique, jobs [K7, K11]
- [x] Stockage par politiques (`ctx.store`, table noyau `Mod_KV`, `[storage]` lu) [K9]
- [x] Modpack enregistré dans la save et les exports (.axiomsave / modpack.json) [K10]
- [x] Mode sans échec — interfaces + chat minimal + fournisseur livrés avec Axiom, rien d'autre (décision 2026-10-03) [K8]
- [x] CLI `axiom mods` utilisable sans UI
- [x] `pluggy` évalué et écarté
- [ ] Noyau neutre (ni LLM, ni JDR, ni config applicative) [K12]

## Phase 2 — Features en mods officiels (façade)
- [~] `axiom.turn` orchestre le tour ; `arbitrator.py` reste dans le noyau (décision de périmètre du 2026-10-03), sans plus aucune logique des fonctionnalités [M2]
- [x] Le noyau n'importe plus rien de `mods/` et ne contient plus le code ni le SQL des fonctionnalités (`test_engine_has_no_forbidden_imports`, `test_kernel_holds_no_feature_data_logic`) [M1]
- [x] `axiom.world` — règles déplacées ; boucle de correction rétablie [M4]
- [x] `axiom.time`, `axiom.inventory`, `axiom.rag`, `axiom.living_memory`, `axiom.illustrations`, `core.stat_dynamics` — décochables un par un
- [x] `axiom.providers` effectif (slot `axiom.turn:llm_backend`) [M8]
- [~] UI en mods — statut réel au lancement, emplacements web rendus ; lanceurs encore à la racine [M7]
- [x] Mod « chat minimal » `axiom.minimal_chat` (installation « tout décoché ») [M3]
- [x] Emplacements du tour — contribution dynamique au schéma JSON (`output_fields`) et sections flexibles [M5, M6]

## Phase 3 — Patches outillés
- [x] Trampolines `@patchable` (before/after/around, `ShortCircuit`) sur fonctions, from-import capturés
- [x] Secours `__code__` — fonctions simples, méthodes et closures [P1]
- [x] Refus bruyant des cibles introuvables, aucun patch inactif listé [P1, P3]
- [x] Points `@patchable` dans le moteur (`build_narrative_prompt`, `build_timekeeper_prompt`, `regenerate_variant`, `get_spatial_context`, `get_time_of_day_context`) [P2]
- [x] Gel pendant un step — réentrant [P4]
- [x] `axiom mods patches` / `axiom mod validate` — listes fiables

## Phase 4 — Création de mods
- [x] `axiom mod new` — modèles sur les hooks publics réellement déclenchés ; modèle « data » sur `ctx.store` [C2]
- [~] `axiom mod test` — existe ; n'utilise pas le harnais golden [C3]
- [x] `axiom mod dev` (rechargement à chaud en dev)
- [x] Créateur LLM : aucune exécution avant confirmation, écriture confinée (lot C, vérifié par l'audit) [C1]
- [ ] Créateur LLM sorti du noyau (mod) [C4]

## Phase 5 — Store, dépendances, licence, distribution (gelée)
- [x] Vérification déclarative `[python].requires`, sans installeur (D-7)
- [~] Client de store (recherche/installation, SHA-256) — sans catalogue ni serveur ; installe dans les sources [S3, S4]
- [ ] Licence des mods — **question ouverte** (avis juridique requis ; clause retirée de `NOTICE`) [S2]
- [ ] Paquet PyPI « noyau seul » fonctionnel — **ne pas publier la 1.0.0 en l'état** [S5]
