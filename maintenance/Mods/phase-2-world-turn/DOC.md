# DOC — Phase 2 : Extraction de axiom.world et axiom.turn

## 1. Contexte & Règles d'Architecture
Cette étape franchit le cap décisif de la modularisation du moteur :
- **Règle D1 (Le noyau qui grossit)** : Le noyau n'embarque plus en dur l'orchestration du prompt LLM, le pipeline de tour, ni l'évaluation des règles JDR / entités du monde persistant.
- **Règle D2 (Pas de privilège pour les mods officiels)** : `axiom.world` et `axiom.turn` sont deux mods distincts au format standard `.axmod`, situés dans `mods/`. Ils n'utilisent que `ModContext`, les hooks officiels et les slots déclarés.
- **Règle D11 (Réversibilité totale)** : Si le mod de tour est absent ou désactivé, le noyau ne tente pas d'exécuter un tour par magie et lève une exception explicite `NoTurnPipelineInstalledError`.
- **Règle D12 (API publique versionnée)** : Le moteur expose `KernelStepContext` et `NoTurnPipelineInstalledError`. Le mod `axiom.turn` expose ses propres slots déclarés pour que d'autres mods puissent enrichir les prompts (`axiom.turn:prompt_sections`), intercepter les tokens (`axiom.turn:stream_filter`) ou router de nouveaux champs de tool call (`axiom.turn:output_fields`).

## 2. Le Mod axiom.world (`mods/axiom.world/`)
Prend en charge le modèle de monde persistant :
- **Hooks souscrits** :
  - `axiom.step:gather_context` : enrichit `ctx.world_context` avec les entités actives et lieux connus.
  - `axiom.step:arbitrate_mutations` : exécute la cascade de règles du `RulesEngine` et valide mathématiquement les deltas de statistiques.
- **Slots fournis (`[provides_slots]`)** :
  - `axiom.world:entity_types` (rule = collect) : enregistrement de types d'entités personnalisés.
  - `axiom.world:custom_rules` (rule = collect) : injection de règles personnalisées.
- **Persistance (`[storage]`)** : tables `entities`, `entity_stats`, `rules`, `locations` déclarées sous politique `versioned_kv`.

## 3. Le Mod axiom.turn (`mods/axiom.turn/`)
Prend en charge le pipeline d'arbitrage et d'orchestration du tour :
- **Hook souscrit** :
  - `axiom.kernel:execute_step` : reçoit `KernelStepContext` et pilote le tour en 6 étapes modulaires.
- **Slots fournis (`[provides_slots]`)** :
  - `axiom.turn:prompt_sections` (rule = collect) : injection de sections additionnelles dans le prompt système ou utilisateur.
  - `axiom.turn:output_fields` (rule = collect) : routage de clés JSON retournées par le LLM vers des gestionnaires dédiés.
  - `axiom.turn:stream_filter` (rule = chain) : filtres successifs appliqués en streaming sur chaque token émis.
  - `axiom.turn:final_text_filter` (rule = chain) : filtres successifs appliqués sur le texte narratif complet.
  - `axiom.turn:llm_backend` (rule = exclusive) : remplacement optionnel du backend LLM pour le tour.

## 4. Découplage du Noyau (`Session`)
Dans `axiom/session.py` :
- `Session.__init__` ne crée plus `self._arbitrator = ArbitratorEngine(...)` en dur. Les mods installés sont découverts et chargés via `axiom.kernel.loader`.
- `Session.resolve_tick` crée une instance de `KernelStepContext` et appelle :
  ```python
  self.kernel_registry.execute_hook("axiom.kernel:execute_step", step_context)
  ```
  Si aucun mod n'implémente ce hook, `NoTurnPipelineInstalledError` est levée immédiatement.

## 5. Validation hermétique
```bash
.venv/bin/python -m pytest tests/test_golden_step.py tests/test_kernel_loader.py tests/test_world_turn_mods.py -q
```
Tous les tests sont 100% au vert, confirmant la préservation de l'intégrité déterministe et l'absence totale de dérive d'état.
