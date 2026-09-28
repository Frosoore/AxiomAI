# Documentation — Phase 0b : Unification de la fin de tour et assainissement des UIs

## Objectif
Résoudre les violations architecturales D4 (Interfaces privilégiées) et D5 (Logique dupliquée) :
1. **Pipeline de fin de tour unifié** : centraliser dans `Session._post_turn_pipeline` tout le travail post-narration (mises à jour métadonnées, living memory, ambiance).
2. **Composant Headless Living Memory** : déplacer la logique d'accumulation (`_FACT_PENDING`) et le déclenchement de distillation de `main_web.py` vers un composant headless pur Python dans `axiom/`.
3. **Tour 0 atomique et canonique** : déplacer le parsing de `first_message`, le split de variantes et la substitution des tags `@setup` dans `axiom.savestore.create_save`.
4. **Allègement des UIs** : `main_web.py`, `ui/tabletop_view.py` et `workers/narrative_worker.py` deviennent de purs contrôleurs sans logique métier dupliquée ni requêtes SQL ad-hoc.
