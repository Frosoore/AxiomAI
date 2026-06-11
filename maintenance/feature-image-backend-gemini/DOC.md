# Backend Gemini pour la génération d'images

## Objectif

Les seuls backends d'images réels étaient **locaux** (Stable Diffusion WebUI, ComfyUI) —
inutilisables sans installation dédiée. Ce chantier ajoute un backend **`gemini`** qui
génère les illustrations via l'API Gemini (modèle d'image type « Nano Banana »,
`gemini-2.5-flash-image`), avec la **même clé API** que le texte. La feature devient
utilisable sur une machine sans GPU exploitable.

## Décisions techniques

- **L'appel API vit dans `axiom/backends/gemini.py`** (`GeminiClient.generate_image_bytes`) :
  c'est le module qui connaît le SDK `google-genai`, et ça réutilise telle quelle la
  résilience quota du TICKET-031 (pacing req/min, retry 429 au délai suggéré par l'API)
  et les hooks du TICKET-033 (compte à rebours `on_status`, annulation `cancel_event`).
  `ImageGenerator` ne fait que construire le client et écrire le PNG.
- **Clé / modèle** : réutilise `gemini_api_key` ; nouveau champ `image_gemini_model`
  (défaut `gemini-2.5-flash-image`). Pas de modèle de secours (le fallback texte
  n'est pas un modèle d'image).
- **Dimensions** : l'API Gemini ne prend pas largeur/hauteur mais un **ratio d'aspect**
  (`1:1`, `16:9`, …) — on choisit le ratio supporté le plus proche de
  `image_width`/`image_height`. `image_steps`/`image_cfg_scale` ne s'appliquent pas.
- **Échec → None** (règle TICKET-045) : pas d'image plutôt qu'un placeholder.
  Clé absente → None + warning (pas d'appel réseau).
- SDK trop ancien sans `ImageConfig` → on omet juste le ratio (défaut du modèle).

## Usage

Paramètres → onglet Illustration → activer la génération, moteur de rendu
« Google Gemini (cloud) », modèle d'image (laisser le défaut sauf besoin).
La clé se configure dans l'onglet Gemini comme avant. Quotas : le modèle d'image a
son propre quota, distinct du modèle texte ; un 429 est retenté comme pour le texte
(compte à rebours dans la barre de statut, annulable).
