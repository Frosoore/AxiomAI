# TODO — TICKET-111 : Filtrage par mots-clés du Lorebook, description personnage principal, règle astérisques & Timekeeper trim_stop

- [x] 1. Filtrage par mots-clés (Keywords) & constantes du Lorebook SillyTavern (`axiom/arbitrator.py`) :
  - Seules les entrées "Constant" (toujours actives) ou dont les mots-clés (`keys` / `keywords`) apparaissent dans les derniers messages du chat (`scan_lower`) sont injectées dans `lore_book_subset` / `=== LORE BOOK ===`.
  - Exclusion de la catégorie conteneur `"sillytavern"` de l'expansion sémantique (`_expand_lore`) pour empêcher la contamination du prompt par des PNJ secondaires non mentionnés (ex: Julie, Fred, Manuscripts).
- [x] 2. Injection de l'identité principale du personnage SillyTavern (`axiom/prompts.py`, `axiom/arbitrator.py`) :
  - `global_lore` (contenant description/personality/scenario) est chargé depuis `Universe_Meta` et injecté en haut du prompt système (sous `universe_system_prompt`) comme identité principale (`MAIN CHARACTER IDENTITY & LORE ({char_name}):`).
  - L'entité NPC principale est systématiquement incluse dans `relevant_entity_ids` et ses stats initialisées, évitant l'affichage `(no entities)` dans `CURRENT STATE`.
  - La règle d'identité précise le personnage incarné : `primarily portraying {char_name}`.
- [x] 3. Règle des astérisques pour le rendu UI (`axiom/prompts.py`) :
  - Consigne modifiée dans `NARRATOR RULES` et `CRITICAL REMINDER` :
    `Format all narrative actions and descriptions inside *asterisks* and all spoken dialogue inside "double quotes".`
- [x] 4. Correction du JSON cassé sur le Timekeeper (`mods/axiom.time/main.py`) :
  - Retrait de `"}"` des stop sequences du chronological parser (conservation de `"<|eot_id|>"`), évitant la troncation de l'accolade fermante sous `trim_stop=True`.
- [x] 5. Base de données & tests de non-régression :
  - Remplissage des keywords de `Lore_Book` dans `ST_Aglae.db` et ses sauvegardes depuis la carte source.
  - Création de `tests/test_ticket_111_lorebook_and_identity.py` (4 tests).
  - Suite complète à 1 358 tests 100% au vert.
