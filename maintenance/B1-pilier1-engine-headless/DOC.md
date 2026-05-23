# DOC — B1 Pilier 1 : axiom-engine headless

Extraction du moteur dans un package `axiom/` sans dépendance Qt (réf doc §5).

Stratégie : COPIE d'abord (app intacte), validation, puis bascule des imports
de l'app (Étape 2), puis abstraction Qt/paths (Étape 3) et API `Session` (Étape 4).

Décisions :
- `core/paths.py` et `core/logger.py` sont déjà stdlib → copiés tels quels dans `axiom/`.
- `workers/db_helpers.py` copié dans `axiom/db_helpers.py` pour résoudre la dépendance de l'arbitrator.
- `prompt_builder.py` copié en un seul `axiom/prompts.py` ; le split (narrative/chronicler/mini_dico/populate) du doc §5.2 est reporté.

## Analyse Étape 3 (abstraction Qt/paths) — fork à arbitrer

Le doc §5.3 étape 3 justifie l'abstraction par « core/paths.py = paths Qt-friendly » →
**incorrect** (vérifié : pur stdlib, déjà headless). Vraie limite : les chemins sont codés en
dur à l'import (`~/.config/AxiomAI`, `~/AxiomAI`), non injectables par un embedder.

Contraintes découvertes qui rendent une injection naïve cassante :
- L'app importe `axiom.config.GLOBAL_DB_FILE` comme **constante de module** (hub_view, settings_dialog, setup_view).
- `tests/test_config.py` **patche `axiom.config._CONFIG_FILE` / `_CONFIG_DIR`** (globals de module).
- 7+ sites importent `from axiom.paths import VECTOR_DIR/UNIVERSES_DIR/SETTINGS_FILE/...` (valeurs figées à l'import).
- `AppConfig` mélange champs engine (backend/urls/keys/models/chronicler_interval/rag_chunk_count)
  et app (ui_font_size/enable_audio/language) ; le scinder change le schéma de `settings.json` (migration).

Conséquence : l'Étape 3 « complète » du doc est plus invasive/risquée que les bugfixes Phase A.
Voir TICKET-004 (révision du doc) et la question de cadrage posée à l'utilisateur.
