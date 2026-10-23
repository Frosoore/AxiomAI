# CHANGELOG — feature-ai-understanding-stats-setup

## [Complété]

- **Story Setup (`axiom/arbitrator.py`, `axiom/prompts.py`)** :
  - Extraction dans `step_1_gather_context` des réponses consignées à la création de partie (`Event_Log` `setup_answer`) corrélées aux questions de `Story_Setup`.
  - Stockage dans `TurnContext.setup_answers`.
  - Nouvelle fonction pure `format_story_setup_block` dans `axiom/prompts.py`.
  - Injection structurée sous `STORY SETUP & PREMISES:` dans le system prompt narratif (juste après le background du joueur), rappelant à l'IA d'honorer et tisser ces choix dans la trame.
- **Stats (`axiom/arbitrator.py`, `axiom/prompts.py`)** :
  - Extraction de `Stat_Definitions` (`stat_id`, `name`, `description`, `value_type`, `parameters`).
  - Nouvelle fonction pure `format_stat_definitions_block` dans `axiom/prompts.py` : injection du bloc `DEFINED STATS & SCALES:` avec description et échelles/bornes (`[min..max]`, `[min X]`, etc.) et instruction de respecter ces règles d'échelle lors des mutations.
  - Enrichissement de `format_entity_stats_block` : affichage des bornes numériques pour les entités (ex: `Health: 85/100`, `Sanity: 10 [-100..100]`).
- **Entités (`axiom/arbitrator.py`, `axiom/prompts.py`)** :
  - Extraction de `Entities.description` pour les entités actives / de scène.
  - Affichage direct de `Description: ...` sous le nom de l'entité dans `format_entity_stats_block`, donnant à l'IA le profil et la personnalité exacte des PNJ présents dans la scène.
- **UI Qt Tabletop (`mods/axiom.ui.qt/ui/tabletop_view.py`)** :
  - Rechargement de `_setup_answers` depuis `Event_Log` lors de la reprise d'une sauvegarde existante si non fourni à l'ouverture.
- **Tests (`tests/test_ai_understanding_stats_setup.py`)** :
  - 10 nouveaux tests unitaires et d'intégration validant le formatage, l'ordre des sections du prompt, et la collecte complète de contexte par l'Arbitrator. Suite à 10/10 vert.
