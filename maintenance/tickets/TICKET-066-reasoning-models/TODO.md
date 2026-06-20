# TICKET-066 — Modèles de raisonnement (gpt-oss…) cassent narration + Timekeeper

**Statut : ✅ CHEMIN DE RAISONNEMENT VALIDÉ DE BOUT EN BOUT (2026-06-12, 2ᵉ reprise).**
La 2ᵉ plainte (« attendu, la réponse n'arrive pas » avec fireworks/gpt-oss-20b) a été
**reproduite et la vraie cause trouvée — elle n'est PAS dans le backend de raisonnement**.
Voir **TICKET-068** : le 1ᵉʳ tour de chaque session figeait ~87 s parce que le modèle
d'embedding (`all-MiniLM-L6-v2`) faisait un HEAD réseau vers HF Hub qui stalle sur
l'IPv6 cassée de la machine. Corrigé (`local_files_only=True`).

Ce qui a été **vérifié en réel ce jour** (clé bêta Fireworks, save Myria, API `Session`
= exactement le chemin GUI) :
- gpt-oss-20b en **streaming** via `UniversalClient` : 1ᵉʳ token à ~2 s, fini ~2,8 s.
- **Tour complet sur Myria** : narration streamée correcte, `elapsed_minutes` parsé,
  texte affiché identique entre ce qui est streamé à la GUI et la narration finale
  (pas d'avalement de fence JSON). Après le fix TICKET-068 : 1ᵉʳ token à 3,9 s, tour
  fini en 7,2 s.

Le fix backend de raisonnement (floor de tokens, `reasoning_effort: low`, tolérance
`content` absent) est donc **bon et nécessaire** ; le blocage résiduel « ça marche pas »
était le stall embedding (TICKET-068), indépendant du backend.

Rapport d'origine : partie réelle sur Myria avec **gpt-oss-20b** (clé bêta Fireworks) →
« Generating » longtemps, puis **aucun texte narratif** ; terminal :
`ERROR: [ARBITRATOR] Timekeeper failed: Unexpected response format: 'content'`.

## Cause racine (CONFIRMÉE par sondage API réel)

Les modèles **gpt-oss** (et o-series, deepseek…) sont des modèles de **raisonnement** :
ils mettent leur réflexion dans `message.reasoning_content` et la vraie réponse dans
`message.content`. `max_tokens` plafonne le **total** (raisonnement + réponse), facturé
à l'usage réel. Avec les budgets calibrés pour modèles non-raisonnants (Timekeeper 150,
narration 200-600), le raisonnement mangeait tout le budget → `content` absent/vide →
`KeyError: 'content'` côté Timekeeper, écran vide côté narration.

## Fait (tout dans `axiom/backends/universal.py` + tests)

1. ✅ **Robustesse `complete()`** : `choice.get("message", {}).get("content") or ""` —
   un `content` absent/None est une génération vide, plus un crash (le Timekeeper
   retombe proprement sur le pace-based timing).
2. ✅ **Floor de tokens** : `_is_reasoning_model()` (hints `gpt-oss`, `deepseek-r`,
   `deepseek-v4`, `qwq`, `-thinking`, `-reasoning` + préfixes o-series `o1/o3/o4`)
   → `max_tokens = max(demandé, 2048)` dans `_get_payload` (profite aussi à
   `stream_tokens`). Plafond facturé à l'usage réel → surcoût ~nul.
3. ✅ **`reasoning_effort: "low"`** envoyé pour les modèles gpt-oss uniquement —
   **sondé accepté** par Fireworks (200, content présent, raisonnement court) le
   2026-06-12. Effet majeur sur la latence (Timekeeper : 2,5 s).
4. ✅ **Défaut bêta inchangé** (`gpt-oss-120b`) : la sonde montre que
   `deepseek-v4-flash` est **AUSSI un modèle de raisonnement** (`reasoning_content`
   présent) — en faire le défaut n'apporterait rien ; il est par contre ajouté aux
   hints de détection (le plan initial ne listait que `deepseek-r`).
5. ✅ **Tests** : `tests/test_reasoning_models.py` (13 tests — détection, floor,
   reasoning_effort, content absent/None toléré). 710 + 5 tests verts (suite scindée
   à cause du segfault préexistant → **TICKET-067** dans PENDING.md).
6. ✅ **Vérif réelle** gpt-oss-20b via `UniversalClient` (clé bêta AXIOMAI-0) :
   Timekeeper `max_tokens=150` → 2,5 s, `finish=stop`,
   `tool_call={'elapsed_minutes': 5, …}` (le cas qui crashait) ; narration 200 tokens
   → 1,0 s, texte non vide.

## Reste à faire

- [x] **Diagnostiquer l'échec de la validation GUI du 2026-06-12** → fait :
  cause = stall embedding HF Hub (TICKET-068), pas le backend. Reproduit +
  corrigé.
- [ ] **Re-valider en GUI** : une partie réelle sur Myria avec la clé bêta
  (gpt-oss par défaut) → le texte narratif s'affiche, plus d'erreur Timekeeper,
  « Generating » nettement plus court. (Le chemin moteur est validé en headless ;
  reste la confirmation visuelle dans l'app.)

## Hors scope / liés

- **TICKET-063** (OpenAI o-series : `max_tokens`→`max_completion_tokens`,
  `temperature` figée à 1) reste ouvert — la détection `_is_reasoning_model()`
  couvre déjà les ids o-series, il ne manque que le basculement de paramètres.
- **TICKET-067** (nouveau) : segfault de la grande suite quand `test_ambiance_manager.py`
  précède `test_arbitrator.py` (Qt multimédia puis import natif triton) — préexistant,
  indépendant de ce ticket.

## Repères

- `axiom/backends/universal.py` — `_REASONING_MODEL_HINTS`/`_REASONING_TOKEN_FLOOR`/
  `_is_reasoning_model()` (module), floor + `reasoning_effort` dans `_get_payload`,
  robustesse dans `complete()`.
- Sonde réutilisable : POST `https://api.fireworks.ai/inference/v1/chat/completions`
  avec une clé de `core.builtin_keys.fireworks_builtin_keys()`, regarder
  `choices[0].message` keys + `finish_reason`. Avec `reasoning_effort: low`,
  gpt-oss répond en ~1-3 s (vs 30-90 s avant).
