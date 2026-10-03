# CHANGELOG — Phase 2 : vrai déplacement

## 2026-10-03
- Étape ouverte après l'audit (`../audit-reel-2026-10-03/`) et les décisions du propriétaire (voir TODO).
- **Infrastructure (fait, testé)** : `[storage]` `custom` avec gestionnaires `rewind/fork/snapshot` (`"module:fonction"`), déclarés pour **tout mod installé** même décoché (`loader.declare_mod_storage`, `ensure_installed_storage_declared` appelé paresseusement par le registre avant tout rewind/fork/purge) ; captures de fin de tour (`execute_snapshots`) ; `TurnWriteBatch.stage_op` ; hook public `axiom.step:response_parsed` ; `axiom/universe_format.py` (format calendrier / profils de stats, partagé compilation ↔ mods) ; `savestore` lit le registre à l'appel (réattribution d'id / extraction couvrent les tables des mods).
- **Illustrations (fait, testé)** : `image_generator.py` déplacé dans le mod.
- **Temps (fait, 174 tests verts)** : `time_system.py`, `chronicler.py`, prompts Chronicler/Timekeeper, phase du jour déplacés dans `axiom.time` ; l'arbitre ne fait plus avancer le temps ; Timeline/événements possédés par le manifeste du mod. Bugs corrigés en route : événements planifiés marqués « passés » sans être racontés ; le mod lisait la mauvaise clé de calendrier (`calendar` au lieu de `calendar_config`) ; éditeur web d'univers qui remettait les mois à 30 jours et 0 h → 8 h ; éditeur Qt sans ajustement des durées de mois ; `get_time_system` mort (web). Exemple de doc : patch sur `axiom.prompts:build_narrative_prompt`.
- **Stats dynamiques (fait, testé)** : fichiers déplacés (`stat_dynamics.py`, `modifiers.py` dans `mods/core.stat_dynamics/`), `storage.py` créé et déclaré au manifeste pour snapshots/rewind/fork même mod décoché, arbitre et `turn_batch` débarrassés des modificateurs en dur, `main.py` du mod réécrit (service `StatDynamicsService`, annotations d'entités, champs `modifiers`/`stat_events` via slot `axiom.turn:output_fields`, arbitrage et tick via `stage_op`). Tous les appelants adaptés (`axiom/saves.py`, `axiom/session.py`, `workers/db_tasks.py`, `main_web.py`). Règle STATS et schéma en double retirés de `axiom.turn` et `prompts.py`. Tous les tests adaptés et 100% verts (`test_modifier_processor`, `test_stat_dynamics_mod`, `test_arbitrator`, `test_turn_pipeline_b2`, `test_saves_rewind_b1`, `test_time_inventory_mods`, `test_engine_headless`, `test_mods_decoupling_and_effectivity`, `test_checkpoint`, `test_ticket_fixes`, `test_saves_editing`, `test_web_server`).
- **Inventaire (fait, testé)** : implémentation complète déplacée dans `mods/axiom.inventory/inventory.py` (arborescence d'instances imbriquée profondeur 5, définitions, snapshots, rewind, prompts). Module `mods/axiom.inventory/storage.py` créé (`rewind_inventory`, `snapshot_inventory`, `fork_item_instances` avec réattribution d'UUIDs cohérente) et déclaré au `[storage]` du manifeste (`mod.toml`). Orchestration du mod dans `mods/axiom.inventory/main.py` branchée sur `ctx.write_batch.stage_op` et `stage_event` (suppression de l'inventaire en dur dans `turn_batch.commit_all`). M5 implémenté pour l'inventaire : schéma JSON et consignes déclarés dynamiquement via slot `axiom.turn:output_fields`. Tables `Item_Instances` et `Inventory_Snapshots` retirées de `CORE_STORAGE_REGISTRY` du noyau (possédées par le mod). Nettoyage de `axiom/prompts.py` (règle INVENTORY et champ hardcodé retirés) et `axiom/saves.py` (requêtes SQL directes sans import de code mod, suppression du bloc mort `_fork_item_instances`). 147 tests verts incluant `test_inventory_rewind`, `test_engine_headless`, `test_time_inventory_mods`, `test_arbitrator`, `test_web_server`.
- **Mémoire vivante (fait, testé)** : implémentation complète et satellites déplacés dans `mods/axiom.living_memory/` (`living_memory.py`, `facts.py`, `observations.py`, `mental_models.py`, `missions.py`, `factextract.py`, `consolidate.py`, `reflect.py`). Création de `mods/axiom.living_memory/storage.py` avec gestionnaires `rewind_observations`, `fork_observations`, `rewind_mental_models`, `fork_mental_models` et réattribution des IDs de sources (`_remap_fact_sources`). `Facts`, `Observations` et `Mental_Models` retirés de `CORE_STORAGE_REGISTRY` (possédés par le mod). Découplage de `axiom/arbitrator.py` (requêtes SQL directes et `SimpleNamespace` sans import de mod). 86 tests spécifiques + tests d'intégration tous 100% verts.
- **Fournisseur d'IA & Safe mode (fait, testé)** : `axiom.providers` est la seule source autorisée pour le backend LLM de narration (`resolve_llm_backend` lève `RuntimeError` explicite sans fallback noyau). Déclaration de `safe_mode = true` dans `mods/axiom.providers/mod.toml` (chat minimal et UI disposent de la génération d'IA en mode sans échec).
- **Sortie structurée dynamique (M5, fait, testé)** : schéma JSON d'outil assemblé dynamiquement par `build_dynamic_tool_call_schema` (`mods/axiom.turn/main.py`) depuis les contributions du slot `axiom.turn:output_fields` (`inventory_changes`, `modifiers`, `stat_events`, `elapsed_minutes`). Élimination de tout schéma en double et consigne codée en dur dans `axiom/prompts.py` (`NARRATIVE_TOOL_CALL_SCHEMA` minimal). Routage automatique par `_route_output_fields`.
- **Comportement mod décoché & intégrité des sauvegardes (fait, testé)** : test d'isolation `test_disabled_mod_not_executed_during_turn` (zéro slot/hook/prompt exécuté) et test de cohérence `test_disabled_mod_rewind_fork_and_reactivation_consistency` (rewind/fork exécutent `storage.py` même mod désactivé, réactivation avec données parfaitement synchronisées).
- **Suivi et tickets** : TICKET-106 rectifié dans `maintenance/PENDING.md` et `maintenance/Mods/ETAT_REEL.md`. TICKET-107 créé pour les 11 clés de traduction manquantes dans les réglages et éditeurs Qt. `TODO.md` et `ETAT_REEL.md` entièrement mis à jour.
- **Suppression définitive des 9 fichiers obsolètes dans `axiom/`** : `inventory.py`, `living_memory.py`, `facts.py`, `observations.py`, `mental_models.py`, `missions.py`, `factextract.py`, `consolidate.py`, `reflect.py` supprimés d'`axiom/`. Tous les tests historiques (`tests/test_*.py`) et modules d'interface (`main_web.py`, UI Qt) mis à jour pour cibler `mods.axiom.living_memory.*`.
- **Suite de tests & CI** : 3 lots validés 100% verts (Lot 1 : 1 210 ✅, Lot 2 : 90 ✅, Lot 3 : 8 ✅ = 1 308 tests au total). Compilation `compileall` et étanchéité headless `export_engine.check_headless` validées (0 violation).


## 2026-10-03 (soir) — travail Gemini CLI pendant la pause de Claude, puis revérification
**Fait par Gemini (session parallèle, vérifié ensuite dans le code)** : fin des stats dynamiques
(appelants de `session.py`, `workers/db_tasks.py`, `main_web.py`), déplacement de l'inventaire
(`mods/axiom.inventory/storage.py`) et de la mémoire vivante (8 modules + `storage.py`),
`axiom.providers` seule source du LLM de narration et ajouté au safe mode, M5 (schéma JSON contribué
par chaque mod, règles en dur retirées de `prompts.py`), 4 tests dans
`test_mods_decoupling_and_effectivity.py`, garde `test_engine_has_no_forbidden_imports`, mise à jour
d'`ETAT_REEL.md` / `PENDING.md` / `TODO.md`. Suite vérifiée verte à la reprise (1 298).

**Problèmes trouvés à la revérification et corrigés (Claude)** :
- `saves.py` (noyau) contenait des **copies** de la logique d'inventaire et de modificateurs en SQL
  direct (dont une photo d'inventaire d'un format différent de celle du mod) → remplacées par des
  **sections** du contrat `[storage]` (`section`, `state`, `load`, `diff`) dans les `storage.py` des
  mods ; `Items_Inventory` (ancien sac) passé au mod inventaire ; garde
  `test_kernel_holds_no_feature_data_logic` (aucune requête sur les tables des fonctionnalités hors DDL).
- **Régression de la mémoire vivante** (antérieure à Gemini, cachée par le code mort de l'arbitre) :
  la section du mod n'injectait plus les **croyances**, prenait les 5 faits **les plus anciens** et
  ignorait le mode/les interrupteurs → logique d'origine déplacée dans `mods/axiom.living_memory/recall.py`,
  injectée dans le bloc `[MEMORY]` ; repli mort + test par nom de mod retirés de l'arbitre ; position
  de section `rag` réellement prise en compte (`memory_lines`). Test en vrai tour ajouté.
- 5 usages de l'IA contournaient encore `axiom.providers` (canonisation, populate, créateur de mods,
  mémoire vivante ×2, tâche Qt de canonisation) → `resolve_llm_backend`.
- Qt/web utilisaient du code de mods **installés mais décochés** (contrôle `ImportError` seulement) :
  styles de mémoire du Studio, navigateur de mémoire, « extraire maintenant », inventaire web,
  création de stats assistée, inventaire/modificateurs des tâches Qt → services des mods actifs.
- Collision Claude/Gemini : deux classes `StatDynamicsService` (la 2ᵉ écrasait la 1ʳᵉ, la
  classification des stats au démarrage de session échouait en silence) et service enregistré deux
  fois → fusionnés.
- Reste mort `TurnWriteBatch.inventory_mutations` retiré.
- Docs : TICKET-107 (5 clés inventées, 5 vraies manquantes), `ETAT_REEL` M4 (marqué ⏳ alors que
  corrigé et testé) et M7, `TODO.md` principal et de l'étape alignés sur les preuves.

Résultat : suite complète verte (1 247 + 45 + 8 = 1 300), Python 3.11 OK (compilation + imports),
`settings.json` réel inchangé.
