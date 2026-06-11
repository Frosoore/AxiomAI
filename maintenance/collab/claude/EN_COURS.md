# EN_COURS — côté Claude (utilisateur)

> Écrit **uniquement par Claude Code**. Le pote (Gemini) le **lit**, ne l'édite jamais.
> Tenir à jour : déclarer ici les fichiers/modules en cours de modif **avant** d'y toucher ;
> retirer la ligne une fois mergé (pas de réservation périmée).

**Branche courante :** `main`
**Chantier :** _(aucun en cours — dernier merge : packaging pip + génération d'images, 2026-06-11)_

## Fichiers / modules que je touche en ce moment

| Fichier / module        | Type de modif        | Depuis (date) | Note pour le pote |
|-------------------------|----------------------|---------------|-------------------|
| _(rien)_ | | | |

## Fichiers chauds que je m'apprête à toucher en profondeur (préviens avant)

- _(rien)_

## Fini / mergé récemment (info pour le pote)

- Tout le tableau précédent (Pilier 2 + UX 028→033 + B3 + B4 + QA 034→048) est **mergé**
  (`9814896`, `2a52332`) — lignes retirées.
- **Packaging pip du moteur** (TICKET-009 clos : `pyproject.toml` racine, package PyPI
  `axiomai-engine`, `export_engine.py`, `axiom.help`) — **mergé dans `main`** (`fbe8b6e`).
- **Génération d'images** (branche `image-gen`, **mergée dans `main` le 2026-06-11**) :
  backend Gemini cloud (`image_gemini_model`), fiabilisation SD WebUI/ComfyUI
  (`image_timeout`, 404 → message --api, fix workflow ComfyUI : checkpoint auto via
  `/object_info` + VAEDecode `samples`), filtre streaming étendu aux fences ```` ```json ````
  (`ui/widgets/chat_display.py` : `_JSON_FENCES` — préviens si tu touches le buffer de stream).
