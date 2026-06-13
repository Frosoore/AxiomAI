# CHANGELOG — TICKET-066 (modèles de raisonnement)

## 2026-06-12 — fix complet backend universel

### `axiom/backends/universal.py`
- **Robustesse** (session précédente, validée ici) : `complete()` lit
  `choice.get("message", {}).get("content") or ""` — un `content` absent ou
  null (budget mangé par le raisonnement) est traité comme une génération
  vide au lieu de lever `KeyError: 'content'` (le crash Timekeeper d'origine).
- **Nouveau** : `_REASONING_MODEL_HINTS`, `_REASONING_TOKEN_FLOOR = 2048` et
  `_is_reasoning_model()` (match sur la fin de l'id : `gpt-oss`, `deepseek-r`,
  `deepseek-v4`, `qwq`, `-thinking`, `-reasoning`, préfixes `o1/o3/o4`).
- `_get_payload()` : pour un modèle de raisonnement, `max_tokens =
  max(demandé, 2048)` — le plafond est facturé à l'usage réel, le floor ne
  coûte donc rien et empêche la troncature avant que `content` n'apparaisse.
  S'applique aussi au streaming (même payload).
- `_get_payload()` : `reasoning_effort: "low"` envoyé pour les modèles
  **gpt-oss uniquement** (sondé accepté par Fireworks le 2026-06-12 ; réduit
  la réflexion → Timekeeper passe de 30-90 s à ~2,5 s).

### `tests/test_reasoning_models.py` (nouveau, 13 tests)
- Détection : ids raisonnants reconnus, modèles classiques non, o-series en
  préfixe seulement (`solar-pro4` ne matche pas, `openai/o1-mini` oui).
- Floor : appliqué (150→2048, défaut 1024→2048), budget explicite supérieur
  conservé (4096), modèles classiques intouchés.
- `reasoning_effort` : présent pour gpt-oss, absent pour deepseek-v4-flash
  et les modèles classiques.
- `content` absent ou null → narrative vide, `tool_call=None`, pas de crash
  (MockTransport, même patron que les tests de rotation TICKET-062).

### Décisions
- **Défaut bêta conservé** (`gpt-oss-120b`) : la sonde réelle montre que
  `deepseek-v4-flash` raisonne aussi (`reasoning_content` présent) — le
  basculer en défaut n'aurait rien gagné. Aucun changement config/UI.
- **TICKET-063** (OpenAI o-series, `max_completion_tokens`) laissé ouvert :
  la détection le couvre déjà, seul le basculement de paramètres manque.

### Vérifications
- Sonde API réelle (clé bêta AXIOMAI-0) : `reasoning_effort` accepté (200) ;
  deepseek-v4-flash = raisonnant.
- Vérif réelle gpt-oss-20b via `UniversalClient` : Timekeeper (150 tokens,
  le cas qui crashait) → 2,5 s, `finish=stop`, `elapsed_minutes` parsé ;
  narration → 1,0 s, texte non vide.
- Tests : `test_reasoning_models.py` + `test_builtin_keys.py` +
  `test_config.py` = 64 verts ; grande suite **715 verts en deux passes**
  (`--ignore=tests/test_ambiance_manager.py` → 710, puis le fichier seul → 5)
  à cause d'un segfault d'environnement préexistant Qt-multimédia/triton,
  consigné comme **TICKET-067** dans PENDING.md.
