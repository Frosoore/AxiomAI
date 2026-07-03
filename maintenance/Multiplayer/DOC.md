# DOC — Mode Multijoueur simultané

**Objectif.** Plusieurs entités de type `player` agissent dans le **même tour**, sur une **seule machine**
(hotseat local). Les intentions sont accumulées via le sélecteur de joueur existant, puis résolues
**simultanément** en un seul tick de l'arbitre, produisant une narration unique à la **troisième personne**.

**Ce n'est PAS** du multijoueur réseau (pas de serveur, pas de clients distants). Réseau = chantier futur.

**Pourquoi c'est faisable simplement.** Le moteur est headless, a une seule base autoritaire, résout un
tour à la fois, et l'arbitre accepte déjà un `intents: dict{acteur → texte}`. On réutilise le patron du
mode Companion (accumulation d'intents → résolution globale).

**Décisions clés** (voir en-tête `PLAN.md`) : implémenteur = Claude ; spatial v1 simple (joueur primaire
+ ajout des positions des autres) ; mode toujours proposé au menu.

**Usage prévu.** Créer une save en mode `Multiplayer` → ouvrir le Creator Studio pour y ajouter les
personnages joueurs → jouer : chaque joueur saisit son action à tour de rôle, la résolution part quand
tous ont validé.
</content>
