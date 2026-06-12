# CHANGELOG — feature-cloud-text-providers

## 2026-06-12 — session 1 (code terminé, commit en attente de feu vert)

- `axiom/backends/universal.py` : constructeur étendu (rétro-compatible) —
  `extra_headers` (schéma d'auth non-Bearer, fusionné dans chaque requête) et
  `max_stop_sequences` (tronque la liste `stop` envoyée).
- `axiom/config.py` :
  - 8 nouveaux champs `AppConfig` : `anthropic_api_key/model`, `venice_api_key/model`,
    `fireworks_api_key/model`, `openai_api_key/model` (défauts : `claude-opus-4-8`,
    `zai-org-glm-4.7`, `accounts/fireworks/models/llama-v3p3-70b-instruct`, `gpt-4.1-mini`) ;
  - table `OPENAI_COMPAT_PROVIDERS` (base URL + champs par fournisseur) et tuple
    `CLOUD_BACKENDS` ;
  - `build_llm_from_config` accepte `llm_backend` ∈ {claude, venice, fireworks, openai}
    → `UniversalClient` préconfiguré. Claude : auth native `x-api-key` +
    `anthropic-version` (le `GET /v1/models` d'Anthropic refuse un Bearer simple —
    vérifié en réel). OpenAI : `stop` plafonné à 4. Clé manquante → `ValueError`
    (même contrat que gemini) ;
  - `resolve_extraction_model` / `resolve_time_model` généralisés à tous les backends
    cloud via `_cloud_main_model` (repli sur le modèle principal du fournisseur).
- `ui/settings_dialog.py` : onglet « Cloud (Gemini) » → onglet **« Cloud »** générique —
  combo fournisseur (Gemini / Claude / Venice AI / Fireworks AI / OpenAI), champs
  clé/modèle partagés avec stash par fournisseur (changer de fournisseur ne perd aucune
  clé), lignes fallback/RPM visibles seulement pour Gemini (`setRowVisible`), bouton
  « Tester la connexion » générique (`_test_cloud`), placeholders par fournisseur.
  Sauvegarde avec l'onglet Cloud actif → `llm_backend` = fournisseur sélectionné.
- `core/locales/*.toml` (10 langues) : clé `cloud_gemini` remplacée par `tab_cloud` +
  nouvelle clé `cloud_provider` — couverture i18n 296/296 OK.
- Tests : +7 dans `tests/test_config.py` (build par fournisseur, headers Claude, cap
  stop OpenAI, clé manquante, override, round-trip persistance, résolveurs) ; +3 dans
  `tests/test_settings_dialog.py` (dropdown, stash/round-trip, défauts modèles).
- Vérifié : **632 tests verts** + `debug/startup_check.py` OK + `tools/i18n_check.py` OK.
- Au passage : pytest/pytest-mock/pytest-qt réinstallés dans `.venv` (manquaient alors
  qu'ils sont dans `requirements-dev.txt`).
- Tickets ouverts en chemin : TICKET-061 (modèles reasoning OpenAI gpt-5/o-series :
  `max_completion_tokens`, `temperature` figée), TICKET-062 (backend d'images Venice AI).

⚠ Reste : validation GUI réelle (sélection fournisseur + test connexion + partie jouée).

## 2026-06-12 — session 2 (retour utilisateur : bug Fireworks + OpenRouter)

- **Bug rapporté** : Fireworks AI → « Test Connection » OK mais la génération échoue avec
  le popup « The LLM server is not responding / To start Ollama… ». Diagnostic :
  1. **Cause racine probable** : Venice ET Fireworks (comme OpenAI) **plafonnent `stop` à
     4 séquences** (vérifié dans leurs docs API) — le client en envoyait 7 → 400 à la
     génération, alors que `GET /models` (test de connexion) passe. Le cap `max_stops=4`
     est maintenant porté par la table `OPENAI_COMPAT_PROVIDERS` (4ᵉ élément) et appliqué
     à venice/fireworks/openai/openrouter ; Claude garde la liste complète (pas de limite
     documentée sur sa couche compat).
  2. **Popup trompeur** : `tabletop_view._on_worker_error` affichait le guide « ollama
     serve » dès que le message contenait "connection"/"404", même sur un backend cloud →
     le guide n'apparaît plus que pour `universal`/`ollama` ; pour le cloud, le popup
     montre la **vraie erreur**. Conditions élargies ("llm unreachable", "llm api error").
  3. **Erreurs muettes** : `UniversalClient` réduisait un 400 à « Bad Request » sans le
     corps de la réponse → nouveau `_format_status_error` (status + URL + corps ≤300 c.)
     branché sur `complete()` et `stream_tokens()`.
- **OpenRouter ajouté** au menu déroulant (6ᵉ fournisseur) : `openrouter_api_key`/
  `openrouter_model` (défaut `openrouter/auto`), base `https://openrouter.ai/api/v1`,
  header d'attribution `X-Title: Axiom AI`, cap stops 4. UI + persistance + tests.
- Tests : +3 (`test_openrouter_backend_builds_universal_client`,
  `test_stop_sequences_capped_where_documented` ×5 providers,
  `test_status_error_message_includes_provider_body`) ; assertions dropdown mises à jour.
- Vérifié : **634 tests verts** + `debug/startup_check.py` OK.

⚠ Reste : re-tester Fireworks en GUI réelle (le 400 stop>4 est corrigé ; si l'erreur
persiste, le popup affichera désormais la réponse exacte du provider — me la transmettre).

## 2026-06-12 — session 3 (2ᵉ retour utilisateur : 404 Fireworks)

- Le nouveau popup a fait son travail : **`LLM API error 404 from .../chat/completions`**
  → le serveur répond, c'est **le modèle qui n'existe pas/plus**. Le défaut choisi en
  session 1 (`llama-v3p3-70b-instruct`) n'est plus servi en serverless chez Fireworks.
- **Défaut Fireworks** → `accounts/fireworks/models/deepseek-v3p1` (l'id utilisé par les
  exemples officiels de leur doc). ⚠ Un `settings.json` déjà sauvegardé garde l'ancien id :
  vider le champ Modèle (re-bascule sur le nouveau défaut) ou saisir un id valide.
- **« Test Connection » vérifie maintenant le modèle** : `UniversalClient.list_models()`
  (GET /models → ids) + `ConnectionTestWorker._check_model()` — serveur joignable mais
  modèle absent ⇒ « ✗ Connected, but model 'X' was not found on this server ». Tolère les
  ids Ollama « name:tag » et reste permissif si /models ne liste rien. Vaut pour les 5
  providers OpenAI-compat ET le backend local (Gemini : pas de list_models → inchangé).
- **Hint 404** dans `_format_status_error` : un 404 sur /chat/completions ajoute « the
  configured model does not exist on this provider — check the Model field in Settings ».
- Tests : +4 (worker modèle inconnu / modèle connu+tag+liste vide, hint 404, défaut
  fireworks mis à jour). Vérifié : **637 tests verts** + startup check OK.

## 2026-06-12 — session 4 (3ᵉ retour : le check par /models rejetait des modèles valides)

- **Faux négatif de la session 3** : chez Fireworks, `GET /models` ne renvoie que les
  modèles **du compte** (déploiements/fine-tunes), pas le catalogue serverless public →
  tout modèle public valide (ex. `accounts/fireworks/models/minimax-m2p7`) était déclaré
  introuvable par le « Test Connection ».
- **Fix** : pour les providers OpenAI-compat, le test valide désormais le modèle par une
  **vraie complétion d'1 token** (`ConnectionTestWorker._probe`, coût négligeable,
  uniquement au clic) — c'est la vérité terrain et l'erreur exacte du provider remonte
  (modèle inconnu, clé sans permission, crédits épuisés…). Le check par liste
  (`_check_model`) reste pour le backend **local** (Ollama/LM Studio : /models exact, et
  un probe y chargerait le modèle à froid). Gemini : inchangé (son client retry les 429).
- `ConnectionTestWorker(llm, probe_model=...)` ; le dialog passe `probe_model=True` quand
  le provider ∈ `OPENAI_COMPAT_PROVIDERS`.
- Tests : +1 (probe OK/KO). Vérifié : **638 tests verts** + startup check OK.
