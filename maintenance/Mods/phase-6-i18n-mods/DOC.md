# DOC — Phase 6 : Traduction complète des mods & Fallback multilingue

## 1. Objectifs
- Fournir les traductions complètes de l'ensemble des mods officiels dans les 10 langues supportées par Axiom AI (`en`, `fr`, `es`, `de`, `it`, `pt`, `ru`, `zh`, `ja`, `ko`).
- Implémenter un système de fallback robuste pour les mods communautaires ou tiers ne disposant que d'un jeu partiel de langues :
  - Si la langue de l'application est disponible pour le mod, elle est utilisée.
  - Sinon, si l'anglais (`en`) est disponible, il sert de premier repli.
  - Sinon, si une quelconque autre traduction existe dans le mod (ex. un mod uniquement en allemand ou en espagnol), elle est utilisée par défaut.
  - En dernier recours, les valeurs brutes du manifeste (`name` et `description` de `mod.toml`) sont utilisées.

## 2. Architecture technique
- **Stockage par mod** : chaque mod dispose d'un sous-dossier `locales/` contenant des fichiers `<lang>.json` (`title`, `description`, et éventuelles clés personnalisées).
- **Représentation en mémoire** : `ModManifest.locales` stocke la cartographie `{lang: {key: value}}`.
- **Accès localisé** : `manifest.localized_name(lang=None)` et `manifest.localized_description(lang=None)` résolvent le libellé avec application automatique de la chaîne de fallback.
- **Enregistrement dans le noyau** : au chargement du mod, `loader.py` injecte automatiquement les dictionnaires dans le slot `axiom.kernel:locales`, les rendant immédiatement accessibles au frontend via `core.localization.tr()`.
