# Changelog - Rework Mode Companion

* Initialisation du dossier et rédaction de la documentation d'intention.
* Refactorisation de `ArbitratorEngine` (`axiom/arbitrator.py`) pour traiter les tours via un `Action Pool` (remplacement de `user_message` par un dictionnaire d'`intents`).
* Adaptation de `build_narrative_prompt` (`axiom/prompts.py`) pour inclure dynamiquement la liste des acteurs et séparer clairement leurs intentions, évitant les conflits narratifs.
* Injection du contexte de localisation et des chunks RAG dans `build_hero_decision_prompt` pour offrir au héros des mémoires et un environnement tangibles.
* Restructuration de `axiom/session.py` : introduction d'un pool d'intentions (`submit_intent`, `resolve_tick`) et retro-compatibilité de `take_turn`.
* Adaptation de `core/multiplayer_queue.py` pour transmettre les actions sous forme de dict `intents`.
* Correction et mise à jour de l'ensemble des tests (passage de 54 tests avec succès) pour valider la transition sans régressions.
* Finalisation des tests unitaires (`tests/test_prompt_builder.py`, `tests/test_phase6.py`) pour la prise en compte de la signature `intents: dict` et l'assertion du bloc `[SIMULTANEOUS ACTIONS FOR THIS TICK]`. Tous les 387 tests du projet passent au vert.
* Révision du `HERO_SYSTEM_PROMPT` pour empêcher l'IA Compagnon de confondre son identité avec celle du joueur (le "you" du narrateur) et vol d'interactions.
* Renforcement des règles du `NARRATOR RULES` (interdiction stricte de hijack de joueur/compagnon et remplacement de la règle de non-répétition par une règle de "Continuité") pour corriger l'effacement des actions des joueurs dans la génération finale.
* Augmentation de `max_tokens` (de 100 à 300) dans `_get_hero_decision` (`axiom/session.py`) pour éviter que la réponse du Compagnon (HERO INTENT) ne soit coupée en plein milieu.
* Résolution du problème d'effacement de l'action du joueur en mode Companion. Les acteurs sont désormais explicitement identifiés (Player vs Companion) dans les `NARRATOR RULES` afin que le LLM n'ignore plus les inputs du joueur.
* Modification du système d'historique dans `build_hero_decision_prompt` : l'historique est désormais injecté sous forme de texte brut ("Narrator: ...", "Player: ...") et les règles du `HERO_SYSTEM_PROMPT` ont été drastiquement durcies pour empêcher l'IA du héros de se prendre pour le narrateur en résolvant l'action du joueur.
* Résolution du problème d'invisibilité du Compagnon dans la narration. Les identifiants (souvent des UUIDs) passés dans l'intent (`[uuid] INTENT: ...`) empêchaient le Narrateur de comprendre qui accomplissait l'action. `ArbitratorEngine.process_turn` a été modifié pour récupérer et injecter les vrais noms des entités (`[Elara] INTENT: ...`). De plus, la règle du Narrateur a été mise à jour pour forcer le "tissage" narratif (`Weave ALL the actors' intents... Describe them performing their intended actions together`).
* Désambiguïsation du pronom "Je" (I) : Comme le joueur et l'IA du compagnon écrivent souvent leur intention à la première personne, le LLM narrateur croyait qu'il s'agissait d'une seule et même personne. Une instruction stricte a été ajoutée dans `build_narrative_prompt` pour forcer la traduction : "Je" venant du joueur devient "Vous" (You), et "Je" venant du compagnon devient son vrai nom à la troisième personne (ex: "Elara").
