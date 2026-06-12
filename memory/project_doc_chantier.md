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

**Volet 2 — Site de doc de la librairie `axiomai-engine`**, façon `devguide.python.org` / PySide6
(tutos, quick guide, référence d'API auto-générée), destiné à **GitHub Pages**. Outil tranché :
**Sphinx** (et non MkDocs) — pour matcher les sites de référence cités et générer la référence d'API
depuis les docstrings existantes. Pas encore commencé.

**Ordre décidé :** i18n d'abord (fait, [[—]] TICKET-053), puis (au choix de l'utilisateur ensuite)
le site Sphinx et/ou la doc intégrée.

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
