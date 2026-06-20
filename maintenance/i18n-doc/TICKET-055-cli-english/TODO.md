# TODO — TICKET-055 : CLI moteur en anglais

Le CLI `axiom` (publié dans le wheel `axiomai-engine`) a son texte user-facing codé en **français**
(historique : outil interne de devs francophones). Le moteur étant publié et « parlant anglais »
(cf. TICKET-054), son CLI doit l'être aussi. **Ce n'est PAS de l'i18n** : un CLI dev = anglais, point.

Périmètre : **uniquement les chaînes vues par l'utilisateur** (`help=`, `description=`, `print(...)`,
`input(...)`, messages d'erreur affichés). On NE touche PAS aux commentaires / docstrings internes
(cohérence avec le reste du code francophone).

## Fichiers à traduire (lire en entier — du français sans accent échappe au grep)
- [x] `axiom/cli/main.py` — description racine + 14 `help=` de sous-commandes.
- [x] `axiom/cli/play.py` — args + messages + boucle de jeu (commandes slash, erreurs).
- [x] `axiom/cli/compile_cmd.py` — compile / pack / import / dev / decompile.
- [x] `axiom/cli/populate_cmd.py` — help + messages.
- [x] `axiom/cli/saves_cmd.py` — save-show/export/import/fork/edit/pack/unpack.

## Validation
- [x] `grep` : plus aucune chaîne user-facing française dans `axiom/cli/`.
- [x] `axiom --help` en anglais, sans régression.
- [x] Tests verts (offscreen) : 157 passed (4 assertions FR de tests mises à jour).

## Hors périmètre (ticketé)
- [ ] TICKET-056 : français encore émis par le MOTEUR (event `axiom dev`, exceptions) et surfacé
      par le CLI. Chantier distinct (impacte des tests qui assertent le FR).
