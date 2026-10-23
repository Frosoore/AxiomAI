# DOC — feature-ai-understanding-stats-setup

## Objectif

Permettre au modèle d'arbitrage narratif (LLM) de recevoir, comprendre et interpréter fidèlement les données créées par l'auteur d'univers et le joueur dans les onglets du Studio :
1. **Story Setup** : Les réponses du joueur au début de la partie (questions d'origine, motivation, métier...) étaient jusqu'alors oubliées après le tour 0. Elles sont désormais injectées de manière persistante comme prémisses de l'histoire.
2. **Stats (Stat_Definitions)** : Les statistiques étaient injectées sous forme de nombres bruts sans bornes ni descriptions. L'IA reçoit désormais la signification des statistiques de l'univers, leurs bornes (min/max, ex: 85/100) et la consigne de respecter ces échelles.
3. **Entités (Description)** : La description narrative des entités présentes dans la scène (rédigée dans l'onglet Entités) est maintenant transmise à l'IA avec leurs statistiques.
