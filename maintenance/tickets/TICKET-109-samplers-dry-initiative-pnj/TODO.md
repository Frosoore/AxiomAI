# TODO — TICKET-109 : Samplers DRY, initiative physique PNJ & formatage roman sans astérisques

- [x] 1. Samplers DRY & trim_stop dans `axiom/config.py` et `axiom/backends/universal.py` :
  - Support de `dry_multiplier` (0.8), `dry_base` (1.75), `dry_allowed_length` (2), `dry_sequence_breakers` (`["\n", ":", "\"", "*"]`), `trim_stop` (True).
  - Température par défaut à 1.12 pour le backend universel avec samplers DRY.
- [x] 2. Initiative des PNJ & interactions physiques dans `CRITICAL REMINDER` (`axiom/prompts.py`) :
  - Débloquer l'accomplissement physique des actions demandées par le joueur (ex. prononcer un vœu, initier un baiser ou un contact).
  - Consigne stricte centrée sur la non-invention de dialogues et de décisions internes pour le joueur.
- [x] 3. Standardisation du formatage : description en texte normal, paroles entre guillemets doubles `"..."` :
  - Mise à jour de `NARRATOR RULES` dans `axiom/prompts.py` pour éliminer l'obligation des astérisques sur la narration (`Format all spoken dialogue inside "double quotes" and narrative descriptions in plain text (no asterisks)`).
  - Alignement des `CRITICAL REMINDER`.
- [x] 4. Headroom token & prévention coupures fin de phrase :
  - Vérification de `verbosity_to_tokens` et support de `trim_stop`.
- [x] 5. Tests unitaires et non-régression de l'ensemble de la suite.
