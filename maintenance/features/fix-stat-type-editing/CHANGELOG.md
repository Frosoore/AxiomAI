# CHANGELOG — Fix Stat Type Editing in Creator Studio

## [Complété]

- Remplacement du `QTableWidgetItem` non-éditable de la colonne 2 ("type") par un `QComboBox` dynamique (`numeric` / `categorical`) dans chaque ligne de `StatDefinitionEditorWidget`.
- Intégration de `set_cell_widget` pour préserver le focus et la sélection de ligne lors de l'interaction avec le combobox.
- Branchement du signal `currentIndexChanged` pour émettre `self.changed.emit()` et réinitialiser/ajuster automatiquement le format des paramètres de la colonne 4 lors du basculement (ex: `min:0, max:100` pour numérique).
- Mise à jour de `collect_data()` pour lire `currentData()` du `QComboBox` avec fallback gracieux.
- Mise à jour de `retranslate_ui()` pour mettre à jour les libellés traduits de tous les combobox de la table tout en préservant la sélection active.
- Création de `tests/test_stat_definition_editor.py` avec 4 tests unitaires complets validant la population, la modification interactive de type, l'ajout et la re-traduction. 100% verts.
