# TODO — TICKET-058 : site de doc de la lib `axiomai-engine` (Sphinx)

Décisions utilisateur (2026-06-12) : site **anglais** + **sélecteur de langue** vers le
**français** (autres langues plus tard) ; périmètre = **TICKET-058 seul** (la doc in-app
TICKET-057 reste « plus tard »).

- [x] Squelette Sphinx dans `docs/` (Furo, MyST/Markdown, autodoc+napoleon, gettext)
- [x] Contenu EN : index, quickstart, guides (Universe-as-Code, CLI, saves, populate, backends, images), référence API autodoc (7 pages)
- [x] Docstrings publiques `axiom/` traduites FR→EN (~100, la réf API est EN ; déclaré dans collab/)
- [x] Formatage reST des docstrings corrigé (34 warnings → 0)
- [x] Traductions FR (`docs/locales/fr/.../*.po`) — pages rédigées 100 % traduites (217 chaînes) ; API en fallback EN (à traduire plus tard si souhaité)
- [x] Sélecteur de langue EN/FR dans le thème (template `sidebar/language.html` + JS de bascule /en/↔/fr/)
- [x] Workflow GitHub Actions → GitHub Pages (build en+fr strict `-W`, redirect racine → /en/, deps lourdes mockées)
- [x] `requirements-dev.txt` (sphinx, furo, myst-parser, sphinx-intl) + `.gitignore` (docs/_build/, *.mo)
- [x] Build local vert (en + fr), **zéro warning** ; validé aussi en venv vierge sans deps lourdes (scénario CI)
- [x] Mise à jour `maintenance/README.md` + `PENDING.md` (058 ✅, TICKET-060 ouvert : `axiom.help` FR)
- [x] Traduction FR de la **référence d'API** (~720 chaînes traduites sur les 7 catalogues `api/*.po` ; restent volontairement en EN : noms de modules, en-têtes de fichiers, littéraux de types) — demandé par l'utilisateur dans la foulée
- [ ] **Utilisateur** : activer Pages (repo GitHub → Settings → Pages → Source = « GitHub Actions »), merger dans `main`
- [ ] (Plus tard, optionnel) ajouter d'autres langues (`sphinx-intl update -l <lang>`)
