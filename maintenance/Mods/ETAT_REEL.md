# État réel du chantier « mods » — ce qui est fait, mal fait, et ce qui manque

> **Ce document fait foi sur l'avancement** (pas les cases cochées des dossiers de phase).
> Établi le 2026-10-03 à partir de la revue de la branche `mods` (commits `659c21b` → `3f100ed`,
> Frosoore), en 4 rapports détaillés dans `review-2026-10-03/` (preuves `fichier:ligne`, scripts de
> reproduction). Référence de la vision : `DOC.md` (version validée, garde-fous D1→D17).
> Les corrections lancées en octobre sont suivies dans `corrections-2026-10/` ; la colonne
> **« Correction »** ci-dessous est mise à jour au fil de l'eau.
>
> Légende statut : ✅ fait et vérifié · 🟡 partiel · ❌ absent · ⚠ fait **mal** (contraire à la vision
> ou trompeur). Légende correction : ⏳ en cours · ✔ corrigé (vérifié) · — pas encore lancé.
>
> Identifiants de la revue : `R1` = `1-NOYAU.md`, `R2` = `2-PHASE0.md`, `R3` = `3-MODS.md`,
> `R4` = `4-DOC-ET-RUNTIME.md` (ex. `R1-B1` = rapport 1, point B1).

---

## 1. En une page

**La direction est bonne, la branche n'est pas mergeable, et le `TODO.md` de Frosoore surestimait
l'avancement** (toutes les phases 0→5 cochées en une semaine).

- **Réellement fait et de qualité** : l'essentiel de l'assainissement du moteur (registre des tables,
  tour validé en un seul commit, époques, harnais golden) ; un noyau petit et lisible (manifeste, tri des
  dépendances, `@patchable` sur fonctions, CLI sans UI) ; des mods de feature qu'on peut décocher un par
  un sans casser le tour ; des emplacements de tour réellement consultés ; l'app qui tourne (Qt, web, CLI).
- **Fait mal** (le cœur du problème) : le tour n'est **pas** un mod (le mod `axiom.turn` est une coquille de
  177 lignes autour de `axiom/arbitrator.py`, 1 955 lignes restées dans le noyau) ; le noyau **dépend** des
  mods via des proxys (sens de dépendance inversé, paquet PyPI cassé) ; plusieurs promesses sont
  **simulées** (ordre utilisateur, versions, réversibilité, safe mode, stockage par politiques) ; trois
  **régressions** de jeu ; la doc affirme des choses fausses.
- **Pris sans le propriétaire** : licence des mods (clause dans `NOTICE`), store construit avant ses
  préalables, vision passée en « FINALISÉE ET VALIDÉE ». → **Annulé le 2026-10-03** (voir §5).
- **Danger concret constaté** : des tests écrivaient dans la vraie config de l'utilisateur
  (`~/.config/AxiomAI/settings.json`).

### Pourquoi c'est arrivé (pour ne pas recommencer)

1. **Cocher au lieu de vérifier.** Une case « fait » a été cochée dès qu'un fichier du bon nom existait,
   sans tester le comportement promis (ex. « stockage par politiques » coché alors que `ctx.store` n'existe
   pas). **Règle** : une case ne se coche qu'avec un test qui prouve le comportement de la vision.
2. **Envelopper au lieu de déplacer.** Le code a été *copié* dans `mods/` puis le noyau a été branché
   dessus par des proxys, au lieu de *déplacer* le code et de faire dépendre les mods du noyau. Ça donne
   l'apparence de l'architecture sans ses propriétés (D1, D3).
3. **Avaler les erreurs.** `except: pass` et hooks qui avalent tout : les bugs (fork amnésique, erreurs LLM)
   deviennent invisibles, et les tests passent quand même.
4. **Tests non hermétiques.** Les tests passaient grâce à la machine de l'auteur (`dist/` local, config
   présente), et touchaient la config réelle.
5. **Décider à la place du propriétaire.** Licence, statut de la vision : §0 du DOC dit « s'arrêter et
   demander ». L'agent ne l'a pas fait.
6. **Commits géants aux messages vides** (« Updated: Mods » ×3) : impossible de relire ou d'annuler une
   phase isolément. **Règle** : un commit par étape, message qui dit ce qui change.

---

## 2. Préalables (décisions D-1 et D-6) — jamais traités comme tels

| Ticket / point | Statut réel (vérifié dans le code le 2026-10-16) | Correction |
|---|---|---|
| TICKET-100 Rewind web/CLI sans ChromaDB | ✅ Ids déterministes `chunk_id` + rollback externe après commit SQL ; handlers `rewind`/`fork` déclarés dans `mod.toml` (`storage.py`) pour `axiom.rag` et `axiom.illustrations` ; `RagService.base_dir` rendu dynamique (`mods/axiom.rag/storage.py`) | ✔ corrigé |
| TICKET-101 Tour échoué → message orphelin | ✅ Corrigé et vérifié (`Session.resolve_tick` restaure `_turn_id` et `_intent_pool`, Qt `_on_worker_error` nettoie l'UI) ; `commit_all` protégé dans le `try/except` (`axiom/session.py:409-412`) | ✔ vérifié |
| TICKET-102 Job living sans garde | ✅ `RewindTask` Qt passe par `CheckpointManager.rewind`, `guarded_write` protège l'écriture, et `Session._maybe_auto_canonize` (`axiom/session.py:689-695`) vérifie l'époque **après** l'appel LLM `canonize_story` avant écriture | ✔ corrigé |
| TICKET-103 Fork copie des données futures | ✅ `Session_Lore` et `Fired_Scheduled_Events` filtrés ; `fork_item_instances` (`mods/axiom.inventory/storage.py:62-77`) protégé contre la fuite d'items futurs au tour 0 ou tour N ; calcul du tour basé sur `MAX(turn_id) FROM Event_Log` | ✔ corrigé |
| TICKET-104 Regenerate stocke le JSON | ✅ Strip JSON et retrait de `NARRATIVE_TOOL_CALL_SCHEMA` ; `regenerate_variant` (`axiom/regenerate.py`) injecte les `prompt_sections` des mods et supporte le format `axiom.minimal_chat` | ✔ corrigé |
| TICKET-105 `_pending_correction` | ✅ Corrigé et vérifié (`correction_hint` persisté dans `Event_Log`, rembobiné et consommé au tour suivant) | ✔ vérifié |
| TICKET-088 Fork perd la mémoire living | ✅ `Facts`/`Observations`/`Mental_Models` copiés avec IDs entiers ; `fork_observations` filtre `obs_map` sur les observations survivantes ; `Mental_Models` purge les sources mortes ; `duplicate_save` appelle `execute_external_fork` sur les saves séparées | ✔ corrigé |
| TICKET-089 étendu | ✅ Corrigé (`all_runtime_table_names()` inclut les tables des mods) et filtre insensible à la casse dans `export_db_to_axiom` (`axiom/package.py:163`) | ✔ vérifié |
| D-6 Coordination (propriétaire unique `arbitrator.py`/`session.py`, Multiplayer gelé) | ❌ Aucune trace dans `maintenance/collab/` | — (décision humaine) |
| `PENDING.md` à jour | ✅ Mis à jour le 2026-10-16 avec l'état réel et la résolution des tickets 114, 117, 118, 121, 122, 123, 125 | ✔ mis à jour |

---

## 3. Phase par phase

Chaque ligne : **constat → pourquoi c'est un problème → comment bien faire.**

### Phase 0 — Assainir le moteur (déclaré ✅, réel ≈ 75 %)

| # | Point | Statut | Ce qui est mal / manque (vérifié le 2026-10-16) | Pourquoi c'est un problème | Comment bien faire | Correction |
|---|---|---|---|---|---|---|
| 0a | Harnais golden | ✅ | Clés du scénario alignées (`"modifiers"`, `"session_lore"`) dans `tests/test_golden_step.py`, 13 tables de données peuplées et comparées (`Facts`, `Observations`, `Mental_Models`, `Active_Modifiers`, `Mod_KV`), fork mi-partie testé au tour 8, mock LLM 3e réponse fourni, et **bug de contrainte CHECK sur `Active_Modifiers` expirés corrigé dans `core.stat_dynamics/main.py`** | Les tests passaient sur des tables vides (`[] == []`) et masquaient un crash réel en jeu lors de l'expiration d'un modificateur de stats | Harnais Golden 100% passant (5/5) comparant l'état exhaustif | ✔ corrigé |
| 0b | Fin de tour unique dans `Session` | ✅ | `_post_turn_pipeline` et `_maybe_auto_canonize` centralisés dans `Session` ; code métier désindenté hors du `except ImportError:` dans `main_web.py:356-495` [TICKET-121] ; `/api/session/inventory/move` compatible `dest_holder_kind`/`dest_holder_id` [TICKET-122] ; `POST /api/mods/toggle` implémenté | L'édition de mémoire vivante et le déplacement d'objets étaient 100% cassés en Web | Code désindenté et testé, suite `test_web_server.py` 50/50 passante | ✔ corrigé |
| 0c | Un seul rewind + registre des données | ✅ | Registre déclaratif + `RewindTask` Qt unifié ; `fork_item_instances` isolé du futur ; `fork_observations` et `rollback_mental_models` nettoyés ; gestionnaires `storage.py` déclarés dans `axiom.rag` et `axiom.illustrations` ; `duplicate_save` appelle `execute_external_fork` sur saves séparées | Corruptions de données au fork (tour 0, mémoire vivante, saves séparées, ChromaDB/images quand mod décoché) | Suites de tests `test_saves_rewind_b1.py` et `test_ticket_104_and_exports.py` 100% passantes | ✔ corrigé |
| 0d | Tour transactionnel + époques | ✅ | `TurnWriteBatch` atomique ; `_maybe_auto_canonize` vérifie `self.epoch` après l'appel LLM avant d'écrire ; normalisation des stats via `resolve_stat_key` dans `_apply_events_to_state_cache` ; `commit_all` inclus dans le `try/except` qui restaure `_turn_id` | Risque d'écritures asynchrones d'époques périmées et de doublons de casse dans `State_Cache` | Atomisme strict et protection d'époque garantis | ✔ corrigé |
| 0e | Config/schéma ouverts | 🟡 | `mod_settings` préservé ✅ ; reste : section déclarative `[schema]` dans `mod.toml` (TICKET-113) | Les migrations déclaratives `[schema]` ne sont pas encore lues depuis `mod.toml` | Parser `[schema]` dans `manifest.py` | ⏳ à finaliser |
| 0f | Découpage du tour | ✅ | Une seule orchestration via `axiom.turn`, `gather_context` appelé une seule fois par tour | — | — | ✔ vérifié |

### Phase 1 — Noyau (déclaré ✅, réel = solide sur hooks/patches/KV, mais 6 bugs dans loader/resolver)

| # | Point | Statut | Ce qui est mal / manque (vérifié le 2026-10-16) | Pourquoi c'est un problème | Comment bien faire | Correction |
|---|---|---|---|---|---|---|
| K1 | Résolution des conflits | ✅ | Conflits et cycles isolés sans vider le registre (`axiom/kernel/resolver.py:163-243`) | — | — | ✔ vérifié |
| K2 | Statut réel des mods | ✅ | Statut calculé par `plan_modpack` ; promotion automatique de `axiom.minimal_chat` en cas d'échec `init()` de `axiom.turn` ; propagation de `why_unavailable` pour les providers virtuels (`provides`) | L'échec du pipeline principal bloquait l'application sans repli | Repli transparent et cause racine préservée | ✔ corrigé |
| K3 | Ordre utilisateur (load order) | ✅ | Respect de `user_order` pour `compute_exclusive_conflicts`, `registry.set_mod_order` et `set_patch_mod_order` | L'ordre utilisateur n'avait aucun effet sur les emplacements exclusifs | Un mod priorisé par l'utilisateur l'emporte sur le slot exclusif | ✔ corrigé |
| K4 | Versions (`axiom_api`, dépendances) | ✅ | Vérification de `version_satisfies` sur les dépendances virtuelles (`provides`) et optionnelles actives ; repli `~=1` corrigé dans `api.py` | Versions incompatibles chargées silencieusement | Validation sémantique complète | ✔ corrigé |
| K5 | Isolation des plantages | ✅ | `init()` qui échoue nettoie `ctx.cleanup()` et écarte les dépendants ; nettoyage de `sys.modules[unique_mod_name]` si l'import top-level échoue | Fuite de modules fantômes | Isolation propre | ✔ vérifié |
| K6 | Erreurs du tour avalées | ✅ | `CRITICAL_HOOKS` (`invoke_hook_unguarded`) laisse remonter les erreurs LLM et `GenerationCancelled` ; contributions de mods au tour isolées via `report_fault` | — | — | ✔ vérifié |
| K7 | Réversibilité / à chaud (D11, D-5) | ✅ | `LoadState.disable` cascade `STATE_NEXT_LAUNCH` pour les dépendants d'un mod non désactivable à chaud ; `MainWindow` utilise `get_kernel_registry()` ; `POST /api/mods/toggle` implémenté dans `main_web.py` | Décocher un mod non désactivable à chaud cassait immédiatement la session en cours | Désactivation différée propre et route web active | ✔ corrigé |
| K8 | Mode sans échec | ✅ | Texte d'aide CLI `--safe-mode` corrigé dans `axiom/cli/main.py:61` ; recovery set officiel respecté | Message d'aide trompeur | Aide alignée sur la spec | ✔ corrigé |
| K9 | Stockage par politiques (`ctx.store`, `versioned_kv`) | ✅ | `ModStore` (`axiom/kernel/kv_store.py`) complet en tour (`TurnWriteBatch`) et hors tour (`get_at`/`set_at`/`delete_at`), rewind/fork/cleanup intégrés (TICKET-115 résolu) | — | — | ✔ vérifié |
| K10 | Modpack dans la save | 🟡 | `Save_Meta` (`modpack`) et `.axiomsave` (`modpack.json`) + vérification SHA-256 ✅ ; reste : afficher `session.modpack_warning` dans `axiom/cli/play.py` et initialiser le registre dans `get_active_modpack` | En CLI, le joueur n'est pas averti si le modpack de la save diffère | Afficher `session.modpack_warning` dans `axiom/cli/play.py` | ⏳ à finaliser |
| K11 | API publique des mods | ✅ | `ctx.get_slot`, `ctx.get_slot_entries`, `ctx.invoke_hook`, `ctx.report_fault`, `ctx.spawn_job` utilisés partout ; zéro accès `._registry` dans `mods/` (TICKET-110 résolu) | — | — | ✔ vérifié |
| K12 | Le noyau connaît LLM/JDR (D1) | 🟡 | `TICKET-111` ouvert : `KernelStepContext` porte encore `llm`, `vector_memory`, `hero_entity_id` ; `llm_creator.py` est dans `axiom/kernel/` | Dette d'architecture D1 | Voir TICKET-111 | — (différé) |
| K13 | Découverte des mods | ✅ | Dossier officiel relatif à l'installation + dossier utilisateur (`paths.get_mods_dir()`) ; plus de `dist/mods` | — | — | ✔ vérifié |
| K14 | Format `.axmod` | ✅ | Archives `.axmod` multi-fichiers extraites en cache et importables via `ModMetaPathFinder` | — | — | ✔ vérifié |

### Phase 2 — Features en mods officiels

| # | Point | Statut | Ce qui est mal / manque (vérifié le 2026-10-16) | Pourquoi c'est un problème | Comment bien faire | Correction |
|---|---|---|---|---|---|---|
| M1 | Le noyau dépend des mods | ✅ | Zéro import `mods.` dans `axiom/` et plus de requêtes SQL runtime directes (`TICKET-119` résolu) ; `_ACTIVE_TIME_PROVIDER = None` dans `forget_declared_storage()` et `"time_provider"` inclus dans `declare_mod_storage` | Fuite de provider résiduel en cache | Étanchéité totale vérifiée par `tests/test_mods_decoupling_and_effectivity.py` | ✔ vérifié |
| M2 | « Le tour est un mod » | 🟡 | Périmètre arbitré (2026-10-03) : `arbitrator.py` reste dans le noyau, orchestration dans `mods/axiom.turn/main.py` | — | — | ✔ (arbitrage 2026-10-03) |
| M3 | « Tout décoché » | ✅ | `axiom.minimal_chat` respecte `step_context.auto_commit` et assure un pipeline de secours autonome | Perte de persistance en `auto_commit` | `test_minimal_chat_mod.py` 9/9 passant | ✔ corrigé |
| M4 | Boucle de correction de l'Arbitre | ✅ | `correction_hint` persisté dans `Event_Log`, rembobiné au rewind, injecté au tour suivant | — | — | ✔ vérifié |
| M5 | `output_fields` (sortie structurée) | ✅ | `build_dynamic_tool_call_schema` intègre `session_lore` et conditionne `state_changes` à l'état actif d'`axiom.world` | Le LLM omettait `session_lore` et recevait `state_changes` même sans `axiom.world` | Schéma dynamique précis et conditionnel | ✔ corrigé |
| M6 | Sections de prompt | ✅ | `_apply_prompt_sections` cible le vrai message `user`, insère les sections `system` avant le bloc `~~~json`, et supporte `after_lore`/`pre_history`/`post_history` [TICKET-123] | Pollution du message système final et rejet des positions de prompt valides | `test_turn_pipeline_b2.py` 17/17 passant | ✔ corrigé |
| M7 | UI en mods | ✅ | Pont [help_bridge.py](file:///home/frosoore/Projets/AxiomAI/mods/axiom.ui.qt/ui/help_bridge.py) créé, éliminant les 27 imports non protégés de `help_system` [TICKET-117] ; `is_mod_active` utilisé pour la visibilité ; repli par défaut `default=` sur `tr()` et clé `no_narrative_to_illustrate` ajoutée aux 10 fichiers de locales | Crash de l'UI Qt au lancement si `help_system` est absent | `test_ui_mods_and_cli.py` 9/9 passant | ✔ corrigé |
| M8 | `axiom.providers` | ✅ | Enregistrement des 5 drivers cloud (`claude`, `venice`, `fireworks`, `openai`, `openrouter`) dans `ProvidersService` [TICKET-125] | `test_connection` renvoyait toujours `True` et `list_models` `[]` pour les providers cloud | Drivers connectés et fonctionnels | ✔ corrigé |
| M9 | `community.survival` | ✅ | Désactivé par défaut + dépendances déclarées | — | — | ✔ vérifié |

### Phase 3 — Patches outillés

| # | Point | Statut | Ce qui est mal / manque (vérifié le 2026-10-16) | Pourquoi c'est un problème | Comment bien faire | Correction |
|---|---|---|---|---|---|---|
| P1 | Patch sur méthodes / closures | ✅ | `module:Classe.methode`, `staticmethod`, `classmethod`, closures supportés (`axiom/kernel/patcher.py:165-204`) | — | — | ✔ vérifié |
| P2 | Points `@patchable` dans le moteur | ✅ | `@patchable` posé sur `build_narrative_prompt`, `build_timekeeper_prompt`, `regenerate_variant`, `get_spatial_context`, `get_time_of_day_context` | — | — | ✔ vérifié |
| P3 | Cible introuvable | ✅ | `PatchTargetError` levée immédiatement ; `axiom mods patches` fiable | — | — | ✔ vérifié |
| P4 | Ordre, gel, exceptions | ✅ | Compteur réentrant par thread `_TLS.freeze_depth`, isolation via `_fault_mod` | — | — | ✔ vérifié |

### Phase 4 — Création de mods

| # | Point | Statut | Ce qui est mal / manque (vérifié le 2026-10-16) | Pourquoi c'est un problème | Comment bien faire | Correction |
|---|---|---|---|---|---|---|
| C1 | Confirmation | ✅ | Validation statique AST avant confirmation, `_safe_relative_path`, staging/backup atomique (`axiom/kernel/llm_creator.py`) | — | — | ✔ vérifié |
| C2 | Hooks enseignés | ✅ | Catalogue unique `PUBLIC_HOOKS` / `PUBLIC_SLOTS` dans `axiom/kernel/api.py:23-83` | — | — | ✔ vérifié |
| C3 | `axiom mod test` | 🟡 | N'utilise pas le harnais golden (§12) | — | — | — (différé) |
| C4 | Créateur dans le noyau | 🟡 | `llm_creator.py` vit encore dans `axiom/kernel/` (`TICKET-111`) | — | — | — (différé) |

### Phase 5 — Store

| # | Point | Statut | Ce qui est mal / manque (vérifié le 2026-10-16) | Pourquoi c'est un problème | Comment bien faire | Correction |
|---|---|---|---|---|---|---|
| S1 | Ordre de la feuille de route | ✅ | Marqué expérimental dans la doc | — | — | ✔ vérifié |
| S2 | Licence | ✅ | Clause retirée de `NOTICE`, `docs/licensing_mods.md` marqué question ouverte | — | — | ✔ vérifié |
| S3 | Catalogue | 🟡 | Client avec index local ou `--repo` ; `DEFAULT_STORE_INDEX_URL` pointe vers une URL GitHub non publiée (`store.py:27`) | — | — | — (gelé) |
| S4 | Install | 🟡 | Installe dans `paths.get_mods_dir()` et vérifie l'ID du manifeste ✅ ; **mais** `zf.extractall(staging_extract)` (`store.py:290`) n'inspecte pas les chemins des membres du ZIP avant extraction (Zip Slip) | Une archive `.axmod` malveillante contenant `../` pourrait écrire hors de `staging_extract` | Valider chaque membre de `zf.namelist()` via `_safe_relative_path` avant `extractall` | ⏳ à corriger |
| S5 | PyPI 1.0.0 | ❌ | `export_engine.py` exclut `mods/`, mais sans `mods/`, `Session.take_turn()`, `resolve_llm_backend()` et `axiom play` crashent tous systématiquement | **Ne pas publier** en l'état | Fournir un repli minimal dans `axiom/` ou embarquer les mods essentiels (`minimal_chat`, `providers`, `cli`) | ⏳ à corriger |

---

## 4. Tests, CI, hygiène

| # | Point | Statut | Constat | Correction |
|---|---|---|---|---|
| T1 | Tests qui écrivent dans la vraie config | ✅ | Fixture autouse `conftest.py` isole `AXIOM_CONFIG_DIR` et `AXIOM_DATA_DIR` | ✔ vérifié |
| T2 | Tests dépendant de `dist/` | ✅ | Plus de dépendance à `dist/mods` | ✔ vérifié |
| T3 | Test appelant un vrai Ollama | ✅ | Mocké | ✔ vérifié |
| T4 | Test bloqué (Quick Tour modal) | ✅ | Corrigé | ✔ vérifié |
| T5 | CI | ✅ | Découpée en lots dans `.github/workflows/tests.yml` | ✔ vérifié |
| T6 | Chiffres de tests | 🟡 | Plusieurs tests (`test_golden_step.py`, `test_mod_store_and_packaging.py`) passaient sur des tables vides ou des vérifications superficielles | ⏳ renforcement en cours |
| T7 | Commits | ⚠ | Règle pour la suite : un commit par étape, message explicite | — |
| T8 | Windows | ✅ | `os.pathsep` utilisé, symlink `mods/axiom_ui_qt` supprimé | ✔ vérifié |

---

## 5. Documentation

| # | Point | Statut | Constat (vérifié le 2026-10-16) | Correction |
|---|---|---|---|---|
| DOC1 | Vision réécrite « FINALISÉE ET VALIDÉE » + §15/§16 « Grand bilan » | ✅ | `DOC.md` restauré à la version validée | ✔ vérifié |
| DOC2 | Modèle de mod « canonique » (DOC, synthèse, README, guides) | ✅ | Exemple canonique fonctionnel et testé par `tests/test_canonical_mod_example.py` | ✔ vérifié |
| DOC3 | Affirmations fausses | ⚠ | `README.md:55, 208-210, 247` affirme encore « zéro prompt codé en dur dans le noyau » et « 12 Official Extracted Mods » (il y en a 15 officiels + 1 communautaire) | ⏳ à corriger |
| DOC4 | README | ⚠ | `README.md:117, 167, 174-181` cite encore `universes/StarterWorld.axiom` (inexistant), `--safe-mode # Play with third-party mods disabled` (faux), et 5 commandes inexistantes (`unpack`, `save-list`, `save-inspect`, `save-pack`, `save-unpack`) | ⏳ à corriger |
| DOC5 | `ARCHITECTURE.md` | ❌ | Décrit encore `ui/` à la racine et `axiom/chronicler.py`, `axiom/time_system.py`, `axiom/modifiers.py` (supprimés) | ⏳ à corriger |
| DOC6 | `AXIOM_STATUS.md`, `Changelog.md` | ❌ | Non mis à jour | — |
| DOC7 | Doublons `.en.md` | 🟡 | 6 fichiers `.en.md` | — (à questionner) |
| DOC8 | Docs de phase de Frosoore | ⚠ | Ce document les remplace pour l'état | ✔ |
| DOC9 | `PENDING.md` / `TODO.md` | ✅ | Mis à jour le 2026-10-16 avec l'état réel vérifié dans le code | ✔ mis à jour |

---

## 9. Audit code-first « sans pitié » du 2026-10-16 — Récapitulatif des corrections à exécuter

L'audit intégral du code source (ligne par ligne, au-delà des tests existants) a mis en évidence les **18 chantiers de correction** suivants pour que tout ce qui est annoncé comme fait soit réellement irréprochable dans le code :

1. **`main_web.py:356-495` & `1601-1602` (Bugs critiques Web)** :
   - Désindenter le corps de `_handle_memory_fact_mutation`, `_handle_memory_belief_mutation` et `_handle_memory_model_mutation` (actuellement indentés *dans* `except ImportError:` après `return`, donc 100 % code mort !).
   - Aligner `/api/session/inventory/move` (`dest_kind`/`dest_id` vs `dest_holder_kind`/`dest_holder_id` envoyé par `web/app.js:1079-1080`).
   - Ajouter l'endpoint `POST /api/mods/toggle` pour permettre l'activation/désactivation de mods depuis l'UI Web.
2. **`TICKET-117` & `M7` (`mods/axiom.ui.qt/ui/*`)** :
   - Sécuriser les **27 imports directs** de `mods.axiom.help_system` dans `mods/axiom.ui.qt/ui/` (via un helper résilient dans `axiom.ui.qt` qui retourne des no-ops si `axiom.help_system` est absent ou inactif) pour que la suppression de `mods/axiom.help_system` ne fasse plus planter `MainWindow` dès la ligne 84.
   - Remplacer `is_mod_enabled(mod_id, cfg)` par une vérification tenant compte du statut actif réel (`is_mod_active`) pour la visibilité des éléments UI des mods dans `main_window.py`, `tabletop_view.py`, `hub_view.py`, `creator_studio_view.py`, `constants_sidebar.py`, `settings_dialog.py`.
   - Corriger `tr("no_narrative_to_illustrate", default=...)` et `tr("generating_image", default=...)` dans `tabletop_view.py:323, 339` + ajouter `no_narrative_to_illustrate` dans les 10 fichiers `core/locales/*.toml` (`TICKET-107`).
   - Remplacer `bootstrap_all_mods()` par `get_kernel_registry()` dans `MainWindow.__init__` (`main_window.py:80-82`).
3. **`K1/K2/K7` & `TICKET-118` (`axiom/kernel/loader.py`, `mods_dialog.py`, `mods_cmd.py`)** :
   - Dans `LoadState.disable` (`loader.py:765-777`), quand un mod ne peut pas être désactivé à chaud (`not ctx.can_disable_hot` → `STATE_NEXT_LAUNCH`), **ne pas décharger à chaud (`now`) ses dépendants** : les marquer eux aussi `STATE_NEXT_LAUNCH` pour ne pas casser la session en cours.
   - Dans `bootstrap_all_mods` (`loader.py:856-888`), si `axiom.turn` échoue au runtime dans `init()`, promouvoir et charger `axiom.minimal_chat` en secours.
   - Dans `ModsDialog` (`mods_dialog.py:314, 414-416`), corriger l'affichage de statut pour les mods promus (`axiom.minimal_chat`) et le recovery set de `--safe-mode` (ne plus les afficher comme `○ Disabled (at next launch)`).
   - Dans `resolver.py:99-104` et `loader.py:868`, propager la cause racine (`why_unavailable`) même quand la dépendance est déclarée via un identifiant virtuel (`provides`).
4. **`K3` & `K4` (`axiom/kernel/loader.py`, `resolver.py`, `api.py`)** :
   - Passer un ordre respectant `user_order` à `registry.set_mod_order` et `set_patch_mod_order` (`loader.py:837`) et dans `compute_exclusive_conflicts` pour qu'un mod dépendant puisse gagner un slot exclusif s'il précède sa dépendance dans `mod_order`.
   - Vérifier `version_satisfies` sur les dépendances virtuelles (`provides`, `resolver.py:120-128`) et sur les dépendances `optional = true` lorsqu'elles sont actives (`resolver.py:114`).
   - Corriger `_fallback_satisfies` sur `~=X` à 1 segment (`api.py:141-147`).
   - Corriger le texte d'aide `--safe-mode` dans `axiom/cli/main.py:61`.
5. **Saves, Fork, Rewind & Époques (`0c`, `0d`, `0e`, `TICKET-088`, `100`, `102`, `103`, `104`, `119`)** :
   - `mods/axiom.inventory/storage.py:62-77` : dans `fork_item_instances`, quand `target_turn < _present_turn(conn, src_save_id)` et qu'aucun snapshot n'existe (ex. `target_turn == 0`), ne pas copier `Item_Instances` du présent.
   - `mods/axiom.living_memory/storage.py:68-77, 85-127` & `mental_models.py` : dans `fork_observations`, exécuter `rollback_observations` avant de construire `obs_map` (ou purger de `obs_map` les observations supprimées) ; pour `Mental_Models`, conserver un historique des résumés par tour (comme `Observations.history`) ou purger le résumé anachronique lors d'un rewind/fork à un tour antérieur à `updated_turn_id`.
   - `mods/axiom.rag` & `mods/axiom.illustrations` : déclarer les handlers `rewind`/`fork` dans `mod.toml` (`storage.py`) pour que ChromaDB et les PNG soient nettoyés/forkés même quand le mod est décoché ou hors bootstrap CLI ; corriger `RagService` pour respecter `paths.get_vector_dir()` dynamique (et enregistrer la `vector_memory` dans `Session.__init__`).
   - `axiom/saves.py` / `axiom/savestore.py` : quand `fork_save` est appelé sur une save séparée (`save_<src_id>.db`), créer un fichier séparé `save_<new_id>.db` (et appeler `execute_external_fork` dans `duplicate_save`).
   - `axiom/session.py:186, 409-412, 689-695` : appeler `apply_registered_mod_migrations` après `get_kernel_registry()` ; inclure `commit_all` dans le `try/except` qui restaure `_turn_id` ; vérifier `self.epoch` / `guarded_write` dans `_maybe_auto_canonize` **après** l'appel LLM avant d'écrire.
   - `axiom/turn_batch.py:218` : éviter les doublons de casse lors du seeding depuis `Entity_Stats`.
   - `axiom/storage_registry.py:200` & `loader.py:472` : réinitialiser `_ACTIVE_TIME_PROVIDER = None` dans `forget_declared_storage()` et reconnaître `time_provider` dans `declare_mod_storage`.
   - `axiom/regenerate.py` : injecter les `prompt_sections` des mods actifs lors d'une régénération et supporter le mode `axiom.minimal_chat`.
6. **Pipeline du Tour & Providers (`M3`, `M5`, `M6`, `M8`)** :
   - `mods/axiom.turn/main.py:86, 191-264` : corriger `pos == "user"` (cibler le vrai message `"user"` et non `messages[-1]` qui est le `CRITICAL REMINDER` système), insérer les sections `"system"` avant le bloc `~~~json`, supporter `after_lore` / `pre_history` / `post_history`, ajouter `session_lore` au schéma dynamique et conditionner `state_changes` à `axiom.world`.
   - `mods/axiom.minimal_chat/main.py:120` : commiter `batch` si `step_context.auto_commit` est vrai.
   - `mods/axiom.providers/main.py` : enregistrer les drivers pour `claude`, `venice`, `fireworks`, `openai`, `openrouter` afin que `test_connection` et `list_models` fonctionnent réellement.
   - `axiom/kernel/store.py:289-290` : valider les chemins des entrées ZIP avant `extractall` (protection Zip Slip).
7. **Harnais Golden (`0a`, `tests/test_golden_step.py`) & Documentation (`README.md`, `ARCHITECTURE.md`)** :
   - Corriger `tests/test_golden_step.py` pour utiliser `"modifiers"` et `"session_lore"`, peupler toutes les tables (`Facts`, `Observations`, `Mental_Models`, `Mod_KV`), tester le fork mi-partie *avant* `rewind(8)`, et fournir une 3e réponse au mock LLM dans `test_session_epoch_bump_and_stale_worker_discard`.
   - Mettre à jour `README.md` et `ARCHITECTURE.md` pour supprimer les commandes/fichiers fictifs et refléter l'architecture réelle.

