# CHANGELOG — Outil de diagnostic : venv auto + i18n

## En cours (2026-06-15)
- Démarrage de l'étape (TODO/DOC/CHANGELOG).
- Reproduction du bug : `python -m tools.diagnostic` (python système 3.14.5, hors
  `.venv`) → torch/chromadb/sentence-transformers/google-genai « not importable »
  alors que `.venv/bin/python` les a tous. `--gui` ouvre bien la fenêtre mais avec ce
  rapport faussement alarmant. Cause = venv, comme soupçonné.

### Fait
- **Bascule venv auto** (`tools/diagnostic.py`) : `_maybe_reexec_in_venv()` au point
  d'entrée `__main__` (pas dans `main()` → tests/appels programmatiques épargnés).
  `os.execve` vers `.venv/bin/python` (ou `.venv\Scripts\python.exe`) en relançant le
  fichier par chemin. Garde `AXIOM_DIAG_REEXEC=1` + flag `--no-venv`.
  - **Piège évité** : détection « suis-je déjà dans le venv ? » par **`sys.prefix`**,
    pas par `Path(sys.executable).resolve()` — le `bin/python` d'un venv est un symlink
    vers l'interpréteur de base, donc `.resolve()` rendait venv == python système et la
    bascule n'avait jamais lieu.
  - Vérifié en réel : `/usr/bin/python -m tools.diagnostic` → message « Bascule vers
    … /.venv/bin/python » puis rapport avec toutes les deps ✅ ; depuis le venv → aucune
    bascule ; `--no-venv` → reste sur le python courant.
- **i18n du rapport** : contenu (titres de sections, noms de checks, phrases de détail,
  en-tête, messages GUI/venv) traduit via `core.localization.tr` (helper `_tr()`
  tolérant). Données littérales (versions, chemins, ids de modèle, nom du backend,
  exceptions) inchangées. EN gardé byte-identique. **57 clés `diag_*`** ajoutées aux
  **10** langues (`i18n_check` : 615/615 partout).
- **Fix d'isolation de test** (révélé par l'i18n) : `tests/conftest.py` reset le cache
  i18n (`reload_translations`) avant/après chaque test — sans ça, un test changeant de
  langue (ex. `test_help_system`) faisait fuiter `_CURRENT_LANG` et cassait tout test
  lisant du texte localisé selon l'ordre. `test_diagnostic_dialog` rendu langue-neutre.
- **README** : note venv remplacée (bascule auto + `--no-venv` + rapport dans la langue
  de l'app).
- Tests : **781 passed** (lot principal) + **7 passed** (lot audio) + couverture i18n
  verte.

### Ajout (retour utilisateur : « t'as oublié un bouton pour changer de langue »)
- **Sélecteur de langue dans le GUI** (`ui/diagnostic_dialog.py`) : combo
  `SUPPORTED_LANGUAGES` (10 langues, noms natifs) en haut de la fenêtre. À la sélection :
  `set_language()` (override **en mémoire, non persisté**) + retraduction du chrome
  (titre, intro, boutons) + re-run rapide pour re-rendre le rapport dans la langue.
- **Setter** `core.localization.set_language(lang)` ajouté (override `_CURRENT_LANG`
  sans écrire la config) + exporté.
- **Restauration à la fermeture** : `self.finished → reload_translations()` — sinon, pour
  le dialog in-app (Aide → Diagnostic), changer la langue ici la laisserait fuiter dans
  tout le reste de l'app. Vérifié : fr → ko → en → (fermeture) → fr restauré.
- +2 tests (`test_language_combo_switches_and_reruns`, `test_close_restores_app_language`).
  Suite : **783 passed** (lot principal). Smoke GUI headless OK.

