# DOC — Fix Stat Type Editing in Creator Studio

## Objectif

Corriger le blocage dans l'onglet "Stats" du Creator Studio où le type de statistique (numeric / categorical) était figé lors de l'ajout (`Qt.ItemIsEditable` désactivé) et impossible à modifier par la suite.

## Décisions techniques

- Remplacer le `QTableWidgetItem` non éditable de la colonne 2 ("type") par un `QComboBox` avec les deux options traduisibles `tr("numeric")` et `tr("categorical")`.
- Associer les clés techniques (`"numeric"`, `"categorical"`) en `userData` du `QComboBox`.
- Utiliser `set_cell_widget` pour préserver le focus et la sélection de ligne lors du clic sur le menu déroulant.
- Mettre à jour `collect_data()` pour extraire `currentData()` du `QComboBox`.
- Gérer la re-traduction via `retranslate_ui()`.
