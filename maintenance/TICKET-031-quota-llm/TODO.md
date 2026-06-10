# TICKET-031 — Résilience aux quotas LLM (429) — TODO

Demande utilisateur 2026-06-10 : un Populate (free tier Gemini, 10 req/min) meurt en plein
vol sur `429 RESOURCE_EXHAUSTED` et tout le lot est perdu. Souhaité : reprendre là où on
s'est arrêté (éventuellement avec un autre modèle) et/ou un ralentisseur respectant les quotas.

- [x] Backend Gemini : retry automatique sur 429 en respectant le délai renvoyé par
      l'API (`Please retry in Xs` / `retryDelay`), backoff exponentiel sinon, plafonné (90 s)
- [x] Backend Gemini : ralentisseur (requêtes/minute configurable, 0 = illimité),
      partagé entre threads, par modèle — couvre aussi narration/Timekeeper/Chronicler
- [x] Backend Gemini : modèle de secours (`gemini_fallback_model`) tenté quand le quota
      du modèle principal persiste après les retries (quotas par modèle chez Google)
- [x] Config : `llm_requests_per_minute` + `gemini_fallback_model` (+ branchement
      `build_llm_from_config`)
- [x] Populate entités : insertion **par chunk** (commit incrémental) — un échec en plein
      lot conserve le travail déjà fait ; relancer reprend (les ids existants sont sautés),
      message d'erreur explicite (« N entité(s) déjà insérée(s)… relancer reprendra ici »)
- [x] Settings GUI : champs « Requêtes max/minute » et « Modèle de secours » (onglet Gemini)
- [x] Localisation EN + FR
- [x] Tests : parse du délai, retry/fallback/pacing (SDK mocké, 7 tests), reprise du
      Populate (3 tests)
- [ ] Validation GUI réelle par l'utilisateur (relancer un gros Populate en free tier,
      avec p.ex. Requêtes/minute = 9 et un modèle de secours)
