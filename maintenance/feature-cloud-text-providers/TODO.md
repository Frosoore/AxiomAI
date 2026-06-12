# TODO — feature-cloud-text-providers

Onglet « Cloud » des paramètres : menu déroulant de fournisseur (Gemini, Claude,
Venice AI, Fireworks AI, OpenAI) pour la génération de texte.

- [x] `axiom/backends/universal.py` : `extra_headers` (auth native Anthropic) + `max_stop_sequences` (OpenAI ≤ 4)
- [x] `axiom/config.py` : champs clé/modèle par fournisseur, table `OPENAI_COMPAT_PROVIDERS`, `build_llm_from_config`, résolveurs extraction/time
- [x] `ui/settings_dialog.py` : onglet « Cloud » avec combo fournisseur, champs clé/modèle partagés (stash par fournisseur), lignes fallback/RPM visibles seulement pour Gemini, bouton test générique
- [x] `core/locales/*.toml` (10) : `tab_cloud`, `cloud_provider` (remplace `cloud_gemini`)
- [x] Tests : `test_config.py` (build par fournisseur, clé manquante, résolveurs), `test_settings_dialog.py` (round-trip provider/clés)
- [x] `maintenance/README.md` (ligne d'étape) + `PENDING.md` (tickets découverts)
- [x] Suites vertes (632) + startup check + i18n check
- [x] Session 2 — fournisseur **OpenRouter** (clé/modèle, base URL, header X-Title, défaut `openrouter/auto`)
- [x] Session 2 — bugfix Fireworks : cap `stop` ≤ 4 sur venice/fireworks/openai/openrouter (limite documentée)
- [x] Session 2 — erreurs HTTP enrichies du corps de réponse provider (`_format_status_error`)
- [x] Session 2 — popup « ollama serve » réservé au backend local ; vraie erreur affichée pour le cloud
- [x] Session 2 — suites vertes (634) + startup check
- [x] Session 3 — 404 Fireworks diagnostiqué (modèle retiré) : défaut → `deepseek-v3p1`
- [x] Session 3 — « Test Connection » vérifie le modèle (`list_models` + `_check_model`)
- [x] Session 3 — hint « modèle inconnu » sur les 404 /chat/completions ; suites vertes (637)
- [x] Session 4 — faux négatif corrigé : test cloud = **probe d'1 token** (le `/models` de Fireworks ne liste pas le catalogue public) ; check par liste conservé pour le backend local ; suites vertes (638)
- [ ] ⚠ Validation GUI réelle (utilisateur) : re-tester Fireworks avec un modèle serverless valide, jouer un tour
- [ ] Commit (feu vert utilisateur requis)
