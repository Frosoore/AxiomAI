# TODO — Système de mods

> Référence : `DOC.md` (vision, garde-fous §2, feuille de route §13). **État réel détaillé et
> justification de chaque case : `ETAT_REEL.md`** (identifiants entre crochets).
> Révisé le 2026-10-16 après l'audit code-first « sans pitié » de la branche `mods` : les cases
> cochées alors qu'il restait des bugs réels, du code mort ou des tests sur tables vides ont été
> repassées en `[~]` avec la liste exacte des correctifs à réaliser.
> Légende : `[x]` fait et vérifié dans le code · `[~]` partiel / bug résiduel (voir sous-tâches) · `[ ]` à faire.

## Cadrage
- [x] Vision validée → `DOC.md`
- [x] Critique → `CRITIQUE.md` ; arbitrage → `ARBITRAGE.md`
- [x] Décisions D-1 → D-9 (2026-09-26)
- [x] Revue de l'implémentation (2026-10-03) + Audit code-first (2026-10-16) → `review-2026-10-03/`, `ETAT_REEL.md`

## Préalable — bugs confirmés (D-1)
- [x] TICKET-100 — ids Chroma déterministes (`chunk_id` + upsert) et rollback externe après commit SQL faits ; handlers `rewind`/`fork` déclarés dans `mod.toml` et implémentés dans `storage.py` (`axiom.rag`, `axiom.illustrations`) ; `RagService.base_dir` rendu dynamique
- [x] TICKET-101 — tour échoué/annulé : plus de message orphelin (`Session.resolve_tick` + Qt `_on_worker_error`)
- [x] TICKET-102 — un seul chemin de rewind (Qt compris), `guarded_write` sur la mémoire vivante et vérification d'époque dans `Session._maybe_auto_canonize` après l'appel LLM `canonize_story`
- [x] TICKET-103 — fork filtré au tour N (`Session_Lore`, `Fired_Scheduled_Events`) et `fork_item_instances` (`mods/axiom.inventory/storage.py`) protégé contre la fuite d'items futurs au tour 0 ou tour N
- [x] TICKET-104 — `regenerate.py` retrait du schéma de tool-call et strip JSON, injection des `prompt_sections` des mods actifs et support du format de `axiom.minimal_chat`
- [x] TICKET-105 — boucle de correction de l'Arbitre rétablie et persistée dans l'`Event_Log` (rembobinable) [M4]
- [x] TICKET-088 — le fork copie `Facts`/`Observations`/`Mental_Models` ; `fork_observations` filtre `obs_map` ; `Mental_Models` purge les sources mortes ; `duplicate_save` appelle `execute_external_fork` sur saves séparées
- [x] TICKET-089 (étendu) — tables runtime des mods exclues des exports définition seule (normaliser la casse dans `export_db_to_axiom`)

## Coordination (D-6)
- [ ] Propriétaire unique de `arbitrator.py`/`session.py` formalisé dans `maintenance/collab/`
- [ ] Statut de `Multiplayer/` (fini ou gelé)

## Phase 0 — Assainir le moteur
- [x] 0a. Harnais golden (`axiom/testing/golden_harness.py`, `tests/test_golden_step.py`) [TICKET-112, TICKET-114] : clés de scénario corrigées (`"modifiers"`, `"session_lore"`), 13 tables peuplées et comparées (`Facts`, `Observations`, `Mental_Models`, `Active_Modifiers`, `Mod_KV`), fork mi-partie testé au tour 8, mock LLM 3e réponse, contrainte `Active_Modifiers` CHECK sur expirés corrigée
- [x] 0b. Fin de tour unique & routes Web (`axiom/session.py`, `main_web.py`, `web/app.js`) :
  - [x] Code mort de `_handle_memory_fact_mutation`, `_handle_memory_belief_mutation` et `_handle_memory_model_mutation` dans `main_web.py:356-495` désindenté hors du `except ImportError` [TICKET-121]
  - [x] Route `/api/session/inventory/move` compatible avec `dest_holder_kind` / `dest_holder_id` [TICKET-122]
- [x] 0c. Rewind unique + registre (`axiom/storage_registry.py`, `axiom/checkpoint.py`) [TICKET-088, 100, 103, 120 partiel]
- [x] 0d. Tour transactionnel + époques (`axiom/turn_batch.py`, `axiom/session.py`) : normalisation des stats via `resolve_stat_key` dans `_apply_events_to_state_cache` ; `commit_all` inclus dans le bloc `try/except` protégeant `_turn_id`
- [~] 0e. Config/schéma ouverts (`axiom/session.py`, `axiom/kernel/manifest.py`) [TICKET-113] :
  - [ ] Appeler `apply_registered_mod_migrations` **après** `get_kernel_registry()` dans `Session.__init__` (`axiom/session.py:186` vs `228`) et dans `savestore.create_save`
  - [ ] Parser la section déclarative `[schema]` dans `axiom/kernel/manifest.py` (TICKET-113)
- [x] 0f. Découpage du tour — orchestration unique via `axiom.turn`, `gather_context` appelé une seule fois

## Phase 1 — Noyau
- [x] Chargeur + manifeste + résolveur [K1–K4, TICKET-118] :
  - [x] Dans `LoadState.disable` (`axiom/kernel/loader.py`), propagation en cascade de `STATE_NEXT_LAUNCH` pour les dépendants d'un mod non désactivable à chaud
  - [x] Dans `bootstrap_all_mods` (`loader.py`), promotion et chargement automatique de `axiom.minimal_chat` en repli si `axiom.turn` échoue
  - [x] Dans `resolver.py`, propagation de la cause racine (`why_unavailable`) pour les dépendances virtuelles (`provides`)
  - [x] Dans `resolver.py`, vérification de `version_satisfies` sur les dépendances virtuelles (`provides`) et correction du repli `~=1` (`api.py`)
- [x] Registre exclusif / chaîne / collecte & ordre utilisateur [K3] : `user_order` respecté pour `registry.set_mod_order`, `set_patch_mod_order` et `compute_exclusive_conflicts`
- [x] Hooks — appelés, isolation par mod fautif [K5, K6] (nettoyage de `sys.modules` sur échec d'`exec_module`)
- [x] `ModContext`, désactivation à chaud & bootstrap unique [K7, K11] : `MainWindow` utilise `get_kernel_registry()` ; route `POST /api/mods/toggle` implémentée dans `main_web.py`
- [x] Stockage par politiques (`ctx.store`, table noyau `Mod_KV`, `[storage]` lu) [K9, TICKET-115]
- [~] Modpack enregistré dans la save et les exports (`.axiomsave` / `modpack.json`) [K10] :
  - [ ] Afficher `session.modpack_warning` dans `axiom/cli/play.py` et initialiser le registre dans `get_active_modpack()`
- [x] Mode sans échec [K8] : texte d'aide `--safe-mode` corrigé dans `axiom/cli/main.py:61`
- [x] CLI `axiom mods` utilisable sans UI [K13, K14]
- [x] `pluggy` évalué et écarté
- [ ] Noyau neutre (ni LLM, ni JDR, ni config applicative) [K12, TICKET-111]

## Phase 2 — Features en mods officiels
- [x] `axiom.turn` orchestre le tour ; `arbitrator.py` reste dans le noyau (décision de périmètre du 2026-10-03) [M2]
- [x] Étanchéité Noyau ↔ Mods [M1, TICKET-106, TICKET-119] : `_ACTIVE_TIME_PROVIDER = None` dans `forget_declared_storage()`, `"time_provider"` dans `declare_mod_storage`
- [x] `axiom.world` — règles déplacées ; boucle de correction rétablie [M4]
- [x] `axiom.time`, `axiom.inventory`, `axiom.rag`, `axiom.living_memory`, `axiom.illustrations`, `core.stat_dynamics` — décochables un par un
- [x] `axiom.providers` effectif (slot `axiom.turn:llm_backend`) [M8, TICKET-125] : 5 drivers cloud enregistrés (`claude`, `venice`, `fireworks`, `openai`, `openrouter`) dans `ProvidersService`
- [x] UI en mods [M7, TICKET-107, TICKET-117] :
  - [x] **TICKET-117** : Élimination des 27 imports non protégés de `help_system` via [help_bridge.py](file:///home/frosoore/Projets/AxiomAI/mods/axiom.ui.qt/ui/help_bridge.py)
  - [x] Utilisation systématique de `is_mod_active` pour la visibilité UI
  - [x] Repli par défaut `default=` sur `tr()` et ajout de `no_narrative_to_illustrate` dans les 10 fichiers de locales
- [x] Mod « chat minimal » `axiom.minimal_chat` (installation « tout décoché ») [M3] : respect de `step_context.auto_commit`
- [x] Emplacements du tour (`output_fields` & `prompt_sections`) [M5, M6, TICKET-123] :
  - [x] `_apply_prompt_sections` cible le vrai message user, insère system avant le bloc `~~~json`, supporte `after_lore`/`pre_history`/`post_history`
  - [x] `build_dynamic_tool_call_schema` intègre `session_lore` et conditionne `state_changes` à `axiom.world`
- [x] `community.survival` désactivé par défaut [M9]

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
- [~] Client de store (recherche/installation, SHA-256) [S3, S4] :
  - [ ] Valider les membres de l'archive `.axmod` contre le Path Traversal (Zip Slip) avant `zf.extractall` dans `axiom/kernel/store.py:290`
- [ ] Licence des mods — **question ouverte** (avis juridique requis ; clause retirée de `NOTICE`) [S2]
- [~] Paquet PyPI « noyau seul » fonctionnel (`export_engine.py`) [S5] :
  - [ ] Fournir un repli minimal dans `axiom/` (ou inclure les mods de base) pour que `Session.take_turn()` et `resolve_llm_backend()` fonctionnent hors du repo

## Documentation [DOC1–DOC9]
- [x] Exemple de mod canonique fonctionnel et testé (`tests/test_canonical_mod_example.py`) [DOC2]
- [ ] Corriger `README.md` (retirer `StarterWorld.axiom`, les 5 commandes CLI fictives, l'ancien texte `--safe-mode`, le « 12 Official Extracted Mods ») [DOC3, DOC4]
- [ ] Mettre à jour `ARCHITECTURE.md` pour refléter l'architecture actuelle (`mods/`, `axiom/kernel/`, registre de stockage) [DOC5]

