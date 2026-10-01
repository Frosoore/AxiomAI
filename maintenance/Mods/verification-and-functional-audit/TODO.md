# TODO — Vérification & Audit Fonctionnel et Déconnexion des Mods

- [x] 1. Inventaire exhaustif des mods dans `mods/` et de leurs points d'attachement (hooks, slots, services, patches, UI)
- [x] 2. Audit de déconnexion du core (`axiom/`, `core/`, `ui/`, `workers/`, `web/`) :
    - [x] Vérifier qu'aucun code métier résiduel/doublon n'est exécuté en dur dans le core (suppression de `_apply_inventory_change` résiduel, suppression des fallbacks de mutation en dur dans `step_5_arbitrate_rules`)
    - [x] Vérifier le comportement quand chaque mod est désactivé (détachement total, zéro overhead, pas de fallback silencieux pour `axiom.world`, `axiom.time`, `axiom.living_memory`, `axiom.rag`, `core.stat_dynamics`)
    - [x] Vérifier l'absence d'imports statiques directs vers `mods.*` dans le micro-noyau headless (`axiom/`)
- [x] 3. Audit fonctionnel mod par mod :
    - [x] Vérifier que chaque mod change réellement quelque chose (non silencieux, non factice)
    - [x] Analyser la solidité du code et repérer tout code inutile/obsolète
    - [x] Corriger le cas de `community.survival` : ajout de `build_survival_prompt_section` sur `axiom.turn:prompt_sections`, écoute de `axiom.step:after_step` pour consigner la fatigue physique sur efforts prolongés (>= 120 min), re-packaging de l'archive .axmod et mise à jour sha256 dans `store_index.json`
- [x] 4. Corrections ciblées des anomalies constatées :
    - [x] Dynamisation du bootstrap dans `Session.__init__` et `main_web.py` avec `bootstrap_all_mods`
    - [x] Sécurisation de `main_web.py` (/api/store/install respecte désormais le paramètre `dest` sans écraser `mods/community.survival` local)
    - [x] Ajout de la méthode `has_service` sur `KernelRegistry`
    - [x] Prise en compte de `config.disabled_mods` dans `is_mod_enabled`
- [x] 5. Validation par tests automatisés de non-régression et d'effectivité :
    - [x] Création de `tests/test_mods_decoupling_and_effectivity.py` (7 tests dédiés à la déconnexion stricte et à l'effectivité des mods)
    - [x] 157 tests unitaires et d'intégration mods & kernel 100% verts
