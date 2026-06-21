# Génération d'images contextuelle

## Vision & Objectif
Ajouter au moteur un système autonome de génération d'images illustrant la situation et le contexte du tour de jeu. Ce système doit être compatible avec les applications d'IA génératives locales via leurs API :
1. **Stable Diffusion WebUI (Automatic1111)** via l'API `/sdapi/v1/txt2img`.
2. **ComfyUI** via l'API `/prompt` (soumission de prompt au format workflow).

## Architecture technique
- **Génération du prompt visuel (LLM)** : Le contexte du tour (narration récente, personnages présents, lieu) est envoyé à l'LLM auxiliaire pour extraire un prompt optimisé pour Stable Diffusion (mots-clés descriptifs, style artistique, éléments d'ambiance).
- **Client de génération d'images (`axiom/image_generator.py`)** :
  - Support de plusieurs backends : `stable_diffusion`, `comfyui`, `mock`.
  - Configuration chargée depuis `settings.json` (URL de l'API locale, type de backend, paramètres d'image comme la taille, le modèle, etc.).
  - Sauvegarde des images reçues (au format PNG encodé en base64) dans le dossier d'actifs de la partie.
- **Intégration Session** : Ajout d'une option facultative de génération d'images à la fin de chaque tour, renvoyant le chemin local de l'illustration produite.
