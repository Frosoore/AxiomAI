# DOC — Règles de Myria

## Objectif
Donner à l'univers vitrine `Myria` un jeu de règles déterministes, pour que l'Arbitrator
(la fonctionnalité phare d'Axiom) ait quelque chose à arbitrer dès le 1ᵉʳ lancement.

## Comment marchent les règles (rappel moteur)
- Source : `universes/Myria/rules/<nom>.toml`, une règle par fichier. Compilé dans la table
  `Rules` (`axiom/compile.py::_parse_rules`).
- Schéma : `rule_id`, `priority` (plus petit = plus prioritaire), `target_entity` (`"*"` = toutes),
  `conditions` (groupe `operator`/`clauses`), `actions`.
- Évaluation (`axiom/arbitrator.py`, Step 8) : à chaque tour, les règles sont évaluées **pour les
  entités dont une stat a changé ce tour-là**, en chaîne (jusqu'à 5 passes ; dédup par signature
  d'action → chaque action ne se déclenche qu'une fois par tour).

## Pièges pris en compte
1. **Stat absente = `"0"`** (`stats.get(stat, "0")`). Donc une condition `<= 0` sur `"*"` se
   déclenche aussi sur les entités qui n'ont **pas** la stat (un PNJ blessé sans « Arcane Focus »
   subirait un faux burnout). → On ne déclenche les effets via des seuils **`>=` positifs**, qu'une
   stat absente (0) ne satisfait jamais. La règle de mort (`Health <= 0`) est conservée car Health
   est porté par quasiment toutes les entités concrètes (le cas des factions sans Health, jamais
   mutées en stat, est négligeable).
2. **Clé du delta** : dans Step 8, un `stat_change` lit `action.get("value")` (→ `payload["delta"]`,
   relu par l'EventSourcer). On fournit donc `value` (et `delta` en doublon, pour le chemin pur
   `RulesEngine.apply_actions` utilisé ailleurs/tests).
3. **`trigger_event` évité** : non géré proprement dans Step 8 (traité comme un `stat_set` avec
   `stat=None`). On n'utilise que `stat_change` et `set_status`.
4. **Stats émergentes non définies** (`Condition`, `Reputation`) : volontairement **pas** ajoutées
   à `stats/definitions.toml`, car `create_player_entity` initialise toute stat définie à `"10"`
   (un `Condition = "10"` n'aurait aucun sens). Elles n'apparaissent que quand une règle les pose,
   et le narrateur les voit alors dans le contexte de l'entité.

## Les règles livrées
| Fichier | Déclencheur | Effet | Prio |
|---------|-------------|-------|------|
| `mortal_collapse.toml` | `Health <= 0` | `Condition = "Mortally wounded"` | 0 |
| `marked_for_death.toml` | `Notoriety >= 90` | `Health -5` (continu tant qu'on est traqué ; chaîne vers la mort) | 20 |
| `notoriety_known.toml` | `Notoriety >= 40` | `Reputation = "Known"` | 30 |
| `notoriety_hunted.toml` | `Notoriety >= 80` | `Reputation = "Hunted"` | 40 |

Chaque règle opérationnalise la description d'une stat existante (« At 0, you are dying » ;
« draws the wrong kind of attention »). À Notoriété ≥ 80, `Known` puis `Hunted` se posent dans
l'ordre de priorité → l'état final est `Hunted`. À ≥ 90, le joueur saigne (−5/tour) et peut
basculer en `Mortally wounded` (démonstration du chaînage de règles).

## Recompilation
Le cache `.axiom-cache/` est gitignoré : il se recompile à la 1ʳᵉ charge (`ensure_compiled`
détecte le changement de hash de la source). Recompilé + vérifié localement (table `Rules` = 4).
