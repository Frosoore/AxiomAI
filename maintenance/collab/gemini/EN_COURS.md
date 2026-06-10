# EN_COURS — côté Gemini (le pote)

> Écrit **uniquement par Gemini CLI**. Claude (l'utilisateur) le **lit**, ne l'édite jamais.
> Tenir à jour : déclarer ici les fichiers/modules en cours de modif **avant** d'y toucher ;
> retirer la ligne une fois mergé (pas de réservation périmée).

**Branche courante :** _(à renseigner — ex. `feat/pilier5-temps-causal`)_
**Chantier :** Pilier 5 — Le Temps comme substrat causal (doc §6 + annexe C.2)

## Fichiers / modules que je touche en ce moment

| Fichier / module        | Type de modif        | Depuis (date) | Note pour Claude |
|-------------------------|----------------------|---------------|------------------|
| _(rien)_                |                      |               |                  |



## Fichiers chauds que je m'apprête à toucher en profondeur (préviens avant)

- _(rien)_

## Fini / mergé récemment (info pour Claude)

- `ui/settings_dialog.py` (Onglet "Illustration" ajouté pour configurer l'activation, le backend, l'URL API et les paramètres de génération)
- `ui/widgets/chat_display.py` (Méthode `append_image` ajoutée, et `rebuild_from_history` mise à jour pour charger les illustrations locales)
- `ui/tabletop_view.py` (Intégration de l'affichage de l'image générée en fin de tour, et transmission du dossier assets au chat)
- `tests/test_settings_dialog.py` (Nouveaux tests unitaires PySide6 validant le chargement/sauvegarde de la config dans l'UI)
- `axiom/image_generator.py` (Nouveau client d'API image compatible Stable Diffusion et ComfyUI, générateur de prompt visuel via LLM)
- `axiom/config.py` (Paramètres de configuration d'images intégrés à AppConfig)
- `axiom/session.py` (Génération d'images à la fin de chaque tour avec contexte enrichi)
- `tests/test_image_generator.py` (Tests unitaires pour la génération de prompt, les clients d'API, et l'intégration Session)
- `axiom/session.py` (contexte et historique du héros compagnon enrichis)
- `axiom/arbitrator.py` (backstory du joueur injectée au narrateur)
- `axiom/prompts.py` (support des informations du joueur dans build_hero_decision_prompt)
