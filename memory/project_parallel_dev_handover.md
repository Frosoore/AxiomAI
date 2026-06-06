---
name: project-parallel-dev-handover
description: Situation de collaboration AxiomAI — handover au possesseur (features GUI via Gemini CLI) + dev parallèle ; conseils d'opération
metadata:
  type: project
---

**Situation (révisée 2026-06-05).** On passe d'une simple passation à un **dev parallèle à deux sur
branches Git séparées du même mono-repo**, tout le code écrit **exclusivement par des agents CLI**.
Répartition réelle désormais :
- **Utilisateur (Claude Code)** : **Pilier 2 — Universe-as-Code** (doc §7) → `axiom/compile.py`,
  migration `Populate*`, **changement du format `.axiom` / schéma** (annexe C.1).
- **Pote (Gemini CLI)** : **Pilier 5 — Le Temps comme substrat causal** (doc §6) → `axiom/time_system.py`,
  `workers/timekeeper_worker.py`, **migration des saves** (annexe C.2). C'est du **moteur**, pas du GUI
  (≠ ancien modèle « possesseur = features GUI » ci-dessous, qui peut redevenir vrai plus tard).

**🔴 Zone de collision des deux chantiers** (le reste des fichiers est disjoint) : `axiom/schema.py`,
le **numéro de version du format `.axiom`**, et **`Session` / la boucle de tour**. Conseil donné :
désigner **un propriétaire explicite** de ces 3 points et **séquencer** les changements de schéma
(jamais deux bumps concurrents). Un dossier de coordination ne protège PAS le code, juste les docs.

**Convention de coordination — CRÉÉE (2026-06-05) dans `maintenance/collab/` :**
- `collab/README.md` = rulebook canonique (règles de merge + snippet de prompt de départ). Stable,
  lu par les deux.
- `collab/claude/EN_COURS.md` (écrit seulement par Claude) + `collab/gemini/EN_COURS.md` (écrit
  seulement par Gemini) = « qui touche quels modules en ce moment ». **Chaque agent n'écrit que dans
  SON sous-dossier et lit celui de l'autre** → zéro conflit sur la coordination.
- Référencé depuis `maintenance/README.md` (section « Dev parallèle à deux »).
- **Pas de table de propriété des fichiers chauds** : l'utilisateur l'a retirée (2026-06-05) —
  « on verra après si besoin ». Seule règle gardée : pas deux refontes de format/schéma concurrentes.
  La zone de collision (`schema.py`/format `.axiom`, `Session`) reste réelle si jamais besoin d'arbitrer.

**Hygiène Git conseillée :** branches courtes, merge fréquent de `main` dans sa branche (petits
conflits réguliers plutôt qu'un gros), **`main` toujours vert** = ne merger que si
`pytest tests/test_engine_headless.py tests/test_cli_play.py` + `debug/startup_check.py` passent
(c'est le contrat partagé qui détecte qu'un casse l'autre), PR même à deux. [[feedback-user-handles-git]]
reste vrai : c'est l'utilisateur qui exécute les commits/branches/merges, pas moi.

---
**Ancien modèle (passation, peut redevenir d'actualité) :** le possesseur ajoute des **features GUI**
via Gemini CLI sans se soucier de l'archi ; l'utilisateur fait le fonctionnel dans `axiom/`.

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
