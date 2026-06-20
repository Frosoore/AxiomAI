# Changelog - Feature Image Generation

- Initialisation de la fonctionnalité de génération d'images.
- Déclaration des fichiers dans la coordination de dev parallèle (`EN_COURS.md`).
- Ajout des variables de configuration d'images à `AppConfig` dans `axiom/config.py`.
- Création du module `axiom/image_generator.py` gérant la génération de prompt visuel via LLM et les appels d'API vers Stable Diffusion WebUI, ComfyUI, et mock.
- Intégration du système de génération d'images dans `Session.resolve_tick` avec extraction du contexte spatial et des personnages pour enrichir le prompt.
- Ajout de l'onglet **Illustration** dans la boîte de dialogue des paramètres (`ui/settings_dialog.py`) permettant de configurer l'activation, le backend (Mock, Stable Diffusion, ComfyUI), l'URL de l'API locale, les dimensions de l'image, le nombre d'étapes de débruitage, le CFG scale, et un workflow ComfyUI personnalisé.
- Prise en charge de l'affichage des images locales dans le widget de chat (`ui/widgets/chat_display.py`) :
  - Affichage instantané en fin de tour avec la méthode `append_image`.
  - Reconstitution et affichage automatique des illustrations des tours précédents lors du rechargement de l'historique de session (`rebuild_from_history`).
- Câblage de l'UI de jeu principale (`ui/tabletop_view.py`) pour transmettre l'illustration au chat à la fin du tour et passer le dossier des actifs de la sauvegarde à l'initialisation.
- Création de tests unitaires d'interface avec `qtbot` dans `tests/test_settings_dialog.py` pour valider le chargement et la sauvegarde de la configuration graphique des images.
- Validation finale de toute la suite de tests (`411 passed`).
