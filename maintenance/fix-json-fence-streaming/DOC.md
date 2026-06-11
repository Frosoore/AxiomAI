# Fix : JSON visible dans le chat (fences backticks)

Le filtre de streaming du chat masque désormais les blocs d'état JSON quel que soit le style
de fence employé par le modèle (`~~~json … ~~~` ou ``` ```json … ``` ```), à l'image de ce que
le parseur moteur acceptait déjà. Limitation connue : un JSON émis **sans aucune fence** par
le modèle reste visible pendant le stream (le parseur moteur le retire de l'historique, donc
il disparaît au rechargement) — non traité ici car rare et coûteux à filtrer en streaming.
