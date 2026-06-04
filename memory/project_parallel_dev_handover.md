---
name: project-parallel-dev-handover
description: Situation de collaboration AxiomAI — handover au possesseur (features GUI via Gemini CLI) + dev parallèle ; conseils d'opération
metadata:
  type: project
---

**Situation.** Le code va être **rendu au possesseur originel**, qui va continuer à développer **en
parallèle** de l'utilisateur (mon interlocuteur). Répartition :
- **Possesseur** : ajoute des **features côté GUI**, via **Gemini CLI**, sans se soucier de comment
  c'est fait — il regarde seulement le comportement côté interface.
- **Utilisateur (moi/lui)** : le **fonctionnel** — porter le moteur, changer le format `.axiom`, les
  piliers. Travaille dans `axiom/`.

**Risques de cette config :**
- Le possesseur va naturellement **éparpiller de la logique dans `ui/`/`workers/`** (c'est ce qu'il
  voit). Cible mouvante quand l'utilisateur migre, lui, de la logique vers `axiom/`.
- **Churn de merge** : éviter toute grosse refonte structurelle pendant la phase parallèle.
- Gemini CLI peut casser la frontière headless (import retour `axiom -> ui/workers`).

**Garde-fous mis en place (2026-06-04) :**
- `ARCHITECTURE.md` à la racine : règles + où mettre les features + table « code non encore migré » +
  carte ancien→nouveau chemin. **Écrit surtout à l'intention de Gemini CLI / du possesseur.**
- `tests/test_engine_headless.py` : détecte automatiquement un import retour qui chargerait Qt dans `axiom/`.

**How to apply (pour mes prochaines sessions) :**
- **Minimiser le churn structurel** tant que le dev est parallèle : pas de split physique (cf.
  [[project-engine-split-strategy]]), pas de déplacements massifs de fichiers sans point de synchro.
- **IMPÉRATIF — tenir à jour la table « non migré » d'`ARCHITECTURE.md`** : dès que je porte une
  feature app→engine, **retirer sa ligne** ; si j'ajoute une logique côté app en attendant, l'ajouter.
  Cette table est la source de vérité du reste-à-migrer ; périmée, elle fait porter du code déjà porté
  ou ignorer du code à porter. La mise à jour fait partie de la migration, pas optionnelle. Suivre le
  patron coquille (`NarrativeWorker`).
- S'attendre à trouver de la **logique éparpillée** ajoutée par le possesseur dans `ui/`/`workers/` ;
  le rôle de l'utilisateur est de la **rapatrier dans `axiom/`** entre les lots du possesseur.
- Vérifs rapides après toute modif moteur : `pytest tests/test_engine_headless.py tests/test_cli_play.py`
  + `debug/startup_check.py`.
- **Ne pas toucher à git** (commits/branches gérés par l'utilisateur — [[feedback-user-handles-git]]).
