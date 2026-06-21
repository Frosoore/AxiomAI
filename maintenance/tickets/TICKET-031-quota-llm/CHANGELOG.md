# TICKET-031 — Résilience aux quotas LLM (429) — CHANGELOG

## 2026-06-10 — implémentation complète (session Claude)

Déclencheur : Populate mort en plein vol sur `429 RESOURCE_EXHAUSTED` (free tier Gemini,
10 req/min/modèle), tout le lot perdu. Trois parades, toutes **côté backend** pour couvrir
tous les appels (Populate, canonisation, narration, Timekeeper, Chronicler) sans toucher
aux appelants :

**Backend (`axiom/backends/gemini.py`) :**
- `_call_with_quota_retry` : sur 429, jusqu'à 3 reprises **en respectant le délai renvoyé
  par l'API** (« Please retry in 32.4s » / `retryDelay`), backoff exponentiel sinon,
  attente plafonnée à 90 s. Toute autre erreur part immédiatement (comportement historique).
- Ralentisseur `_RateLimiter` (module, thread-safe, par modèle) : espacement minimal entre
  requêtes selon `llm_requests_per_minute` (0 = illimité, défaut).
- Modèle de secours `gemini_fallback_model` : si le quota du modèle principal persiste
  après les retries, on bascule (les quotas Google sont PAR MODÈLE, un autre modèle a
  souvent encore du budget). Le streaming (narration) est couvert : le 429 d'un stream
  surgit à l'établissement, le premier chunk est forcé dans la zone de retry.

**Config (`axiom/config.py`) :** + `llm_requests_per_minute` (int, 0) et
`gemini_fallback_model` (str, "") ; `build_llm_from_config` les transmet au client.

**Reprise du Populate (`workers/db_tasks.py`, PopulateEntitiesTask) :** insertion commitée
**par chunk** (avant : tout inséré à la fin → un échec au chunk 3/5 perdait tout). Un échec
LLM en plein lot synchronise la source (TICKET-027), conserve les chunks déjà commités et
lève une erreur explicite (« N entité(s) déjà insérée(s) (chunk i/n). Relancer le Populate
reprendra ici »). L'idempotence existante (ids connus sautés) fait office de reprise.

**GUI (`ui/settings_dialog.py`) :** onglet Gemini — champs « Modèle de secours (quota) » et
« Requêtes max / minute » (0 = Illimité), tooltips explicatifs. Localisation EN + FR.

**Tests :** `tests/test_gemini_client.py` (+7 : parse délai, retry avec délai API, pas de
retry hors quota, fallback après retries, erreur claire si tout épuisé, pacing par modèle,
pas de pacing par défaut), `tests/test_populate_resume.py` (nouveau, 3 : chunks commités
conservés, relance sans doublon, échec au 1er chunk sans message trompeur). Suites vertes :
gemini/config/populate_resume/ollama/localization (76), narrative_worker/session/chronicler
(36), garde-fous collab + startup_check.

**Reste :** validation réelle par l'utilisateur (gros Populate en free tier avec
Requêtes/minute = 9 et un modèle de secours configuré).
