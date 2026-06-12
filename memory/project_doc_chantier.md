---
name: project-doc-chantier
description: Chantier « documentation » d'Axiom AI (doc intégrée à l'app + site Sphinx de la lib) — décisions et état
metadata:
  type: project
---

Nouveau gros chantier lancé le **2026-06-12** : doter Axiom AI d'une **documentation**, en deux
volets indépendants.

**Volet 1 — Doc intégrée à l'app GUI** (PySide6) : tooltips au survol de chaque élément, bouton
« explique cette page » par page, quick tour de départ, annuaire global cherchable. **Traduit dans
les 10 langues** via le système `tr()` (cf. [[project-test-env]] et le rework i18n). Décision
utilisateur : on la fera **« tout d'un bloc »** (conception des 4 briques ensemble), **plus tard**.

**Volet 2 — Site de doc de la librairie `axiomai-engine`** : **✅ FAIT (TICKET-058, 2026-06-12,
branche `dev-documentation`)**. Projet **Sphinx** dans `docs/` (Furo, pages Markdown/MyST,
autodoc) ; **EN + FR** (décision utilisateur : « anglais et un menu des langues vers le
français, le reste après ») via gettext `.po` + sélecteur de langue maison ; quickstart,
6 guides, référence d'API. Au passage **~100 docstrings publiques du moteur traduites FR→EN**
(règle désormais : docstring publique = anglais). Déploiement GitHub Pages :
`.github/workflows/docs.yml` (build strict `-W`, deps lourdes mockées). ⚠ Reste à l'utilisateur :
**activer Pages (Settings → Pages → Source « GitHub Actions ») + merger `main`**. Traduction FR
de la réf API (~800 chaînes) et autres langues = plus tard. Mode d'emploi :
`maintenance/TICKET-058-doc-sphinx/DOC.md`.

**Ordre décidé :** i18n d'abord (fait, TICKET-053/054), puis le site Sphinx (fait, TICKET-058),
puis la doc intégrée (TICKET-057, en attente).

**Prérequis traité (i18n) :** TICKET-053 (rework : traductions externalisées en TOML par langue,
10 langues complétées à 295/295) **puis** TICKET-054 (séparation des couches) — tous deux le
2026-06-12. **Le moteur ne traduit plus** : il émet des données/clés stables/anglais par défaut
(`axiom/textfmt.py::fmt_num`, `TimeSystem.get_time_components`). **Tout l'i18n vit côté app** :
`core/localization.py` (`tr`, `SUPPORTED_LANGUAGES`, `canonical_verbosity`, `format_time`,
`compute_coverage`) + `core/locales/<lang>.toml`. Outil de couverture : `python tools/i18n_check.py`.
Voir `maintenance/TICKET-053-i18n-rework/` et `maintenance/TICKET-054-i18n-engine-gui-split/`.
**Règles désormais :** ajouter une clé = éditer `core/locales/*.toml` ; le moteur ne doit JAMAIS
importer `core.localization` ; afficher le temps dans le GUI = `core.localization.format_time(...)`.
⚠ Validation GUI (changement de langue, temps localisé) en attente.

**Why:** l'utilisateur (non-codeur, cf. [[user-profile-non-coder]]) veut rendre l'app
auto-explicative pour tout public et publier une vraie doc de la lib. Chantier ouvert, à reprendre.
