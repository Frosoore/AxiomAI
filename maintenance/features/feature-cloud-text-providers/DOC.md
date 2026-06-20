# Fournisseurs cloud de génération de texte

## Objectif
Remplacer l'onglet « Cloud (Gemini) » des paramètres par un onglet « Cloud » générique
avec un menu déroulant de fournisseur : **Google Gemini, Anthropic Claude, Venice AI,
Fireworks AI, OpenAI**. Chaque fournisseur garde sa propre clé API et son propre modèle
dans `settings.json` (changer de fournisseur ne perd pas les clés des autres).

## Décisions techniques
- **Gemini** garde son client natif (`GeminiClient` : quotas 429, fallback, RPM).
- **Claude / Venice / Fireworks / OpenAI** sont tous OpenAI-compatibles → réutilisation du
  `UniversalClient` existant avec une base URL préréglée (table
  `axiom.config.OPENAI_COMPAT_PROVIDERS`). `llm_backend` prend les nouvelles valeurs
  `claude` / `venice` / `fireworks` / `openai`.
- **Claude** : la couche compat OpenAI d'Anthropic (`https://api.anthropic.com/v1`) accepte
  `x-api-key`, mais `GET /v1/models` (test de connexion) refuse un simple Bearer → le client
  s'authentifie en natif via `extra_headers` (`x-api-key` + `anthropic-version`), sans
  header `Authorization` (vérifié en réel : les deux endpoints lisent `x-api-key`).
- **OpenAI** : limite dure de 4 séquences `stop` → `max_stop_sequences=4` sur le client.
  Les modèles « reasoning » (gpt-5/o-series) refusent `temperature`/`max_tokens` → hors
  scope, ticket dans PENDING.md ; défaut `gpt-4.1-mini` (paramètres classiques).
- `resolve_extraction_model` / `resolve_time_model` : sur tout backend cloud, repli sur le
  modèle principal du fournisseur (les noms Ollama locaux n'existent pas chez eux).

## Usage
Paramètres → onglet « Cloud » → choisir le fournisseur, saisir clé + modèle, « Tester la
connexion », sauvegarder avec l'onglet Cloud actif pour activer ce backend.
Défauts : Claude `claude-opus-4-8`, Venice `zai-org-glm-4.7`, Fireworks
`accounts/fireworks/models/llama-v3p3-70b-instruct`, OpenAI `gpt-4.1-mini`.
