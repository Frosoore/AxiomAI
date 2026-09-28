# DOC — Phase 2 : Extraction de axiom.time et axiom.inventory

## 1. Contexte & Règles d'Architecture
Cette étape poursuit l'extraction des systèmes périphériques du tour :
- **Règle D1 (Le noyau qui grossit)** : Le noyau ne connaît plus en dur ni le concept de minute diégétique, ni la gestion des arborescences de conteneurs et d'objets, ni la simulation hors-champ du Chroniqueur.
- **Règle D2 (Pas de privilège pour les mods officiels)** : `axiom.time` et `axiom.inventory` s'intègrent au pipeline de tour exclusivement via les slots officiels de `axiom.turn` (`output_fields`, `prompt_sections`) et le hook `axiom.step:after_step`.
- **Règle D7 (Rewind unifié)** : Leurs schémas de stockage déclarent explicitement les tables versionnées dans `[storage]` (`Timeline`, `Scheduled_Events`, `Inventory_Snapshots`).
- **Règle D11 (Réversibilité totale)** : Si `axiom.inventory` est désactivé ou absent, `axiom.turn` s'exécute normalement en ignorant simplement les modifications d'inventaire retournées par le modèle.

## 2. Le Mod axiom.time (`mods/axiom.time/`)
Gère le temps diégétique, le calendrier personnalisé et la simulation hors-champ :
- **Service exposé** : service `"time"` offrant `format_time`, `get_current_time` et `get_calendar`.
- **Slot souscrit** : `axiom.turn:output_fields` avec `time_elapsed_minutes` et `elapsed_minutes`.
- **Slot souscrit** : `axiom.turn:prompt_sections` avec un constructeur dynamique injectant la date/heure formatée dans le prompt système.
- **Hook souscrit** : `axiom.step:after_step` :
  - Enregistre la ligne temporelle dans `Timeline` (`ctx.write_batch.timeline_entries`).
  - Détecte les `Scheduled_Events` échus et les ajoute à `ctx.write_batch.fired_scheduled_events`.
  - Évalue le déclenchement de `ChroniclerEngine` et planifie son exécution dans `ctx.write_batch.post_commit_callbacks`.

## 3. Le Mod axiom.inventory (`mods/axiom.inventory/`)
Gère l'arborescence des objets et conteneurs :
- **Service exposé** : service `"inventory"` offrant `load_tree`, `format_prompt`, `move`, `add`.
- **Slot souscrit** : `axiom.turn:output_fields` avec `inventory_changes`. Valide les transactions d'inventaire, résout les conteneurs (`container_id`) et renseigne `ctx.write_batch.inventory_mutations`.
- **Slot souscrit** : `axiom.turn:prompt_sections` avec un constructeur dynamique injectant le résumé d'équipement du joueur.
- **Slot fourni** : `axiom.inventory:actions` (rule = collect) pour étendre les actions d'inventaire.

## 4. Allègement du Moteur
- `Session.resolve_tick` ne déclenche plus directement `ChroniclerEngine`.
- `Session._get_snapshot_data` interroge le service `"time"` fourni par le registre.
- `ArbitratorEngine` ne contient plus de traitement d'inventaire ou de timeline en dur lorsque le registre de mods est actif.
- `main_web.py` utilise les services exposés via le registre pour `/api/session/inventory` et `/api/session/time`.

## 5. Exécution des tests
```bash
.venv/bin/python -m pytest tests/test_golden_step.py tests/test_kernel_loader.py tests/test_world_turn_mods.py tests/test_time_inventory_mods.py -q
```
Toutes les suites sont 100% au vert.
