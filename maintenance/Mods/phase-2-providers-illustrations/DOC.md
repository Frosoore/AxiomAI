# DOC — Phase 2 : Extraction de axiom.providers, axiom.illustrations & Hooks Universe-as-Code

## 1. Objectifs & Dérives ciblées

Ce bloc d'instructions achève la phase d'extraction modulaire des fonctionnalités majeures du moteur Axiom AI en s'attaquant à l'inférence LLM, à la génération d'images et à l'extensibilité du format Universe-as-Code.

* **D1 (Le noyau qui grossit) :** Le noyau (`axiom/session.py`) ne contient plus aucune instanciation en dur de SDKs d'inférence ni de logique procédurale de génération d'images.
* **D2 (Pas de privilège pour les mods officiels) :** Les pilotes LLM s'enregistrent via un slot ouvert (`axiom.providers:drivers`) et contribuent au slot exclusif `axiom.turn:llm_backend` comme le ferait un mod tiers.
* **D7 (Le rewind unifié) :** Les assets générés sur disque (`turn_N.png`) sont déclarés via la politique de stockage déclarative `assets = { policy = "custom" }` et automatiquement épurés lors d'un rewind via `storage_registry`.
* **D10 (Système ouvert aux besoins imprévus) :** Tout mod tiers peut injecter son propre fournisseur d'IA (Anthropic, Mistral, llama.cpp, etc.) sans toucher au code de `axiom/` ni de `axiom.providers`.
* **§11 (Universe-as-Code & mods) :** La compilation, décompilation et le rechargement à chaud d'univers invoquent désormais des hooks officiels pour permettre aux mods d'étendre la structure de `universe.toml` et les tables de base de données d'univers.

---

## 2. Architecture & Composants

### A. Mod `axiom.providers` (`mods/axiom.providers/`)
* **Slot ouvert `axiom.providers:drivers`** (`rule = "collect"`) : Permet l'enregistrement de pilotes tiers sous forme de tuples `(name, builder_callable)` ou dictionnaires `{"id": name, "builder": builder_callable}`.
* **Slot exclusif `axiom.turn:llm_backend`** : Fournit une fabrique résolvant dynamiquement le backend selon `AppConfig.llm_backend`.
* **Service `providers`** : Offre les méthodes `register_driver`, `get_driver`, `list_drivers`, et `get_backend(model_override=None)`.

### B. Mod `axiom.illustrations` (`mods/axiom.illustrations/`)
* **Hook `axiom.step:after_step`** : Inspecte le résultat narratif du tour et schedule la génération de l'image de scène dans les `post_commit_callbacks` du `TurnWriteBatch`.
* **Stockage custom `assets`** : Déclaré dans `[storage]` et enregistré dans le `storage_registry` avec un `rewind_callback`. Lors de `session.rewind(target_turn)`, toutes les images `turn_N.png` où `N > target_turn` sont supprimées du disque.
* **Service `illustrations`** : Offre `generate_scene_art(turn_id, scene_text, style_hint)`, `get_turn_illustration(turn_id)` et `truncate_assets(save_id, target_turn)`.

### C. Hooks Universe-as-Code (§11)
* **`axiom.universe:compile`** : Déclenché dans `compile_universe(src_tree, ...)` avec le dictionnaire `{"src_tree": Path, "conn": sqlite3.Connection, "universe_toml": dict}`.
* **`axiom.universe:decompile`** : Déclenché dans `decompile_universe(db_path, target_dir, ...)` avec `{"db_conn": sqlite3.Connection, "target_dir": Path}`.
* **`axiom.universe:refresh_definition`** : Déclenché dans `dev.py` lors du rechargement d'un univers édité.

### D. Allègement du Noyau
* `Session.__init__` initialise `llm` comme optionnel et interroge le registre de mods en cas d'absence.
* `Session.resolve_tick` ne contient plus d'appel en dur à `generate_scene_art`.

---

## 3. Validation

La couverture de cette étape est garantie par `tests/test_providers_illustrations_mods.py` et l'ensemble de la suite de tests modulaire (46 tests au vert) :
1. Validation des manifestes et compatibilité `.axmod`.
2. Enregistrement dynamique d'un driver custom et utilisation effective au tour.
3. Génération d'assets et rollback strict des fichiers d'illustrations au rewind.
4. Extension déclarative de `universe.toml` via les hooks de cycle de vie Universe-as-Code.
5. Tour de rôle canonique impliquant les 9 mods officiels de la plateforme sans injection explicite de LLM.
