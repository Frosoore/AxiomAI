# TODO — Audit et alignement de l'encapsulation et détachement total des mods

- [x] Audit exhaustif des mods officiels et de leur degré de couplage au noyau
- [x] `axiom.sillytavern` : suppression du code de repli redondant dans le noyau (`core/st_parser.py`) ; délégation stricte au mod et erreur explicite si désactivé
- [x] `axiom.illustrations` : transfert du code canonique (`ImageGenerator`) dans `mods/axiom.illustrations/image_generator.py` ; rétrocompatibilité propre
- [x] `axiom.inventory` : transfert du code canonique d'arbre d'objets dans `mods/axiom.inventory/inventory.py` ; rétrocompatibilité propre
- [x] `axiom.time` : transfert du code canonique dans `mods/axiom.time/time_system.py` ; rétrocompatibilité propre
- [x] `core.stat_dynamics` : transfert du code canonique dans `mods/core.stat_dynamics/stat_dynamics.py` ; rétrocompatibilité propre
- [x] `axiom.living_memory` : transfert du code canonique dans `mods/axiom.living_memory/living_memory.py` ; rétrocompatibilité propre
- [x] Maintien de l'étanchéité headless du moteur `axiom/` (D-8, `check_headless`) avec imports dynamiques via `importlib` dans les shims de rétrocompatibilité
- [x] Re-génération et packaging de l'ensemble des archives `.axmod` et synchronisation des empreintes SHA-256 dans `dist/mods/store_index.json`
- [x] Validation de toutes les suites de tests unitaires, d'intégration, de packaging et d'intégrité
