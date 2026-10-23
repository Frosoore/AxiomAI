# TODO — Fix Stat Type Editing in Creator Studio

Permettre la modification du type de statistique (numeric / categorical) dans l'onglet Stats du Creator Studio.

- [x] 1. Remplacer l'item statique non éditable par un `QComboBox` dans la colonne 2 ("type") de `StatDefinitionEditorWidget._add_row` (`mods/axiom.ui.qt/ui/widgets/stat_definition_editor.py`).
- [x] 2. Utiliser `set_cell_widget` pour l'intégration de sélection et connecter le signal `currentIndexChanged` à `self.changed.emit`.
- [x] 3. Adapter `collect_data()` pour lire le type depuis le `QComboBox` (`currentData()` / fallback).
- [x] 4. Mettre à jour `retranslate_ui()` pour re-traduire les options de type dans tous les `QComboBox` de la table et du champ de saisie.
- [x] 5. Ajuster intelligemment le champ options / paramètres (colonne 4) lors du basculement de type (ex: défaut `min:0, max:100` si passage à `numeric`).
- [x] 6. Écrire des tests unitaires de validation dans `tests/test_stat_definition_editor.py`.
