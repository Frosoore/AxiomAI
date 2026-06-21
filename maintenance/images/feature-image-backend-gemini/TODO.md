# TODO — Backend Gemini pour la génération d'images

Objectif : rendre la génération d'images utilisable sans logiciel local (SD WebUI /
ComfyUI), via la clé API Gemini déjà configurée pour le texte.

- [x] Déclarer les fichiers touchés dans `maintenance/collab/claude/EN_COURS.md`.
- [x] `axiom/config.py` : champ `image_gemini_model` (défaut `gemini-2.5-flash-image`).
- [x] `axiom/backends/gemini.py` : méthode `GeminiClient.generate_image_bytes(prompt, aspect_ratio)`
      — réutilise la résilience quota TICKET-031 (`_call_with_quota_retry` : pacing,
      retry 429 au délai suggéré) et les hooks TICKET-033 (statut + annulation).
- [x] `axiom/image_generator.py` : backend `"gemini"` — clé absente → None ;
      ratio d'aspect dérivé de `image_width`/`image_height` (liste supportée par l'API) ;
      échec réel → None (règle TICKET-045, pas de mock).
- [x] `ui/settings_dialog.py` : entrée « Google Gemini (cloud) » dans le combo backend +
      champ « Modèle d'image Gemini » (chargement/sauvegarde/retraduction).
- [x] `axiom/localization.py` : clé `image_gemini_model` (en + fr).
- [x] Tests : succès (octets écrits, bon modèle appelé, ratio 16:9), clé absente → None,
      échec API → None + rien sur disque, réponse sans image → None, mapping du ratio.
- [x] Lancer les suites (image_generator 32 ✅, settings_dialog 2 ✅, contrat partagé
      headless+cli_play 15 ✅, startup_check ✅, suite large 518 ✅ + lot vector/Qt 56 ✅).

## Reste (hors code)

- [ ] Validation GUI utilisateur : activer l'illustration avec le backend Gemini et
      jouer un tour réel (nécessite la clé ; le modèle d'image a son propre quota).
