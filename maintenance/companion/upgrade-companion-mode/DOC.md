# Amélioration du Mode Compagnon / Fondations Multijoueur

## Objectif
Enrichir le contexte décisionnel de l'IA héroïque (mode Companion) et la narration en injectant l'historique complet des intentions des différents acteurs ainsi que le profil/backstory du joueur.

## Décisions techniques
1. **Historique d'intentions unifié (`_load_history`)** : Groupement des événements de l'Event Log par `turn_id` pour fusionner les intentions simultanées (`user_input` + `hero_intent`) sous le même message de rôle `user` dans l'historique conversationnel du LLM.
2. **Contextualisation du Héros (`_get_hero_decision` & `build_hero_decision_prompt`)** :
   - Injection du nom et du profil du joueur (`player_persona`).
   - Remplacement de la vue restreinte des stats du héros par un bloc de stats consolidé contenant le joueur et les NPCs à proximité immédiate (même localisation), offrant à l'IA une perception claire de la situation tactique (ex: soigner si le joueur est blessé).
3. **Narration améliorée (`process_turn`)** : Récupération du `player_persona` à la volée depuis la table `Saves` pour enrichir la narration globale générée par l'arbitre principal.
