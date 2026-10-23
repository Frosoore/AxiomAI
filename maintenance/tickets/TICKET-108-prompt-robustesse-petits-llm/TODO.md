# TODO — TICKET-108 : Robustesse des petits LLM (Stheno / Gemma / KoboldCPP)

- [x] 1. Prompt Narrateur & CRITICAL REMINDER : corriger l'usurpation du joueur (`translate 'I' to 'You'`, règle `CONTINUITY`, consignes de perspectives et de non-invention d'actions/dialogues joueur).
- [x] 2. Macros `{{char}}` et `{{user}}` : remplacement systématique dans l'import SillyTavern (`workers/import_export_worker.py`) et dans le formatage du lorebook (`axiom/prompts.py`).
- [x] 3. Anti-duplication RAG : exclure de la recherche vectorielle les tours déjà présents dans l'historique de conversation (`history`), évitant la double injection et le renforcement des erreurs de formatage.
- [x] 4. Allègement du schéma JSON & Timekeeper : épurer les règles du prompt narratif pour les petits modèles et éviter la redondance avec le Timekeeper dédié.
- [x] 5. Samplers API : ajout du support de `min_p` dans `UniversalClient` et configuration pour les modèles locaux (KoboldCPP).
- [x] 6. Tests unitaires ciblés pour valider les nouveaux prompts, le remplacement des macros et le filtrage RAG.

