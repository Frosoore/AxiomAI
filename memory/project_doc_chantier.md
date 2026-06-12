---
name: project-doc-chantier
description: Chantier « documentation » d'Axiom AI (doc intégrée à l'app + site Sphinx de la lib) — décisions et état
metadata:
  type: project
---

Nouveau gros chantier lancé le **2026-06-12** : doter Axiom AI d'une **documentation**, en deux
volets indépendants.

**Volet 1 — Doc intégrée à l'app GUI** (PySide6) : **✅ code FAIT (TICKET-057, 2026-06-12,
branche `dev-documentation`, non commité)**. Les 4 briques « tout d'un bloc » : tooltips partout,
bouton « expliquer cette page » (F1), quick tour au 1ᵉʳ lancement (remplace la welcome box,
déclencheur = `SETTINGS_FILE` absent), annuaire cherchable (Aide → Documentation). Architecture :
registre déclaratif unique `ui/help_system.py::PAGES` (208 éléments, 6 pages) + dialogues
`ui/help_dialogs.py` ; 1 élément = 2 clés TOML `doc_<page>_<el>_t`/`doc_<page>_<el>` ; étendre =
1 ligne de registre + `doc(widget, "page.el")` + clés ×10 langues ; trous détectés par
`tools/doc_check.py`. **Traduit dans les 10 langues** (i18n_check 515/515 partout). En chemin :
3 clés préexistantes mal traduites corrigées (`chronicler_interval_label` — cascade
italien/espagnol dans it/pt/ru/zh/ja/ko —, `univ_params` ×7, `image_api_url` ko).
Suites vertes 581 + 56. ⚠ Reste : validation GUI réelle par l'utilisateur.
**Retours utilisateur traités (2026-06-12)** : toggle « bulles d'aide au survol » dans les
paramètres (config `doc_tooltips_enabled` + filtre `install_tooltip_gate` — ne coupe que les
tooltips de doc, dialogues/audit intacts) ; bug retranslate de la vue setup corrigé (onglet
Persona : labels figés dans la langue de démarrage) + chaînes EN en dur traduites (9 clés ×10
langues) ; restes Studio → TICKET-061. Suites 587 + 56 = 643 vertes.

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
puis la doc intégrée (fait côté code, TICKET-057 — validation GUI en attente).

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
