# TODO — QA-test-connexion-gemini

Rapport utilisateur (2026-06-12) : « Test Connection » de la clé Gemini dans
Réglages → Cloud ne répond pas (semble mort). QA du système d'API après la
feature `feature-cloud-text-providers`.

- [x] Relire le flux complet du bouton « Test Connection » (settings_dialog →
      ConnectionTestWorker → build_llm_from_config → GeminiClient.is_available)
- [x] Reproduire en headless avec la config réelle de l'utilisateur
- [x] Diagnostiquer la cause racine (IPv6 cassé vers Google + aucun timeout
      de connexion dans le SDK google-genai)
- [x] GeminiClient : injecter un timeout de connexion via un transport httpx
      custom (le SDK passe `timeout=None` à chaque requête, ce qui désactive
      tout timeout configuré au niveau client)
- [x] UniversalClient : timeout de connexion explicite (le scalaire 600 s
      s'appliquait aussi à la phase connect)
- [x] Tests unitaires (injection du connect timeout, configuration httpx)
- [x] Vérification réelle : is_available() → True en 20,3 s sur la machine
      (IPv6 cassée) au lieu de bloquer 5 min+
- [x] Suites de tests existantes vertes (609 + 56 Qt/vector)

## Itération 2 — « IPv4 d'abord » (demande utilisateur : quasi instantané)

- [x] Module partagé `axiom/backends/transport.py` : `IPv4FirstTransport`
      (IPv4 épinglée d'abord, fallback dual-stack mémorisé, connect timeout)
- [x] Branché dans `gemini.py` et `universal.py`
- [x] Tests réécrits/ajoutés (7) ; suites vertes (612 + 56 Qt/vector)
- [x] Vérification réelle : `is_available()` → True en **0,27 s** (avant
      itération 2 : 20,3 s ; avant tout fix : > 5 min)
- [ ] ⚠ Validation GUI réelle par l'utilisateur (bouton « Test Connection »,
      ✓ attendu en ~1 s)
