# TODO — TICKET-062 item 2 : clés Fireworks embarquées + sélecteur de modèles

4 clés fournies par l'utilisateur (2026-06-12) : AXIOMAI-0/1 (6 $) et
AXIOMAI-2/3 (1 $), expirent le 2026-06-30. Décision actée dans le ticket :
embarquées dans le repo avec obfuscation légère, rotation automatique.

- [x] Sondage réel de l'API : 4 clés valides ; `/models` incomplet et sans
      prix ; **défaut `deepseek-v3p1` mort (404)** → remplacé par
      `gpt-oss-120b` ; table de prix relevée sur docs.fireworks.ai
- [x] Moteur : rotation multi-clés dans `UniversalClient`
      (`fallback_api_keys`, bascule collante sur 401/402/403/429)
- [x] Moteur : registre de clés intégrées dans `axiom/config.py`
      (`register_builtin_keys` — le moteur publié ne contient AUCUNE clé)
      + `GeminiClient.list_models()`
- [x] App : `core/builtin_keys.py` (clés obfusquées, table de prix, plafond
      entrée ≤ 0,30 $ / sortie ≤ 1,00 $ par M tokens) + `main.py`
- [x] App : `apply_beta_defaults()` au premier lancement (backend fireworks,
      zéro saisie)
- [x] GUI : bouton « Parcourir… » (worker dédié, prix affichés, filtre
      « pas chers » sur clés partagées, note explicative, placeholder clé)
      + i18n 8 clés ×10 langues + doc()
- [x] Tests unitaires : 23 nouveaux (`tests/test_builtin_keys.py`)
- [x] Vérification réelle : complétion zéro-config OK, rotation réelle
      clé morte → clé valide OK, sélecteur 6 → 3 modèles filtrés
- [ ] ⚠ Validation GUI utilisateur (Réglages → Cloud → Fireworks sans clé :
      Test Connection + Parcourir + une partie réelle)
- [ ] Rappel : retirer/renouveler le pool après expiration le 2026-06-30
