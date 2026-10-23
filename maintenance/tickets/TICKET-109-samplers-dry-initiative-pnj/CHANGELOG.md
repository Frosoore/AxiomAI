# CHANGELOG — TICKET-109 : Samplers DRY, initiative physique PNJ & formatage roman

## 2026-10-17
- Initialisation du ticket suite à l'analyse de la session 11 tours sur Stheno v3.4.
- **Samplers DRY & Température 1.12** (`axiom/config.py`, `axiom/backends/universal.py`, `axiom/session.py`, `axiom/arbitrator.py`) :
  - Ajout des champs `universal_temperature: float = 1.12`, `universal_dry_multiplier: float = 0.8`, `universal_dry_base: float = 1.75`, `universal_dry_allowed_length: int = 2`, `universal_dry_sequence_breakers: list[str] = ["\\n", ":", '"', "*"]`, `universal_trim_stop: bool = True` dans `AppConfig`.
  - Transmission des paramètres DRY et `trim_stop` dans `UniversalClient` et injection dans les payloads API KoboldCPP/OpenAI (`complete`, `stream_tokens`, `_get_payload`).
  - Résolution de la température par défaut à 1.12 pour les backends universal/ollama.
- **Formatage standard de roman** (`axiom/prompts.py`) :
  - Remplacement de la consigne d'actions entre astérisques par du texte narratif standard : `Format all spoken dialogue inside "double quotes" and narrative descriptions in plain text (no asterisks).`
  - Suppression du conditionnement aux astérisques pour éviter les pertes de guillemets sur les dialogues.
- **Initiative et interactions physiques des PNJ** (`axiom/prompts.py`) :
  - Affinement des règles système et du `CRITICAL REMINDER` : les PNJ doivent accomplir les actions physiques demandées par le joueur (ex. prononcer un vœu, initier un toucher ou un baiser).
  - Ciblage de la limite d'agence strictement sur la non-invention de dialogues ou de décisions internes pour le joueur.
- **Budget tokens & headroom** (`axiom/arbitrator.py`) :
  - Ajustement de `verbosity_to_tokens` : short (300), balanced (600), talkative (1200) pour prévenir les coupures de milieu de phrase.
- **Macro `{{user}}` / `<user>` préservée à l'import** (`workers/import_export_worker.py`) :
  - `_substitute_st_macros` ne résout que `char_name` à l'import pour préserver la portabilité de la carte entre différents joueurs et personas, la substitution de `{{user}}` se faisant dynamiquement au runtime dans `prompts.py`.
- **Tests unitaires et de non-régression** :
  - Création de `tests/test_ticket_109_samplers_and_prompt_formatting.py` (8 tests).
  - Validation de `tests/test_ticket_108_prompt_robustness.py`, `tests/test_prompt_builder.py`, `tests/test_arbitrator.py`, `tests/test_sillytavern_mod.py`, `tests/test_config.py`.
