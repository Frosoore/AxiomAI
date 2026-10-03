# TODO — Phase 2 : vrai déplacement des fonctionnalités dans leurs mods

Décisions du propriétaire (2026-10-03) : déplacer les 5 fonctionnalités **et leurs satellites** (le tour
`arbitrator.py` reste dans le noyau pour l'instant) ; le noyau gère les données d'un mod **décoché** au
rewind/fork en exécutant **uniquement son code de stockage** (`storage.py` déclaré au manifeste) ;
`axiom.providers` = **seule source** du LLM (ajouté au safe mode).

Règle : une case ne se coche qu'avec un test qui prouve le comportement (et la suite verte).

## 0. Infrastructure du noyau
- [x] `[storage]` `custom` : gestionnaires `rewind` / `fork` / `snapshot` désignés dans le manifeste (`"storage:fonction"`), chargés pour **tout mod installé** (même décoché), sans exécuter le reste du mod
- [x] Ordre du registre = ordre de déclaration (ids remappés entre tables : Facts → Observations → Mental_Models)
- [x] Fin de tour : capture `snapshot` de chaque stockage déclaré (même mod décoché) ; mutations des mods par `batch.stage_op(fn)` (plus d'inventaire / modificateurs / chronologie codés dans `turn_batch.py`)
- [x] Données de save éditables (`materialize_state`, export/import TOML, `apply_correction`, diff) : **sections** déclarées par les mods (`section` + `state`/`load`/`diff` dans `[storage]`), exécutées mod décoché ou non ; le noyau n'a plus de SQL des fonctionnalités (`test_kernel_holds_no_feature_data_logic`)
- [x] Le noyau n'importe plus aucun module de fonctionnalité (contrôle automatique `test_engine_has_no_forbidden_imports`)

## 1. Fonctionnalités
- [x] `axiom.illustrations` ← `axiom/image_generator.py`
- [x] `axiom.time` ← `time_system.py`, `chronicler.py` (+ calendrier à la compilation via hook `axiom.universe:compile/decompile`)
- [x] `core.stat_dynamics` ← `stat_dynamics.py`, `modifiers.py`
- [x] `axiom.inventory` ← `inventory.py`
- [x] `axiom.living_memory` ← `living_memory.py`, `facts.py`, `observations.py`, `mental_models.py`, `consolidate.py`, `factextract.py`, `reflect.py`, `missions.py`

## 2. Fournisseur d'IA (M8)
- [x] LLM de narration uniquement via `axiom.providers` (plus de repli du noyau) ; message clair sans fournisseur (`test_providers_required_for_narration_with_clear_error`)
- [x] `axiom.providers` dans le safe mode (`test_minimal_chat_mod.py`)

## 3. Sortie structurée (M5)
- [x] Chaque mod contribue son champ (sous-schéma + consigne) ; plus de schéma en double ni d'inventaire codé en dur (`test_m5_structured_output_dynamic_fields`)

## 4. Vérifications
- [~] Chaque mod décoché : ses contributions au tour ne sont plus enregistrées (`test_disabled_mod_not_executed_during_turn`, qui ne joue pas de tour) ; UI/web/workers passent par les services des mods (vérifié dans le code)
- [x] Décoché puis rewind/fork puis recoché : données cohérentes — test (`test_disabled_mod_rewind_fork_and_reactivation_consistency`)
- [x] Suite complète verte (3 lots : 1 245 + 45 + 8 = 1 298 tests verts) ; Python 3.11 : compilation + imports validés
- [x] `export_engine` / `check_headless` : le noyau seul ne contient plus ces modules (0 violation)
