# CHANGELOG — Fix Tabletop Image Button Crash

## 2026-10-04 — Correction du crash lors du clic sur le bouton "Illustration" dans TabletopView
- Création de `workers/image_worker.py` : `ImageWorker(QThread)` encapsulant la génération d'images pour le thread d'arrière-plan sans bloquer la boucle d'événements Qt.
- Modification de `mods/axiom.illustrations/main.py` : ajout du paramètre `force: bool = False` à `generate_turn_image` pour permettre le déclenchement manuel ponctuel même si `image_generation_enabled` est inactif globalement, et renvoi d'une instance `Path` normalisée.
- Correction dans `mods/axiom.ui.qt/ui/tabletop_view.py` :
  - Remplacement de `self._active_save_id` par `self._save_id` dans `_on_generate_image_clicked`.
  - Ajout de la propriété `@property def _active_save_id(self) -> str` renvoyant `self._save_id` pour la rétro-compatibilité et éviter tout crash d'attribut futur.
  - Remplacement de `self.show_image_placeholder()` par `self._chat.show_image_placeholder()`.
  - Extraction du texte narratif et du numéro de tour cible depuis `self._history`.
  - Déclenchement non-bloquant via `ImageWorker` avec désactivation temporaire du bouton et mise à jour de la barre d'état.
  - Connexion des slots `_on_image_generated` (insertion de l'image dans le chat ou retrait du placeholder, réactivation du bouton) et `_on_image_error` (nettoyage et signalement d'erreur).
- Ajout de la suite de tests `tests/test_tabletop_image_button.py` validant l'alias de propriété, l'absence de crash en cas d'absence de session ou de texte narratif, le parcours complet de génération et le traitement des erreurs (**5/5 ✅**).
