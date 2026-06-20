# DOC — Outil de diagnostic : venv auto + i18n

## Objectif
Fiabiliser l'outil de diagnostic externe (`python -m tools.diagnostic`, CLI + `--gui`)
pour la bêta : il doit donner un rapport juste même lancé « nu », et être lisible dans
les 10 langues de l'app.

## Décisions

### 1. Bascule automatique dans le venv
`tools/diagnostic.py::_maybe_reexec_in_venv()` s'exécute tout au début de `main()`.
- Si `--no-venv` ou `AXIOM_DIAG_REEXEC=1` (garde anti-boucle) → ne fait rien.
- Cherche le python du venv projet : `.venv/bin/python` (POSIX) ou
  `.venv\Scripts\python.exe` (Windows), relatif à la racine du repo.
- Si l'interpréteur courant n'est pas celui-là et que le venv existe →
  `os.execve` vers ce python en relançant **le fichier par son chemin** (pas `-m`,
  pour ne pas dépendre du cwd), `AXIOM_DIAG_REEXEC=1` posé.
- Pourquoi toujours préférer `.venv` (et pas seulement « si hors de tout venv ») :
  l'app tourne dans `.venv` (run.sh/run.bat) ; le diagnostic doit refléter CET
  environnement. Si aucun `.venv` n'existe (deps installées globalement), on tourne
  sur place.

### 2. i18n du rapport
Le tool vit côté app (il importe déjà `core`), il peut donc utiliser
`core.localization.tr`. Traduit **à la construction** (dans les `_check_*`), donc
`format_report`/`_to_json` restent inchangés et le JSON est localisé aussi.
- Sont traduits : titres de sections, noms de checks, phrases de détail, en-tête du
  rapport, messages GUI/venv.
- Restent littéraux (données, pas du langage) : versions, chemins, ids de modèle,
  nom du backend, messages d'exception bruts.
- Helper `_tr()` à tolérance de panne (si `core` indisponible → renvoie la clé), pour
  ne jamais casser le rapport.
- Clés préfixées `diag_*` dans `core/locales/*.toml`, ajoutées aux **10** langues.
- L'EN reste byte-identique à l'existant (tests d'assertion + langue par défaut = en).

### 3. Sélecteur de langue dans le GUI
`ui/diagnostic_dialog.py` a un combo de langue (10 langues, noms natifs). Le rapport
étant traduit à la construction, changer la langue appelle `set_language()` puis re-run
les checks rapides pour le re-rendre, et retraduit le chrome du dialog.
- `core.localization.set_language(lang)` : override **en mémoire seulement** (pas d'écriture
  config) — c'est une vue transitoire, pas un changement de réglage.
- À la fermeture (`finished`), `reload_translations()` relit la config : l'override ne fuit
  pas dans le reste de l'app (cas du dialog in-app Aide → Diagnostic).

## Usage
Inchangé pour l'utilisateur : `python -m tools.diagnostic [--gui|--tests|--offline]`.
Nouveau : `--no-venv` pour forcer l'interpréteur courant. Dans le GUI, menu déroulant de
langue pour lire/copier le rapport dans une autre langue à la volée.
