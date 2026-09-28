# Documentation — Phase 0e : Schéma ouvert & Configuration extensible

## Objectif
Préparer le socle du moteur à l'accueil de mods autonomes :
1. **Schéma ouvert** : Ne plus restreindre SQL `difficulty` à une liste codée en dur dans le noyau (`Saves`). Permettre aux mods de jeu de définir librement leurs modes.
2. **Migrations de mods** : Fournir une table standardisée `Mod_Schema_Versions` et une fonction `apply_mod_migrations` garantissant l'évolution transactionnelle et ordonnée des tables propres à chaque mod.
3. **Configuration extensible** : Permettre aux mods de stocker des dictionnaires de configuration ouverts dans `settings.json` sous `mod_settings` sans altération ni troncature.
