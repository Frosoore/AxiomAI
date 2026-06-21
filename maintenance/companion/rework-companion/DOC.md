# Rework Intégral du Mode Companion & Multijoueur

## Vision & Objectif
Le "Mode Companion" n'est pas qu'une simple surcouche IA. Il doit servir de **fondation technique au futur mode Multijoueur**.
Cela implique que le moteur (`Session`, `Arbitrator`) doit être capable de gérer de multiples acteurs indépendants agissant simultanément dans le même univers, de manière robuste et sans conflit ("race condition").

## Constat d'échec de l'architecture actuelle
Aujourd'hui, l'architecture est du type "Ping-Pong Solo" :
1. Le joueur envoie un message.
2. Le système interroge le LLM Compagnon pour obtenir `[HERO INTENT]`.
3. Le système concatène tout dans le prompt Narrateur et résout "le tour du joueur".

**Pourquoi ça ne passe pas à l'échelle (Multijoueur) :**
- Si deux joueurs envoient une commande, le système actuel ferait deux résolutions narratives distinctes qui pourraient se contredire.
- Le Compagnon n'est pas un vrai "Acteur", il n'a pas d'existence propre en dehors de la requête du joueur local.

## Nouvelle Architecture : Action Pool & Tick Resolution

### 1. Le Modèle d'Acteur
Dans la nouvelle architecture, le Joueur, le Compagnon, et les Humains distants (plus tard) sont tous des "Acteurs" du point de vue du moteur.
Chaque Acteur peut prendre connaissance de l'état du monde (indépendamment) et décider de son intention.

### 2. L'Action Pool (`Session.submit_intent`)
Au lieu d'exécuter un tour immédiatement après un message, la `Session` recueille les intentions dans un Pool.
`Session.submit_intent("player_1", "J'attaque le gobelin.")`
`Session.submit_intent("kael_companion", "Je soigne le joueur.")`

### 3. Le Tick de Résolution (`Session.resolve_tick`)
Une fois que le quorum d'intentions est atteint (ex: le joueur et le compagnon ont tous deux validé leur choix), la session se verrouille et passe à la résolution globale :
- L'Arbitrator reçoit la liste structurée des intentions.
- Le LLM Narrateur résout la simultanéité ("*Pendant que Kael soigne le joueur, ce dernier parvient à blesser le gobelin...*").
- Un seul état du monde (`state_changes`) est généré.

### Avantages
- **Increvable :** Les conflits d'états disparaissent puisqu'il n'y a qu'une seule résolution par "Tick".
- **Scalable :** Ajouter un Joueur 2 ou un NPC autonome ne coûte rien structurellement, c'est juste un `submit_intent` de plus dans le Pool.

## Implémentation
- Déprécier la méthode `Session.take_turn`.
- Créer une nouvelle classe interne `TurnManager` ou gérer l'état `Pending_Intents` dans `Session`.
- Refondre `build_narrative_prompt` pour gérer un bloc `[INTENTIONS SIMULTANÉES]`.
