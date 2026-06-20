# CHANGELOG — TICKET-058 : site de doc Sphinx

## 2026-06-12 — Livraison complète (1 session)

**Décisions utilisateur en début de session :** site EN avec menu de langue vers le FR
(autres langues plus tard) ; périmètre = TICKET-058 seul.

### Site (`docs/`, nouveau dossier)
- `conf.py` : Furo, MyST (pages en Markdown), autodoc+napoleon (docstrings style Google),
  intersphinx, viewcode ; `autodoc_mock_imports` pour les deps lourdes (chromadb,
  sentence-transformers, google-genai, httpx, requests, tomlkit) → la doc se construit sans
  installer le runtime ; gettext (`locale_dirs=["locales"]`, un `.po` par page) ; version lue
  depuis `axiom.__version__`.
- Contenu EN rédigé : `index.md`, `quickstart.md`, `guides/{universe-format,cli,saves,populate,
  backends,images}.md`, `api/{index,core,config,universe-as-code,saves,content,backends,runtime}.md`
  (autodoc sur 27 modules du moteur). Tout vérifié contre le code réel (clés TOML du compilateur,
  flags argparse du CLI, schéma save_state.toml, settings.json).
- Sélecteur de langue : `_templates/sidebar/language.html` (Jinja + JS qui bascule le segment
  /en/↔/fr/ de l'URL) + `_static/custom.css`.

### Français
- Catalogues gettext générés (`sphinx-intl update -l fr`) ; **217 chaînes traduites** couvrant
  100 % des pages rédigées (index, quickstart, 6 guides, api/index). La référence API (~800
  chaînes de docstrings) reste en **fallback anglais** (mécanisme gettext natif) — traduisible
  plus tard sans rien changer à la structure.

### Docstrings du moteur (la réf API doit être EN)
- **~100 docstrings publiques traduites FR→EN** dans 19 fichiers : session, universe, compile,
  decompile, package, library, dev, savestore (23), saves (10), populate, regenerate, multiplayer,
  paths, textfmt, time_system, db_helpers, config, backends/base, backends/gemini. Docstrings
  **uniquement** — zéro ligne de code, placeholders/sens préservés ; commentaires internes laissés
  en FR (même règle que TICKET-055/056). Méthode : script AST (localisation par nom, réindentation
  automatique), vérif `ast.parse` après coup.
- Formatage reST corrigé dans les docstrings EN existantes (backends/base ` ``` ` et blocs
  d'exemple, ollama/gemini sections « Typical usage » dupliquées, arbitrator liste 1-10, rules
  schéma JSON en bloc littéral, parse_tool_call) : **34 warnings Sphinx → 0**.

### Déploiement
- `.github/workflows/docs.yml` : push sur `main` (paths docs/+axiom/) → build EN puis FR en
  `-W` (warnings = erreurs), redirect racine → `/en/`, déploiement Pages
  (upload-pages-artifact + deploy-pages). Une action utilisateur unique : Settings → Pages →
  Source « GitHub Actions ».

### Divers
- `requirements-dev.txt` : + sphinx, furo, myst-parser, sphinx-intl.
- `.gitignore` : + `docs/_build/`, `*.mo`.
- `maintenance/README.md`, `PENDING.md` (058 ✅), `collab/claude/EN_COURS.md` mis à jour.
- **TICKET-060 ouvert** : `axiom.help` (guide REPL du wheel) encore 100 % FR — angle mort de
  055/056.

### Validation
- Build EN + FR : **zéro warning** (`sphinx-build -W` passe).
- Scénario CI reproduit en venv vierge (sphinx+furo+myst seulement, aucune dep lourde) : OK.
- Rendu vérifié dans le HTML produit (texte FR appliqué, sélecteur présent dans la sidebar).
- Tests : **565 passed** (suite large hors vector/Qt) + **56 passed** (lot vector/Qt séparé)
  = 621 verts, aucun impacté par les docstrings.
