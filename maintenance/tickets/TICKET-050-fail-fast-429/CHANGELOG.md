# CHANGELOG — TICKET-050 (fail-fast quota 429 « limit: 0 »)

## 2026-06-12 — quota structurellement à zéro → échec immédiat

### Constat
Quand un modèle n'est **pas inclus dans le free tier** de la clé (tous les
modèles d'image, parfois `gemini-2.0-flash` texte : la violation `QuotaFailure`
rapporte `quotaValue: "0"` / `limit: 0`), l'API renvoie tout de même un 429 avec
un `retryDelay` **trompeur** (« retry in 14s »). Or le quota du jour est à zéro :
attendre ne réussira jamais. `_call_with_quota_retry` enchaînait alors 3 retries
avec compte à rebours → **1-2 min de blocage par tour, pour rien** (et par appel
Populate, Chronicler, etc.).

### `axiom/backends/gemini.py`
- **`_is_hard_quota_error(exc)`** : un 429 dont le quota est structurellement
  nul (`limit: 0` ou `quotaValue: 0`, valeur exactement zéro — `limit: 100` ne
  matche pas). Distinct de `_is_quota_error` (qui couvre aussi les quotas
  par-minute récupérables).
- `_call_with_quota_retry` : sur un quota dur, on **saute les retries** du modèle
  courant (`break`) et on passe direct au **modèle de secours** (qui, lui, peut
  être dans le tier gratuit). Les quotas par-minute classiques gardent leurs
  retries + backoff inchangés.
- Message final **actionnable** quand la cause est un quota à 0 : « Gemini quota
  is 0 for this model — it is not included in your API key's free tier. Enable
  billing… or pick a model that is in the free tier (e.g. gemini-2.0-flash). »
  au lieu du générique « quota exhausted after retries ».

Couvre **texte ET image** (backend partagé, même chemin de résilience TICKET-031).

### `tests/test_gemini_client.py` (+4)
- `_is_hard_quota_error` : détecte `quotaValue: 0` et `limit: 0`, rejette le
  quota par-minute récupérable, `limit: 100` et les erreurs non-quota.
- Quota dur sans secours → 1 seul appel, **zéro attente**, message « free tier ».
- Quota dur AVEC secours → primary appelé **une fois** (pas `_MAX+1`), bascule
  sur le secours sans backoff, réponse OK.

### Vérifications
- `pytest tests/test_gemini_client.py` → 38 verts.
- ⚠ Pas de re-vérif sur API réelle (pas de clé Gemini avec un modèle hors tier
  sous la main ; déclencher un vrai `limit: 0` consommerait/ciblerait un modèle
  précis). La logique est couverte par les tests unitaires.
