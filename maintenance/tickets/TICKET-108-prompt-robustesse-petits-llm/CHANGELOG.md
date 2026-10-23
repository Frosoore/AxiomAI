# CHANGELOG — TICKET-108 : Robustesse des petits LLM

## 2026-10-17
- Initialisation de l'étape suite à l'analyse d'exécution réelle sur Stheno v3.4 / KoboldCPP.
- **Agency Protection & Reminders** :
  - Mise à jour de `build_narrative_prompt` (`axiom/prompts.py`) : ajout de la règle *Epistemic Boundary* pour empêcher les PNJ d'inventer ou révéler des secrets hors de leur perception directe.
  - Refonte des `CRITICAL REMINDER` (modes Solo, Companion, Multiplayer) : ordre explicite de considérer les actions du joueur comme déjà accomplies, de commencer immédiatement par les réactions PNJ/environnement, et interdiction formelle de narrer ou inventer des actions, pensées ou dialogues pour le joueur.
  - Mise à jour de la règle `CONTINUITY` dans `mods/axiom.turn/main.py`.
- **Substitution des macros `{{char}}` et préservation de `{{user}}`** :
  - Création de `substitute_macros()` dans `axiom/prompts.py` gérant `{{char}}`, `<char>`, `{{user}}`, `<user>` sans sensibilité à la casse.
  - À l'import SillyTavern (`workers/import_export_worker.py`), seul `{{char}}` est résolu de manière permanente. `{{user}}` / `<user>` est expressément préservé en base de données pour permettre la résolution dynamique au runtime selon le nom/persona du joueur actuel.
  - Résolution dynamique de `{{user}}` au vol dans `_format_lore_book_block` et `build_narrative_prompt`.
- **Anti-duplication RAG** :
  - Calcul dynamique de `max_turn_id` dans `axiom/arbitrator.py` et `mods/axiom.rag/main.py` pour exclure tous les tours déjà inclus dans l'historique récent du chat.
  - Filtrage post-query éliminant les fragments dont le texte est identique ou chevauche les messages du contexte actif.
- **Support Sampler `min_p` & Headroom `max_tokens`** :
  - Ajout du paramètre `universal_min_p` (défaut 0.1) dans `AppConfig` (`axiom/config.py`).
  - Prise en charge de `min_p` dans `UniversalClient` (`axiom/backends/universal.py`) pour `complete()`, `stream_tokens()` et `_get_payload()`.
  - Augmentation du budget `verbosity_to_tokens` dans `axiom/arbitrator.py` (short: 300, balanced: 600, talkative: 1200) pour éviter les coupures prématurées au milieu du JSON en cas d'émission de tool call.
- **Audit de la troncature du Lorebook** :
  - Vérification par inspection directe de la base `ST_Aglae.db` et du code : aucune fonction de slicing/truncation de texte n'existe sur le Lorebook.
  - Confirmation que la coupure observée (`Wherea...se, navy-blue`) provenait d'une troncature du tampon terminal lors du copier-coller du log (~2 500 caractères omis entre les deux entrées distinctes `Schedule` et `Guild Receptionist (Liora)`).
- **Tests unitaires** :
  - 10 tests unitaires dans `tests/test_ticket_108_prompt_robustness.py`.
  - Régression complète validée (194 tests passés).
