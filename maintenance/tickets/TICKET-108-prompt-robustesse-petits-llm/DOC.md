# DOC — TICKET-108 : Robustesse des petits LLM (Stheno / Gemma / KoboldCPP)

## Objectif
Résoudre les problèmes majeurs de cohérence narrative, d'usurpation d'agence et de redondance de prompt observés sur les petits modèles locaux (8B/9B, ex: Stheno v3.4 sous KoboldCPP) :
1. L'IA parle et agit à la place du joueur (injonction contradictoire dans le `CRITICAL REMINDER` et la règle `CONTINUITY`).
2. Les macros de cartes (`{{char}}` / `{{user}}`) ne sont pas substituées dans le Lorebook / fiches de personnages.
3. RAG réinjecte dans `RELEVANT MEMORIES` le tour précédent déjà présent dans l'historique `messages`, gaspillant des tokens et créant un écho d'erreurs de formatage (guillemets).
4. Le schéma d'état JSON pollue le prompt narratif principal alors qu'un appel séparé (Timekeeper) résout le temps.
5. Manque du sampler `min_p` pour stabiliser l'échantillonnage sous KoboldCPP.
