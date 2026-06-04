---
name: project-engine-split-strategy
description: Stratégie moteur/app d'AxiomAI — mono-repo, pas de split physique avant reprise solo, migration features = chantier des piliers
metadata:
  type: project
---

**Décision (2026-06-04) : rester en MONO-REPO** avec séparation *logique* (`axiom/` = moteur headless
zéro Qt ; `ui/`+`workers/` = app). **Pas de split physique** en deux packages (`axiom-engine/` +
`axiom-app/`) ni de `pip install` pour l'instant → c'est **TICKET-009, différé**.

**Why:** le code va être rendu au **possesseur originel**, qui ajoute des features **côté GUI** (via
Gemini CLI) sans se soucier de l'archi, **en parallèle** du travail moteur. Un split physique
n'empêcherait pas l'éparpillement de logique côté app, ajouterait une frontière deux-packages +
install editable qu'un dev non-archi (et Gemini CLI) casserait, et créerait un churn de merge maximal.
Le split sert la *distribution*, pas la *coordination*.

**État réel du moteur :** seul le cœur de simulation + la boucle de tour est dans `axiom/` (+ Session,
CLI `play`, backends, prompts, memory, config). **Restent côté app** (Qt, à migrer plus tard) :
Populate/CreatePlayerEntity (`workers/db_tasks.py`), regenerate, mini-dico, timekeeper, chronicler_worker,
et `core/multiplayer_queue.py` (encore Qt). La migration features app→engine est un **chantier étalé
sur les piliers** (Populate ↔ Pilier 2 Universe-as-Code → `axiom/compile.py`), pas du Pilier 1.

**How to apply:**
- Ne PAS proposer/faire le split physique tant que le repo n'est pas repris en solo et que les features
  ne sont pas migrées. Le `pip install axiom-engine` = bien plus tard.
- Règle de migration : une seule source de vérité par feature. Logique dans `axiom/`, worker Qt =
  coquille fine (template : `NarrativeWorker`/`VectorWorker`). Jamais d'import `axiom/` → `ui/`/`workers/`
  (casse le headless). Si un helper manque côté moteur, le déplacer dans `axiom/` (cf. `db_helpers`).
- L'état mixte (features neuves dans l'engine, anciennes encore en workers) est sain : dépendance à
  sens unique app→engine. Voir [[feedback-user-handles-git]] (l'utilisateur gère ses commits).
- Répartition du travail : l'utilisateur fait le fonctionnel (porter le moteur, format `.axiom`, piliers) ;
  le possesseur fait les features GUI. Synchroniser les refontes/migrations entre ses lots.
