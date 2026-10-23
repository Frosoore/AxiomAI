# TODO — feature-ai-understanding-stats-setup

Compréhension, réception et interprétation par l'IA des informations des onglets du Studio (Stats, Story Setup, Entités).

- [x] 1. Extraction et contextualisation du Story Setup (`axiom/arbitrator.py`) :
  - Extraire les réponses aux questions de départ (`Event_Log` `event_type = 'setup_answer'`) et les associer aux questions réelles (`Story_Setup`).
  - Stocker dans `TurnContext.setup_answers`.
- [x] 2. Injection du Story Setup dans le prompt narratif (`axiom/prompts.py`) :
  - Ajouter la section `STORY SETUP & PREMISES` dans le prompt système (`build_narrative_prompt`).
  - Guider l'IA pour qu'elle respecte et intègre ces choix et antécédents tout au long de la partie.
- [x] 3. Enrichissement des Stats avec `Stat_Definitions` (`axiom/arbitrator.py`, `axiom/prompts.py`) :
  - Charger les définitions (`name`, `description`, `value_type`, `parameters` avec min/max) depuis `Stat_Definitions`.
  - Formater les valeurs d'entités avec leurs bornes (ex: `Health: 85/100`) dans `format_entity_stats_block`.
  - Injecter le bloc de référence `DEFINED STATS & SCALES` dans le prompt avec la consigne de respecter les échelles et de ne pas inventer de fausses stats.
- [x] 4. Enrichissement des Entités de scène avec leur description (`axiom/arbitrator.py`, `axiom/prompts.py`) :
  - Charger `Entities.description` pour les entités pertinentes de la scène.
  - Afficher la description dans `format_entity_stats_block`.
- [x] 5. Tests unitaires et validation complète (`tests/test_ai_understanding_stats_setup.py`) :
  - Vérifier la présence et le formatage du Story Setup, des bornes de stats, des définitions de stats et des descriptions d'entités.
  - S'assurer que tous les tests de la suite passent.
