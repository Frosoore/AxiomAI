# TICKET-033 — Retries visibles + annulation des générations — DOC

Pendant une génération LLM (Populate, preview, canonisation) :
- si un quota 429 force une attente, la **barre de statut** affiche un compte à rebours
  vivant : « Quota exhausted (gemini-2.5-flash-lite) — attempt 1/3 — retry in 27s » ;
- un bouton **« ✖ Annuler la génération »** apparaît à droite de la barre de statut tant
  qu'une génération tourne. L'annulation est *coopérative* : effective immédiatement
  pendant une attente, sinon à la prochaine frontière (fin du chunk en cours) — le
  travail déjà enregistré est conservé (relancer le Populate reprend, comme pour le 429).
  Une prévisualisation annulée ne laisse rien : la sandbox est supprimée.

Mécanique : hooks neutres `on_status`/`cancel_event` sur le backend (zéro Qt), registre
process-wide des tâches annulables côté workers, bouton MainWindow qui ne fait que
consulter ce registre (aucune vue à câbler).
