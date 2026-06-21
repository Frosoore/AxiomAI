# Backends d'images locaux (SD WebUI / ComfyUI) — fiabilisation

## Usage

- **Stable Diffusion WebUI / reForge** : lancer le serveur avec `--api` (désormais permanent
  dans le `webui-user.sh` de l'utilisateur). Dans Axiom : onglet Illustration → moteur
  « Stable Diffusion (WebUI) », URL `http://127.0.0.1:7860`.
- **Délai max par image** (nouveau réglage, défaut 180 s) : temps d'attente maximal pour la
  requête SD ou le polling ComfyUI. À augmenter sur machine lente — la **première** image
  d'une session inclut le chargement du modèle côté serveur.
- En cas d'échec : pas d'image pour ce tour (règle TICKET-045) + warning précis dans les logs
  (404 = API non activée ; timeout = délai à augmenter ; connexion refusée = serveur éteint).

## Décisions

- Le timeout est **un seul réglage** pour SD et ComfyUI (même besoin, pas de raison d'en
  exposer deux). Borne basse 10 s, haute 900 s.
- Le 404 est intercepté avant `raise_for_status` pour produire un message ciblé : c'est
  l'erreur de configuration la plus probable (serveur lancé sans `--api`), vérifiée en réel.
