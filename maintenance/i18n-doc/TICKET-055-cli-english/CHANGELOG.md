# CHANGELOG — TICKET-055 : CLI moteur en anglais

## 2026-06-12 — livré

Le CLI `axiom` (publié dans le wheel `axiomai-engine`) avait son texte user-facing en **français**
(historique : outil interne de devs francophones). Le moteur étant publié et « parlant anglais »
(TICKET-054), son CLI doit l'être. **Pas de l'i18n** : un CLI dev = anglais, point.

### Traduit FR → EN (texte user-facing uniquement : `help=`, `description=`, `print`, `write`)
- `axiom/cli/main.py` — description racine + les 14 `help=` des sous-commandes.
- `axiom/cli/play.py` — args, `_HELP_TEXT` (commandes slash), messages de la boucle de jeu
  (`/stats`, `/checkpoints`, `/rewind`, erreurs LLM/tour), câblage (`run_play`).
- `axiom/cli/compile_cmd.py` — compile / pack / import / dev / decompile (help + messages).
- `axiom/cli/populate_cmd.py` — help + messages (univers introuvable, erreur LLM).
- `axiom/cli/saves_cmd.py` — save-show/export/import/edit/pack/unpack/fork (help + messages).
- **Non touchés** (volontaire) : commentaires et docstrings internes (cohérence avec le reste du
  code, francophone). Périmètre = ce que voit l'utilisateur du CLI.

### Tests
- 3 assertions FR de `tests/test_cli_play.py` mises à jour (LLM unreachable / Error during turn /
  Unknown command) + 1 de `tests/test_savestore.py` ("introuvable" → "not found"). Mises à jour
  d'assertions (le texte a changé volontairement), aucune suppression de test.
- Validation (offscreen) : `axiom --help` 100 % anglais ; 157 passed
  (cli_play, universe_as_code, saves_editing, savestore, packaging, dev_hotreload, populate_engine).
- `grep` : plus aucune chaîne user-facing française dans `axiom/cli/` (help/print/write).

### Découverte → TICKET-056 (hors périmètre, ticketé)
Le CLI surface encore du français **émis par le moteur hors `cli/`** : l'événement de `axiom dev`
(`axiom/dev.py`, « Définition compilée… ») et surtout les **messages d'exception** (`package.py`,
`library.py`, `compile.py`, `saves.py`, `savestore.py`…) affichés via `print(f"...{exc}")`. Chantier
distinct et plus large (impacte des tests qui assertent le FR) → **TICKET-056** ouvert dans PENDING.
