# CHANGELOG — Phase 2 : Extraction de axiom.providers, axiom.illustrations & Hooks Universe-as-Code

## [Phase 2] - 2026-09-27

### Ajouts

- **Mod officiel `axiom.providers` (`mods/axiom.providers/`)** :
  - `mod.toml` : Manifeste déclarant le service `llm_providers`, dépendance `axiom.turn >= 1.0.0`, slot ouvert `axiom.providers:drivers` (`rule = "collect"`), et contribution au slot `axiom.turn:llm_backend`.
  - `main.py` : Enregistrement du service `providers` fournissant les pilotes Google Gemini et Universal/OpenAI-compatible. Implémentation du slot ouvert permettant à des tiers d'enregistrer des pilotes personnalisés (Mistral, Anthropic, local custom, mock). Résolution dynamique du backend selon la configuration active.
  - Empaquetage dans `dist/mods/axiom.providers.axmod`.

- **Mod officiel `axiom.illustrations` (`mods/axiom.illustrations/`)** :
  - `mod.toml` : Manifeste déclarant le service `illustrations`, politique de stockage custom `assets` dans `[storage]`, et hook `axiom.step:after_step`.
  - `main.py` : Service `illustrations` gérant la génération de visuels de scène (SD WebUI, ComfyUI, Gemini Imagen) via les `post_commit_callbacks` du tour transactionnel. Enregistrement auprès du `storage_registry` de la politique `assets` avec nettoyage automatique des illustrations orphelines lors d'un rewind.
  - Empaquetage dans `dist/mods/axiom.illustrations.axmod`.

- **Hooks Universe-as-Code (§11)** :
  - `axiom/compile.py` : Ajout du paramètre optionnel `kernel_registry` et exécution du hook `axiom.universe:compile` transmettant le contexte `{src_tree, conn, universe_toml}`.
  - `axiom/decompile.py` : Ajout du paramètre optionnel `kernel_registry` et exécution du hook `axiom.universe:decompile` transmettant le contexte `{db_conn, target_dir}`.
  - `axiom/dev.py` : Ajout du paramètre optionnel `kernel_registry` et exécution du hook `axiom.universe:refresh_definition` transmettant le contexte `{src_tree, conn, universe_toml}`.

- **Suite de tests d'intégration (`tests/test_providers_illustrations_mods.py`)** :
  - `test_manifests_and_loading` : Chargement et validation depuis dossiers et archives `.axmod`.
  - `test_custom_driver_registration_and_activation` : Enregistrement d'un pilote LLM tiers via le slot ouvert `axiom.providers:drivers` et exécution au tour.
  - `test_illustrations_and_rewind_cleanup` : Génération d'assets graphiques et suppression automatique au rewind.
  - `test_universe_as_code_mod_extension` : Extension déclarative du format `universe.toml` via les hooks de compilation et décompilation.
  - `test_full_turn_with_all_official_mods_and_implicit_llm` : Validation d'un tour de jeu complet avec l'ensemble des 9 mods officiels actifs sans instanciation explicite de LLM.

### Modifications & Découplages

- **Noyau (`axiom/session.py`)** :
  - L'argument `llm` de `Session.__init__` devient optionnel (`llm: LLMBackend | None = None`). Si omis, la session interroge le slot `axiom.turn:llm_backend` ou le service `"providers"`.
  - Suppression complète du bloc procédural de génération d'images dans `Session.resolve_tick`. Le déclenchement est entièrement délégué au hook `axiom.step:after_step` du mod `axiom.illustrations`.
- **Mod `axiom.turn` (`mods/axiom.turn/main.py`)** :
  - Support des fabriques/callables pour le slot `axiom.turn:llm_backend`.
  - Préséance explicite pour `step_context.llm` lorsqu'il est fourni (permettant les tests hermétiques et mocks de harness).
  - Réempaquetage dans `dist/mods/axiom.turn.axmod`.
