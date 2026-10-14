# DOC — Fix Tabletop Image Button Crash

## Contexte et Problème
Lors d'une partie dans TabletopView, un clic sur le bouton "Illustration" (`_image_btn`) déclenchait immédiatement une exception non gérée :
```
AttributeError: 'TabletopView' object has no attribute '_active_save_id'
```
Une analyse de `mods/axiom.ui.qt/ui/tabletop_view.py` a révélé :
1. L'utilisation erronée de `self._active_save_id` au lieu de `self._save_id`.
2. L'appel `self.show_image_placeholder()` qui aurait crashé à la ligne suivante (`show_image_placeholder` appartient à `ChatDisplayWidget`, soit `self._chat`).
3. L'absence de worker asynchrone pour effectuer la génération sans bloquer l'UI Qt principale.
4. Dans `mods/axiom.illustrations/main.py::generate_turn_image`, l'impossibilité de forcer la génération manuelle si `image_generation_enabled` est `false` dans les réglages.

## Solution apportée
1. Implémentation d'un `ImageWorker(QThread)` dans `workers/image_worker.py` pour exécuter la génération en arrière-plan.
2. Ajout du paramètre `force: bool = False` dans `IllustrationsService.generate_turn_image`.
3. Correction de `TabletopView._on_generate_image_clicked` et ajout d'une propriété `@property def _active_save_id` pour la rétrocompatibilité.
4. Récupération dynamique du texte narratif et du numéro de tour depuis `self._history`.
5. Gestion des slots de fin (`_on_image_generated`, `_on_image_error`) avec affichage dans le chat et restauration de l'état du bouton.
