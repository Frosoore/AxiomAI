# Changelog - Upgrade Companion Mode

- Initialisation de l'étape d'amélioration du mode Compagnon.
- Déclaration des fichiers cibles dans la coordination de dev parallèle (`EN_COURS.md`).
- Récupération du nom et de la biographie du joueur (`player_persona`) depuis la table `Saves` dans `ArbitratorEngine.process_turn` pour les passer au prompt de narration principal.
- Refonte de la récupération de l'historique dans `Session._load_history` pour grouper les événements par `turn_id` et y intégrer les intentions de compagnons (`hero_intent`), permettant au héros de garder une cohérence narrative avec ses propres actions passées.
- Enrichissement de `_get_hero_decision` dans `Session` pour y inclure le contexte du joueur (`player_name`, `player_persona`) et les statistiques de toutes les entités locales pertinentes (joueur et NPCs proches).
- Adaptation de `build_hero_decision_prompt` pour recevoir ces paramètres supplémentaires et formater le bloc de statistiques avec un titre dynamique adapté.
- Résolution du problème d'attention/narrateur (biais binaire "you two") :
  - Extraction de la liste des personnages présents à la même localisation que le joueur.
  - Ajout dynamique d'une règle "- Group Awareness" dans les NARRATOR RULES listant toutes les entités locales présentes et interdisant formellement au narrateur de les ignorer ou de s'adresser à eux en tant que duo ("you two") si 3 personnes ou plus sont réunies.
  - Ajustement du message système final (recency bias reminder) pour y injecter un rappel explicite de présence de groupe et le verbe de tissage approprié ("BOTH" vs "ALL").
- Correction d'un bug de résolution d'entité de joueur : Remplacement des recherches de localisation basées sur la clé fixe `"player"` par le `player_entity_id` résolu dynamiquement (ex: `"player1"` dans les environnements de tests).
- Ajout de cas de tests unitaires complets dans `tests/test_session.py` (`test_load_history_with_hero_intent`, `test_get_hero_decision_passes_player_context_and_stats`) et dans `tests/test_arbitrator.py` (`test_process_turn_injects_player_persona`, `test_process_turn_injects_group_awareness`).
- Validation réussie de l'intégralité de la suite de tests unitaires sans aucune régression.
