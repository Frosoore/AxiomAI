# CHANGELOG — Règles de Myria

## 2026-06-15
- Constat : `universes/Myria/` n'avait **aucune règle** (pas de `rules/`) → le moteur de règles
  déterministe (l'argument phare d'Axiom) ne faisait rien dans l'univers vitrine.

### Fait
- Créé `universes/Myria/rules/` avec **4 règles** (une par fichier) :
  - `mortal_collapse.toml` — `Health <= 0` → `Condition = "Mortally wounded"` (prio 0).
  - `marked_for_death.toml` — `Notoriety >= 90` → `Health -5` (continu ; chaîne vers la mort ; prio 20).
  - `notoriety_known.toml` — `Notoriety >= 40` → `Reputation = "Known"` (prio 30).
  - `notoriety_hunted.toml` — `Notoriety >= 80` → `Reputation = "Hunted"` (prio 40).
- **Robustesse vérifiée** (le gros piège) : une stat absente vaut `"0"` → une condition `<= 0`
  sur `"*"` se déclencherait à tort sur les entités sans la stat. Toutes les règles ciblant le
  joueur utilisent des seuils `>=` positifs (qu'un `0` ne satisfait pas) → un PNJ sans Notoriety
  n'est jamais touché par `marked_for_death`/notoriety_*. Vérifié par évaluation directe du
  `RulesEngine` (PNJ Health-only → 0 action déclenchée). La règle de mort (`Health <= 0`) est
  gardée : Health est porté par quasiment toutes les entités concrètes, et les factions (stats
  texte `Influence`/`Stance`, hors `Stat_Definitions`) ne passent pas par le chemin de mutation
  validé → edge jamais déclenché en pratique.
- Détails de sémantique respectés : `stat_change` fournit le delta sous `value` (lu par l'Arbitrator
  Step 8) **et** `delta` (chemin pur `apply_actions`) ; pas de `trigger_event` ; `Condition`/
  `Reputation` laissées émergentes (pas dans `definitions.toml`, sinon `create_player_entity` les
  initialiserait à `"10"`).
- Comportement vérifié de bout en bout via `RulesEngine` : étagement Known→Hunted à Noto≥80,
  Health−5 + Hunted à Noto≥95, Condition à HP≤0, **rien** sur un PNJ sans Notoriety.
- **Cache** : `.axiom-cache/` gitignoré → recompilé à la charge (`ensure_compiled` sur changement
  de hash). Compilé + table `Rules` = 4 vérifiée (source repo).
- **Copie installée de l'utilisateur** (`~/AxiomAI/universes/Myria/`, non écrasée par l'installateur
  bundled) : 4 règles copiées + cache purgé → recompilé, `Rules = 4`. (Les nouveaux testeurs les
  reçoivent à l'install.)
- Tests : **783 passed** (lot principal) ; `test_bundled_universes`/`test_rules_engine`/
  `test_universe_as_code`/`test_arbitrator` verts.

⚠ Rien commité — l'utilisateur gère git.
