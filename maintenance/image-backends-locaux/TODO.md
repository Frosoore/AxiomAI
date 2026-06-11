# TODO — Fiabiliser les backends d'images locaux (SD WebUI / ComfyUI)

Contexte : l'utilisateur teste avec `stable-diffusion-webui-reForge` en local (API A1111).

- [x] Diagnostiquer pourquoi « ça ne fonctionne pas » : reForge était lancé **sans `--api`**
      → `/sdapi/v1/*` en 404. Activé en permanence dans
      `~/stable-diffusion-webui-reForge/webui-user.sh` (`COMMANDLINE_ARGS="--api"`).
- [x] Timeout configurable `image_timeout` (défaut 180 s) — le 30 s en dur condamnait toute
      machine lente (la 1ʳᵉ image charge le modèle : ~36 s rien que ça chez l'utilisateur).
      Utilisé par la requête SD ET le polling ComfyUI (1 poll/s jusqu'au timeout, au lieu
      de 60 s fixes).
- [x] Messages d'erreur actionnables : 404 SD → « serveur lancé sans --api » (vérifié en
      réel contre le reForge tournant) ; timeout → « augmentez le délai dans les réglages ».
- [x] UI : champ « Délai max par image » (10–900 s) dans l'onglet Illustration + i18n en/fr.
- [x] Tests : timeout transmis à la requête SD, timeout custom, 404 → None sans exception,
      polling ComfyUI borné par `image_timeout` (+4, fichiers image_generator/settings_dialog).
- [x] Suites vertes (image_generator 16, settings_dialog 2, suite large 523, lot Qt/vector 56).
- [x] **ComfyUI : workflow par défaut invalide** (2026-06-11, erreurs réelles utilisateur) :
      checkpoint `v1-5-pruned-emaonly.ckpt` codé en dur (absent de toute install réelle)
      → résolu via `GET /object_info/CheckpointLoaderSimple` (checkpoint manquant remplacé
      par le 1ᵉʳ installé) ; entrée VAEDecode `latent_image` → `samples` (nom attendu par
      ComfyUI) ; rejet 400 de validation → warning détaillé nœud par nœud + None.
- [x] Tests : +3 (checkpoint substitué + samples, /object_info injoignable → workflow
      intact, 400 validation → None) ; suites vertes (image_generator 18, large 525, Qt/vector 56).

## Reste (hors code)

- [ ] **Utilisateur : relancer reForge** (Ctrl+C puis `./webui.sh` — le `--api` est désormais
      permanent) puis jouer un tour avec backend « Stable Diffusion (WebUI) »,
      URL `http://127.0.0.1:7860`.
- [ ] Premier tour : prévoir ~1 min (chargement modèle + génération) — le tour reste bloqué
      pendant ce temps (génération en arrière-plan = chantier séparé, non lancé).
- [ ] **Utilisateur : retester ComfyUI** après le fix workflow (le checkpoint
      `ilustmix_v111.safetensors` sera choisi automatiquement).
