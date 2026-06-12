# DOC — TICKET-055 : CLI moteur en anglais

## Objectif
Le CLI `axiom` (commande console du wheel `axiomai-engine`) doit parler **anglais** : c'est une
surface dev-facing d'un moteur publié internationalement. Ce n'est PAS de l'i18n (un CLI dev = anglais).

## Périmètre
- **Traduit** : tout le texte vu par l'utilisateur du CLI (`help=`, `description=`, `print(...)`,
  `.write(...)`, prompts) dans `axiom/cli/*.py`.
- **Pas touché** : commentaires et docstrings internes (restent en français, comme le reste du code).

## Règle pour la suite
- Tout nouveau message du CLI s'écrit **en anglais**.
- Voir TICKET-056 (PENDING) pour les messages français encore émis par le moteur (events `dev`,
  exceptions) et surfacés par le CLI.
