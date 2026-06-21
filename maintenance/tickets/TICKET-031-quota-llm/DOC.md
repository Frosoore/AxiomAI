# TICKET-031 — Résilience aux quotas LLM (429) — DOC

Trois mécanismes, tous dans le backend Gemini (donc valables pour TOUT appel LLM) :

1. **Retry intelligent** : sur `429 RESOURCE_EXHAUSTED`, l'appel attend le délai que
   Google indique lui-même dans l'erreur (ex. « retry in 32s ») et réessaie (3 fois max).
   Dans la plupart des cas, un Populate free tier passe désormais tout seul, juste plus
   lentement.
2. **Ralentisseur** (Réglages → Gemini → « Requêtes max / minute ») : espace les appels
   pour ne jamais taper le plafond. Free tier = 10/min par modèle → mettre 9. 0 = illimité.
3. **Modèle de secours** (Réglages → Gemini) : si le quota du modèle principal reste
   épuisé, on bascule sur ce modèle (les quotas sont par modèle).

En plus, le Populate d'entités enregistre maintenant **au fil de l'eau** (chunk par chunk) :
si ça s'arrête quand même, ce qui est généré est gardé, et relancer le Populate reprend où
il s'était arrêté (les entités déjà connues sont ignorées).
