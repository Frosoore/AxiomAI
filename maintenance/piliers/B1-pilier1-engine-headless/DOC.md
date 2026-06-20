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

## Décision Étape 6 — source d'historique canonique = Event_Log

Le worker mappait la liste d'historique tenue par l'UI ; `Session` reconstruit depuis l'`Event_Log`.
Choix acté : **l'Event_Log est la source canonique** (déjà persistée, indépendante de toute UI,
identique pour GUI/CLI/serveur). À l'Étape 7, le `NarrativeWorker` déléguera à `Session` et héritera
donc de cette source — la liste UI ne sert plus qu'à l'affichage. La décision du héros Companion est
portée dans `Session` (backend héros injectable, défaut = modèle local `extraction_model`, parité worker).

## Conséquence Étape 7 — déduplication du message courant dans le prompt

L'ancien `NarrativeWorker` mappait la liste d'historique de l'UI, qui contenait **déjà** le message
du joueur du tour courant (ajouté avant le lancement du worker). `build_narrative_prompt` ajoute par
ailleurs ce message comme `user_message` final → il apparaissait potentiellement **deux fois**.
`Session._load_history` lit l'Event_Log **avant** que `process_turn` n'y écrive le `user_input` du
tour ; le message courant n'y figure donc pas et n'est présent qu'une fois (param `user_message`).
Le passage worker→`Session` supprime ainsi ce doublon (comportement plus correct, à confirmer en run réel).

## Étape 8 — CLI `axiom play`

Le moteur se joue hors Qt via la même API `Session` que le GUI :

    python -m axiom.cli play <univers.axiom>        # ou un nom sous ~/AxiomAI/universes
    python -m axiom.cli play Monde --new --name Hero --difficulty Companion
    python -m axiom.cli play Monde --save <save_id>  # reprendre une partie

Sans `--save`/`--new`, la sauvegarde la plus récente est reprise (sinon une partie neuve est créée).
En jeu : toute saisie = action du joueur (narration streamée) ; `/help`, `/stats`, `/checkpoints`,
`/rewind <turn_id>`, `/quit`. Point d'entrée `axiom.cli:main` prêt pour le futur console_script `axiom`.
Le CLI ne dépend que de l'API publique (`Session`/`Universe` + helpers config/db) : les
réorganisations internes à venir (`prompts.py` splitté, `memory` en Protocol) ne l'impactent pas.
