# Tickets 092→098 (2026-09-22)

**Objectif.** Solder les tickets ouverts par `maintenance/qa/qa-post-17h59-2026-09-22/` sans décision
utilisateur, sauf TICKET-096 (verbosité : l'utilisateur a choisi `balanced`).

**Décisions techniques.**
- Web : pas de jeton CSRF (il aurait fallu modifier le front) → garde serveur `Host` + `Origin`/`Referer`
  + Content-Type JSON. Un navigateur envoie toujours `Origin` sur un POST cross-origin, y compris un
  formulaire multipart, donc la règle « aucun des deux en-têtes → accepté » ne laisse passer que les
  clients hors navigateur (curl, tests).
- `canonical_verbosity(value, default=None)` : le défaut utilisateur (config) est passé par l'appelant
  (Studio, tabletop, web) ; sans `default`, repli sur `axiom.prompts.DEFAULT_VERBOSITY_LEVEL`.
- `ActionQueue` non supprimée : API publique du paquet `axiomai-engine` + tests existants.
- Inventaire historique non fait : pas d'historique dans le schéma (voir TICKET-095).
- Inventaire (TICKET-095) : snapshots par tour plutôt que rejeu d'`Event_Log` — les éditions manuelles
  ne sont pas journalisées et l'`instance_id` créé par un `add` n'est pas stocké, donc le rejeu serait
  faux. Une ligne par tour **même vide**, car l'absence de ligne doit signifier « inconnu » (tours
  d'avant la mise à jour → on ne touche à rien), pas « inventaire vide ».
