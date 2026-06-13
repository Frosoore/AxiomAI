# CHANGELOG — TICKET-062 item 2 : clés Fireworks embarquées + sélecteur de modèles

## Session du 2026-06-12

### Sondage réel (avant design)
- **Les 4 clés fournies (AXIOMAI-0..3, expirent 2026-06-30) sont valides.**
- `/models` Fireworks : 6 modèles listés, **aucune info de prix** (table de
  prix maintenue à la main depuis docs.fireworks.ai/serverless/pricing).
- Le listing est **incomplet** : `gpt-oss-20b`, `deepseek-v4-flash` et
  `qwen3p6-plus` répondent en génération sans être listés.
- ⚠ Le modèle Fireworks par défaut de l'app (`deepseek-v3p1`) renvoie **404**
  (retiré du serverless) → défaut changé vers `gpt-oss-120b`
  (0,15 $/0,60 $ par M tokens, vérifié vivant).

### Moteur (`axiom/` — aucune clé dans le wheel)
- `UniversalClient` : **rotation multi-clés** — nouveau paramètre
  `fallback_api_keys`, bascule collante vers la clé suivante sur 401/402/403/
  429 (`_send_with_rotation`), branchée dans `complete`, `stream_tokens`
  (avant le premier token), `is_available`, `list_models`.
- `axiom/config.py` : **registre de pools** (`register_builtin_keys`/
  `get_builtin_keys`/`uses_builtin_keys`) — `build_llm_from_config` utilise le
  pool enregistré quand l'utilisateur n'a pas de clé pour le fournisseur ;
  défaut `fireworks_model` → `gpt-oss-120b`.
- `GeminiClient.list_models()` ajouté (préfixe `models/` retiré, filtré
  `generateContent`) pour le sélecteur.

### App
- **`core/builtin_keys.py`** : les 4 clés obfusquées (inversées + base64 — les
  regex `fw_…` des scrapers ne matchent pas le texte du repo), table de prix
  des 8 modèles serverless connus, plafond « clés partagées » (entrée
  ≤ 0,30 $ ET sortie ≤ 1,00 $/M → `gpt-oss-120b`, `gpt-oss-20b`,
  `deepseek-v4-flash`), `register_builtin_providers()` et
  `apply_beta_defaults()` (1ᵉʳ lancement sans settings.json → backend
  `fireworks`, zéro saisie).
- `main.py` : enregistrement du pool + défauts bêta au démarrage.
- **GUI (onglet Cloud)** : bouton « Parcourir… » à côté du champ modèle →
  `workers/model_list_worker.py` (listing hors thread principal) → dialogue
  de sélection (double-clic OK, prix affichés quand connus). Sur les clés
  partagées : liste filtrée aux modèles « pas chers » + note explicative.
  Placeholder du champ clé : « Laisser vide pour utiliser les clés bêta
  partagées » quand un pool couvre le fournisseur. i18n complet (8 clés ×10
  langues), `doc()` + entrée `settings.browse_models` du registre d'aide.

### Tests
- Nouveau `tests/test_builtin_keys.py` (23) : décodage du pool (sans clé en
  clair dans le test), registre, `uses_builtin_keys`, `build_llm` avec/sans
  pool, plafond de prix, rotation via `httpx.MockTransport` (429/401/402,
  collante, pas de rotation sur 500, stream, list_models), entrées du
  sélecteur, défauts premier lancement (config injectée).
- 1 assertion mise à jour (`test_settings_dialog`, ancien défaut mort).
- `tools/i18n_check.py` : 535/535 ×10 langues ; `tools/doc_check.py` : OK.

### Vérification réelle (vraies clés)
- Pool zéro-config détecté, complétion 1 token sur le défaut OK.
- **Rotation réelle** : clé morte en tête de pool → bascule loggée sur la
  vraie clé, complétion OK.
- Sélecteur : 6 modèles listés → 3 proposés en mode clés partagées, prix
  corrects.
- Suites : 647 tests verts (grande suite hors Qt/vector).

## 2026-06-12 (session 2) — kill-switch + re-vérif rotation

Demande utilisateur : pouvoir **retirer l'offre « clés gratuites »** facilement
quand le pool prépayé expirera (2026-06-30) **sans supprimer le code**, et
confiance sur le **fallback clé épuisée → clé avec quota**.

### `core/builtin_keys.py`
- **`BUILTIN_KEYS_ENABLED: bool = True`** : interrupteur maître. À `False`,
  `register_builtin_providers()` et `apply_beta_defaults()` deviennent des
  no-ops → pool jamais enregistré (`get_builtin_keys` vide), filtre
  d'abordabilité éteint, placeholder « clés bêta » masqué, et un utilisateur
  fireworks sans clé reçoit le message clair « add your key ». Les clés, la
  table de prix et la rotation **restent en place**, réactivables d'un flip.

### `tests/test_builtin_keys.py` (+4)
- `TestKillSwitch` : register no-op quand off / peuple le pool quand on, défaut
  bêta sauté quand off, fireworks sans clé → `ValueError("no API key")` off.

### Vérification réelle (vraies clés, rotation)
- **Complétion** : fausse clé en tête + vrai pool en spare → 401 → bascule
  loggée « spare key 2/5 » → réponse « OK » (idx 0→1).
- **Streaming** (chemin narration) : même setup → bascule avant le 1ᵉʳ token →
  « OK ». Les deux chemins de rotation confirmés sains.
- `pytest tests/test_builtin_keys.py` → 27 verts.
