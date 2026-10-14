# CHANGELOG — QoL Creator Studio

## 2026-10-04 — Suppression de ligne sur sélection de colonne / cellule
- Correction dans `mods/axiom.ui.qt/ui/widgets/table_context.py` : `select_row_at` gère désormais le clic droit sur `horizontalHeader()` et `verticalHeader()`, sélectionnant automatiquement la colonne/ligne si elle n'était pas entièrement sélectionnée, et activant l'option "Supprimer".
- Correction dans `mods/axiom.ui.qt/ui/widgets/entity_editor.py` : `keyPressEvent` ne vide plus le contenu des cellules (`item.setText("")`) en cas de sélection partielle ou de colonne ; il supprime désormais les entités sélectionnées via `_on_delete_entity()`, tout en préservant le comportement standard de la touche Delete lors de la saisie dans un champ texte (`QLineEdit`, etc.).
- Alignement sur l'ensemble des éditeurs de tables du Creator Studio (`lore_book_editor.py`, `rule_editor.py`, `scheduled_events_editor.py`, `stat_definition_editor.py`, `story_setup_editor.py`).
- Suite de tests `tests/test_creator_delete.py` enrichie pour couvrir la sélection de colonne + touche Delete, le bouton Supprimer, le clic droit sur header horizontal, et la non-suppression lors de la saisie texte (**8/8 ✅**).

## 2026-10-04 — Auto-scroll intelligent du chat (Qt & Web)
- Implémentation dans `mods/axiom.ui.qt/ui/widgets/chat_display.py` :
  - Détection automatique de la position de scroll (`is_at_bottom()`) via les signaux `valueChanged` et `rangeChanged` de la scrollbar verticale.
  - Tant que le joueur est au bas du chat, les tokens insérés en streaming par le LLM maintiennent le défilement fluide vers le bas.
  - Dès que le joueur scrolle vers le haut pour relire un message ou un paragraphe précédent, l'auto-scroll se désactive immédiatement et sa position de lecture reste figée.
  - Dès que le joueur redescend en bas du chat ou soumet une nouvelle action, l'auto-scroll se réactive automatiquement.
- Implémentation dans `web/app.js` (`startFastTypewriter`) :
  - L'animation du typewriter n'écrase plus `scrollTop` si l'utilisateur est remonté dans l'historique web.
- Suite de tests `tests/test_chat_buffer.py` enrichie avec 4 tests validant le maintien au fond, le gel de position lors du scroll vers le haut, la réactivation manuelle et l'envoi de message joueur (**12/12 ✅**).

