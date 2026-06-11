# EN_COURS — côté Claude (utilisateur)

> Écrit **uniquement par Claude Code**. Le pote (Gemini) le **lit**, ne l'édite jamais.
> Tenir à jour : déclarer ici les fichiers/modules en cours de modif **avant** d'y toucher ;
> retirer la ligne une fois mergé (pas de réservation périmée).

**Branche courante :** `image-gen`
**Chantier :** Génération d'images — backend Gemini (images via la clé API cloud, sans SD/ComfyUI local)

## Fichiers / modules que je touche en ce moment

| Fichier / module        | Type de modif        | Depuis (date) | Note pour le pote |
|-------------------------|----------------------|---------------|-------------------|
| `axiom/image_generator.py` | + backend `gemini` | 2026-06-10 | nouveau backend d'images via l'API Gemini |
| `axiom/backends/gemini.py` | + méthode `generate_image_bytes` | 2026-06-10 | additif — ne touche pas `complete`/`stream_tokens` |
| `axiom/config.py`       | + champ `image_gemini_model` | 2026-06-10 | additif (dataclass, défaut fourni) |
| `axiom/localization.py` | + clé `image_gemini_model` (en+fr) | 2026-06-10 | additif |
| `ui/settings_dialog.py` | onglet Illustration : choix « Gemini » + champ modèle | 2026-06-10 | additif |
| `tests/test_image_generator.py` | + tests backend gemini + timeout/404 | 2026-06-10 | additif |
| `ui/widgets/chat_display.py` | filtre streaming : fences ```` ```json ```` aussi | 2026-06-10 | `_JSON_OPEN`/`_JSON_CLOSE` → `_JSON_FENCES` (préviens si tu touches le buffer de stream) |
| `axiom/config.py` | + champ `image_timeout` | 2026-06-10 | additif |
| `axiom/image_generator.py` | timeout configurable SD/ComfyUI + 404 explicite | 2026-06-10 | |
| `axiom/image_generator.py` | fix workflow ComfyUI (checkpoint auto via /object_info, VAEDecode `samples`, 400 détaillé) | 2026-06-11 | |
| `tests/test_chat_buffer.py` + `tests/test_phase6.py` | +3 tests backticks / fake aligné | 2026-06-10 | |

## Fichiers chauds que je m'apprête à toucher en profondeur (préviens avant)

- _(rien)_

## Fini / mergé récemment (info pour le pote)

- Tout le tableau précédent (Pilier 2 + UX 028→033 + B3 + B4 + QA 034→048) est **mergé**
  (`9814896`, `2a52332`) — lignes retirées.
