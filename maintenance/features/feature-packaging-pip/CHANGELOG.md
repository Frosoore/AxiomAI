# CHANGELOG — feature-packaging-pip

## 2026-06-10 — étape complète (1 session)

**Décision structurante :** TICKET-009 clos en **version légère** — pas de split physique, pas de
déplacement de `axiom/`. Un `pyproject.toml` à la racine avec liste d'inclusion explicite suffit
pour rendre le moteur pip-installable tout en restant mono-repo (l'app = vitrine du moteur).

### Ajouté
- `pyproject.toml` (racine) : package **`axiomai`**, n'emballe que `axiom/` ; deps moteur
  zéro Qt (chromadb, sentence-transformers, httpx, google-genai, tomlkit, requests) ;
  `requires-python >= 3.11` (tomllib) ; licence AGPL-3.0-or-later ; entry point console
  `axiom = axiom.cli.main:main` ; version dynamique `attr: axiom.__version__`.
- `axiom/__init__.py` : `__version__ = "0.1.0"` (source de vérité unique) + objet **`axiom.help`**
  (classe `_Help` : `__repr__` = `__call__` = guide de démarrage rapide ~40 lignes — API Session,
  modules, CLI ; aucun import lourd déclenché). `help` volontairement hors `__all__`.
- `export_engine.py` (racine, hors package) : exporte un dossier PyPI-ready autonome
  (`dist/axiomai/` par défaut : axiom/ sans caches + pyproject + LICENSE + README librairie
  généré). Options : `--bump patch|minor|major` / `--set-version X.Y.Z` (réécrit la version dans le
  repo puis exporte), `--build` (sdist+wheel via le module `build` si dispo), `--force` (n'écrase
  qu'un export précédent reconnu). Garde anti-fuite : export refusé si un fichier du moteur importe
  PySide6/PyQt/ui/workers/core/database.
- `tests/test_packaging.py` : 15 tests (help, version, pyproject, bump/écriture de version,
  garde headless, export, sécurités d'écrasement).
- `.gitignore` : + `dist/`, `build/`, `*.egg-info/`.

### Corrigé en chemin
- Regex d'écriture de version : `\s*$` avalait la ligne vide suivant `__version__`
  (remplacé par `[ \t]*$`, test de non-régression ajouté).

### Vérifié en réel
- `pip wheel .` → wheel `axiomai-0.1.0` qui ne contient **que** `axiom/` (+ metadata).
- Venv vierge : install wheel (`--no-deps` + tomlkit) → `import axiom`, `axiom.__version__`,
  `axiom.help` (40 lignes), commande **`axiom --help`** fonctionnelle.
- `export_engine.py --set-version 0.1.0` → export OK, et l'export se construit en autonome
  (`pip wheel` depuis le dossier exporté).
- Garde-fous collab : `test_engine_headless` + `test_cli_play` (15) + `startup_check` ✅.
- Suites : 548 verts (tests/ hors groupe vector/Qt) + 55 verts (vector/Qt séparés, TICKET-008
  oblige) = 603, dont les 15 nouveaux.

### Bookkeeping
- TICKET-009 : PENDING → DONE (clos en version légère).
- `maintenance/README.md` : ligne d'étape ajoutée ; `memory/` mis à jour (stratégie split).

## 2026-06-10 (session 2) — renommage `axiomai` + première release prête

- **Nom PyPI : `axiomai`** (choix utilisateur) — `axiom-engine` et `axiom` sont déjà pris sur PyPI
  par d'autres projets (vérifié via l'API pypi.org). Le nom d'IMPORT reste `axiom`
  (`pip install axiomai` → `import axiom`). Renommé dans pyproject, export_engine.py
  (README généré + `dist/axiomai/` par défaut), tests, docs, memory.
- `requirements-dev.txt` : + `build`, `twine` (installés dans `.venv`).
- Release 0.1.0 préparée : `python export_engine.py --build`, **`twine check` : PASSED ×2**.
- **Re-renommage → `axiomai-engine`** : le premier upload réel a révélé que PyPI refuse `axiomai`
  (400 « too similar to an existing project », règle anti-typosquatting vs `axiom-ai` — invisible
  via l'API json). Choix utilisateur : `axiomai-engine` (libre sous toutes ses variantes).
  Renommé partout, release reconstruite : `dist/axiomai-engine/dist/axiomai_engine-0.1.0.{tar.gz,whl}`,
  twine check PASSED ×2. Au passage : le 1er essai d'upload a aussi validé le token en réel
  (le 403 initial était un token mal collé/mauvaise portée, résolu par l'utilisateur).
  Il ne reste que l'upload final (côté utilisateur).

## 2026-06-10 (session 3) — PUBLIÉ 🎉 + doc générale à jour

- **`axiomai-engine` 0.1.0 est en ligne sur PyPI** (upload utilisateur réussi). Vérifié depuis
  l'extérieur : `pip install axiomai-engine` dans un venv vierge → `import axiom` 0.1.0 +
  commande `axiom --help` OK. Page : https://pypi.org/project/axiomai-engine/
- `ARCHITECTURE.md` : le paragraphe « Distribution (plus tard) — ne crée pas de pyproject » (devenu
  faux) remplacé par l'état réel ; nouvelle section « Packaging & distribution » (table des
  emplacements : pyproject, `__version__`, `axiom.help`, `export_engine.py`, tests, étape) +
  règles (dep moteur ⇒ pyproject + requirements ; version via `--bump` uniquement) ;
  + 1 ❌ dans « Ce qu'il ne faut pas faire ».
- `README.md` : badge PyPI + Python 3.11+ (tomllib), pitch librairie en intro, section
  « The Python Library (`axiomai-engine`) » (install, quickstart, `axiom.help()`, sous-commandes
  CLI), Key Features enrichies (Universe-as-Code, mondes/saves portables `.axiom`/`.axiomsave`,
  modes Normal/Hardcore/Companion, temps causal Timekeeper, illustrations IA, Studio avec preview
  de diff + canonisation, résilience quotas, moteur headless), Architecture Overview (+ Timekeeper,
  renvoi ARCHITECTURE.md), prérequis 3.11+.
