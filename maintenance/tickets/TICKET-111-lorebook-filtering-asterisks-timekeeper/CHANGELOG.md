# CHANGELOG — TICKET-111 : Filtrage Lorebook par mots-clés, description personnage principal, règle astérisques & Timekeeper trim_stop

## 2026-10-18
- Initialisation du ticket suite aux retours de logs KoboldCPP.
- **Filtrage par mots-clés du Lorebook SillyTavern** (`axiom/arbitrator.py`, `workers/import_export_worker.py`) :
  - Dans `axiom/arbitrator.py`, implémentation de `_is_constant_lore()` et `_entry_keywords_match()`.
  - Les entrées de la catégorie `"SillyTavern"` ne sont plus injectées par similarité vectorielle arbitraire ou expansion de catégorie : elles sont strictement filtrées par la présence de leurs mots-clés dans la fenêtre récente du chat (message actuel + derniers tours d'historique) ou par le statut Constant.
  - Exclusion de `"sillytavern"` des catégories d'expansion sémantique (`_expand_lore`), évitant que la présence d'une entrée SillyTavern n'entraîne l'injection en cascade de tout le character-book (Julie, Fred, Manuscripts, Schedule...).
  - Support de l'attribut `constant` lors de l'import SillyTavern (`workers/import_export_worker.py`), assignant la catégorie `"Constant"`.
  - Mise à jour des mots-clés réels de `Lore_Book` dans `ST_Aglae.db` et ses sauvegardes depuis la carte source.
- **Identité principale du personnage & `CURRENT STATE`** (`axiom/prompts.py`, `axiom/arbitrator.py`) :
  - `TurnContext` transporte désormais `global_lore`.
  - `global_lore` (description, personality, scenario de la carte) est lu depuis `Universe_Meta` et injecté en tête du prompt système (`MAIN CHARACTER IDENTITY & LORE ({char_name}):`), directement sous le prompt de base.
  - L'entité NPC principale est systématiquement ajoutée à `relevant_entity_ids` et initialisée dans `all_stats`, garantissant que `CURRENT STATE` affiche `[NPC] {char_name} (id: {eid})` au lieu de `(no entities)`.
  - La consigne d'identité précise le personnage incarné : `primarily portraying {char_name}`.
- **Alignement de la règle des astérisques** (`axiom/prompts.py`) :
  - Remplacement de la règle de formatage dans `NARRATOR RULES` et `CRITICAL REMINDER` par :
    `Format all narrative actions and descriptions inside *asterisks* and all spoken dialogue inside "double quotes".`
  - Alignement des assertions dans `tests/test_ticket_109_samplers_and_prompt_formatting.py`.
- **Timekeeper : préservation de l'accolade JSON** (`mods/axiom.time/main.py`) :
  - Retrait de `"}"` des stop sequences du chronological parser (conservation de `"<|eot_id|>"`). L'option `trim_stop: true` ne supprime plus l'accolade fermante du JSON.
- **Tests** :
  - Création de `tests/test_ticket_111_lorebook_and_identity.py` (4 tests).
  - Validation complète de la suite : 1 358 tests passés (100% succès).
