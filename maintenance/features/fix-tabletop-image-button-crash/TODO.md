# TODO — Fix Tabletop Image Button Crash

- [x] Créer `workers/image_worker.py` : `ImageWorker(QThread)` pour générer l'image en tâche de fond sans figer le thread Qt.
- [x] Mettre à jour `mods/axiom.illustrations/main.py` : supporter l'argument `force: bool = False` dans `generate_turn_image` pour autoriser la génération manuelle à la demande même si `image_generation_enabled` est décoché dans les paramètres globaux.
- [x] Corriger `mods/axiom.ui.qt/ui/tabletop_view.py` :
  - Remplacer `self._active_save_id` par `self._save_id` dans `_on_generate_image_clicked`.
  - Ajouter une property de rétro-compatibilité `@property def _active_save_id(self) -> str`.
  - Remplacer `self.show_image_placeholder()` par `self._chat.show_image_placeholder()`.
  - Extraire le texte narratif de la scène courante depuis `self._history` et cibler le `turn_id` approprié.
  - Déclencher `ImageWorker` de manière asynchrone et connecter les slots `_on_image_generated` et `_on_image_error`.
  - Réactiver le bouton et nettoyer le placeholder en cas d'erreur ou fin de génération.
- [x] Écrire les tests unitaires dans `tests/test_tabletop_image_button.py` validant l'absence de crash, la propriété et le flux complet de génération manuelle (5/5 ✅).
- [x] Valider la suite de tests et mettre à jour le CHANGELOG.
