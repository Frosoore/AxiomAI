# TICKET-050 — Gemini 429 « limit: 0 » : fail-fast au lieu de retries inutiles

**Statut : ✅ CODE FAIT + tests verts (2026-06-12). ⚠ re-vérif API réelle optionnelle.**

## Fait
- `_is_hard_quota_error()` (quota structurellement à 0) dans `axiom/backends/gemini.py`.
- Retries sautés sur quota dur, bascule directe sur le modèle de secours.
- Message actionnable « hors free tier ».
- +4 tests (`tests/test_gemini_client.py`), 38 verts.

## Reste (optionnel)
- [ ] Re-vérif sur API réelle avec un modèle hors tier (image, ou texte hors
  free tier) → l'échec doit être immédiat, message clair, plus de compte à
  rebours. (Couvert par les tests unitaires en attendant.)
