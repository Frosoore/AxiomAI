# DOC — TICKET-062 item 2 : clés Fireworks embarquées + sélecteur de modèles

## Objectif

Qu'un bêta-testeur joue **sans rien configurer** : l'app embarque un pool de
clés Fireworks prépayées (AXIOMAI-0..3, **expirent le 2026-06-30**), utilisées
seulement quand l'utilisateur n'a pas saisi sa propre clé, avec rotation
automatique quand une clé est épuisée/révoquée, et un choix de modèles limité
aux peu coûteux pour préserver le budget partagé.

## Architecture

- **Le moteur publié (PyPI) ne contient aucune clé.** Il offre deux mécanismes
  génériques : `UniversalClient(fallback_api_keys=…)` (rotation collante sur
  401/402/403/429) et `axiom.config.register_builtin_keys(provider, keys)`
  (pool utilisé par `build_llm_from_config` quand la clé utilisateur est vide).
- **Les clés vivent côté app** dans `core/builtin_keys.py`, inversées +
  base64 (anti-regex de scraper ; la vraie protection = pool prépayé, plafonné
  et à durée courte). `main.py` enregistre le pool au démarrage.
- **Prix** : l'API Fireworks n'expose pas les tarifs → table maintenue à la
  main (`FIREWORKS_MODEL_PRICES`, source docs.fireworks.ai/serverless/pricing,
  relevée le 2026-06-12). Plafond clés partagées : entrée ≤ 0,30 $ ET sortie
  ≤ 1,00 $ par million de tokens. Un modèle absent de la table = considéré
  trop cher (un nouveau modèle hors de prix ne passe jamais tout seul).
- **Sélecteur de modèles** (Réglages → Cloud → « Parcourir… ») : liste les
  modèles du fournisseur via son API (hors thread principal), fusionnée avec
  la table de prix pour Fireworks (leur `/models` est incomplet), filtrée au
  plafond quand on tourne sur les clés partagées.

## Maintenance

- **Renouveler/retirer les clés** : régénérer les chaînes via
  `base64.b64encode(cle[::-1].encode())` et remplacer
  `_OBFUSCATED_FIREWORKS_KEYS`. Liste vide = plus aucun pool (l'app exige
  alors une clé utilisateur, comportement d'avant).
- **Après le 2026-06-30** (clés expirées) : retirer le pool et, si on garde le
  zéro-config, soit de nouvelles clés, soit revoir `apply_beta_defaults`.
- **Mettre à jour les prix** : éditer `FIREWORKS_MODEL_PRICES` (et le plafond
  si besoin). Fireworks retire des modèles serverless sans préavis — en cas de
  404 sur le défaut, re-sonder et changer `AppConfig.fireworks_model`.

## Limites assumées

- Les prix sont figés dans le code (pas d'API) — à rafraîchir à la main.
- La rotation traite un 429 de rate-limit comme un 429 de quota : bascule de
  clé dans les deux cas (inoffensif, chaque clé a son propre rate limit).
- Obfuscation = dissuasion de bots, pas de la cryptographie ; risque acté
  par l'utilisateur (ticket), encadré par le prépaiement et l'expiration.
