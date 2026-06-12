# DOC — TICKET-053 : rework i18n

## Objectif
Sortir les traductions du code (`axiom/localization.py`, dict de 2400 l.) vers des fichiers de
données par langue (`axiom/locales/<lang>.toml`), compléter les langues incomplètes, et ajouter un
outil de contrôle de couverture. Prérequis structurel du chantier « doc intégrée à l'app ».

## Décisions
- **Format TOML** (cohérent avec le reste du projet : compile/saves/decompile).
- **API publique inchangée** : tous les `from axiom.localization import tr` (~25 fichiers UI)
  continuent de marcher sans modification.
- Chargement **paresseux + caché** au runtime (lecture `tomllib`, stdlib rapide).

## Usage
- `axiom i18n-check` : audite la couverture des 10 langues (clés manquantes / en trop).
