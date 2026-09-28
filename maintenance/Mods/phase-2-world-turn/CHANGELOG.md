# CHANGELOG — Phase 2 : Extraction de axiom.world et axiom.turn

## 2026-09-27
- Extraction du mod officiel `axiom.world` dans `mods/axiom.world/` :
  - Manifeste `mod.toml` avec déclaration des hooks `axiom.step:gather_context`, `axiom.step:arbitrate_mutations`, des slots `axiom.world:entity_types`, `axiom.world:custom_rules`, et des politiques de stockage versionnées pour les entités, stats, règles et lieux.
  - Implémentation du point d'entrée standard `main.py` : injection de contexte et entités spatiales dans `on_gather_context`, cascades du `RulesEngine` et validation mathématique des deltas dans `on_arbitrate_mutations`.
- Extraction du mod officiel `axiom.turn` dans `mods/axiom.turn/` :
  - Manifeste `mod.toml` exposant le hook `axiom.kernel:execute_step` et les slots d'extension `axiom.turn:prompt_sections`, `axiom.turn:output_fields`, `axiom.turn:stream_filter`, `axiom.turn:final_text_filter`, `axiom.turn:llm_backend`.
  - Implémentation de `on_execute_step` dans `main.py` orchestrant le cycle complet des 6 étapes du tour à travers `TurnContext`, l'application des chaînes de filtres de streaming et de texte final, et le routage déclaratif des champs d'outils.
- Découplage complet du noyau Axiom :
  - Création de `KernelStepContext` et `NoTurnPipelineInstalledError` dans `axiom/kernel/step_context.py` (exportés dans `axiom/kernel`).
  - Évolution de `axiom/kernel/manifest.py` et `axiom/kernel/loader.py` pour supporter `provides_slots` et auto-déclarer les slots déclarés par les manifestes.
  - Évolution de `axiom/kernel/registry.py` avec `apply_slot_chain`, `get_slot_contributions`, `execute_hook`, `has_hook`, et préservation de la propagation de `GenerationCancelled`.
  - Modification de `Session.__init__` dans `axiom/session.py` : suppression de l'instanciation directe de `ArbitratorEngine`, chargement modulaire des mods installés.
  - Modification de `Session.resolve_tick` : dispatch synchrone via `self.kernel_registry.execute_hook("axiom.kernel:execute_step", step_context)` avec levée explicite de `NoTurnPipelineInstalledError` si le hook est absent.
  - Découplage de `ArbitratorEngine` (`step_1_gather_context` et `step_5_arbitrate_rules`) vers les hooks d'étape.
- Création de la suite de tests hermétique `tests/test_world_turn_mods.py` (6 tests d'acceptation au vert) :
  - Conformité des manifestes et chargement direct / archivé `.axmod`.
  - Contribution tierce au slot `axiom.turn:prompt_sections` sans modifier le noyau ni le mod `axiom.turn`.
  - Levée immédiate de `NoTurnPipelineInstalledError` en l'absence de mod de turn.
  - Chaînes de filtrage de streaming et texte final (`stream_filter`, `final_text_filter`).
  - Routage dynamique des champs de sortie du LLM (`output_fields`).
  - Validation de mutations d'état complètes de bout-en-bout.
- Packaging des mods vers `dist/mods/axiom.world.axmod` et `dist/mods/axiom.turn.axmod`.
- Validation hermétique Golden Step à 100% (31 tests passants sans régression).
