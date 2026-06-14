# CHANGELOG — Audit moteur, 2ᵉ passe (2026-06-14)

Suite de `audit-moteur-2026-06-14`. Cette passe corrige ce que le 1ᵉʳ audit n'avait
pas couvert. Feu vert utilisateur « fix absolument tout, aucune régression ».
Suite après corrections : **779 verts** (772 hors ambiance + 7 ambiance/Qt), 0 échec.
Découpage anti-segfault TICKET-067 conservé, `QT_QPA_PLATFORM=offscreen`. Pas de commit.

## Perf — index base de données (le vrai défaut à impact joueur)

**Constat** : 20 tables, **0 index**. SQLite n'auto-indexe que les PRIMARY KEY / UNIQUE.
Trois requêtes tournant **à chaque tour** sur des colonnes non-PK faisaient donc un
full scan d'une table qui grossit d'(au moins) une ligne par tour → coût linéaire qui
empire sur une longue partie. Prouvé par `EXPLAIN QUERY PLAN` (SCAN → SEARCH après fix) :

| Requête (par tour)                              | Table             | Avant | Après |
|-------------------------------------------------|-------------------|-------|-------|
| `get_events` : `save_id=? AND turn_id>?`        | `Event_Log`       | SCAN  | SEARCH USING INDEX |
| tick décroissance : `save_id=?`                 | `Active_Modifiers`| SCAN  | SEARCH USING INDEX |
| résolution temps : `save_id=? (AND turn_id<=?)` | `Timeline`        | SCAN  | SEARCH USING INDEX |

`State_Cache` / `Snapshots` / `Fired_Scheduled_Events` ont déjà `save_id` en tête de
PRIMARY KEY → déjà index-backed, **aucun index ajouté** (pas de churn inutile).

**Implémentation** (`axiom/schema.py`) :
- Nouvelle constante `_DDL_INDEXES` (3× `CREATE INDEX IF NOT EXISTS`), commentée.
- Exécutée dans `create_universe_db` après le DDL des tables → **toute nouvelle DB**
  (univers ET save, la save étant créée via `create_universe_db`) naît indexée.
- Nouvelle `migrate_indexes(db_path)` idempotente pour les **DB existantes** ; tolère
  une table absente (schéma legacy/partiel) — `no such table` est avalé, toute autre
  `OperationalError` remonte.

**Câblage** (`axiom/db_helpers.py`) : `migrate_indexes` ajouté aux blocs de migration
de `create_new_save` et `load_saves` (mêmes points que les autres `migrate_*`), donc
les saves d'avant le correctif se mettent à niveau au listing / à la création.

Les colonnes d'index commençant par `save_id` servent aussi d'**index enfant de FK** :
la suppression en cascade d'une `Save` ne re-scanne plus ces tables enfants non plus.

## Hygiène — `except Exception: pass` silencieux sur le chemin de jeu

Un avalage d'erreur DB sans trace masquerait une corruption. Ajout d'un
`logger.debug(..., exc_info=True)` (comportement de repli **inchangé**, on ne fait
qu'ajouter une trace dans le log fichier DEBUG) :
- `arbitrator.py` `_get_travel_distance` (repli distance 0)
- `session.py` map id→nom des entités (repli IDs bruts) + nom/persona joueur (repli défauts)
- `config.py` provisioning best-effort de la global DB
- `cli/play.py` `_resolve_player_id` (repli `player_1`)

Imports `from axiom.logger import logger` ajoutés à `session.py`, `config.py`,
`cli/play.py` (sans risque de cycle : `logger` ne dépend que de `paths`→stdlib ;
vérifié `A5-hotfix-import-circulaire`). `arbitrator.py` l'importait déjà.

**Laissés tels quels, justifiés** :
- `memory.py:57` — l'`except` protège l'**émission du warning elle-même** ; y logger
  serait circulaire.
- `backends/universal.py:135` — `exc.response.read()` best-effort, le corps lu est
  réutilisé immédiatement dans le `try` suivant.

## CI (déjà fait la passe précédente, tracé ici pour mémoire)

`.github/workflows/tests.yml` : étape de cache `~/.cache/huggingface` + pré-fetch
offline-first du modèle `all-MiniLM-L6-v2` avec retry ×5 → règle les échecs flaky
HTTP 429 (HuggingFace rate-limit sur runners partagés) qui faisaient tomber
`test_update_turn_narrative` et les autres tests à embedding réel. Une fois le cache
chaud, plus aucun appel réseau à HF. Détail dans la réponse de session + le diff.

## Tests / non-régression

- Index = perf pure : **résultats de requêtes identiques**, aucun test affecté.
- `test_schema.py` (assert `EXPECTED_TABLES`) filtre `type='table'` → les index
  (`type='index'`) ne le perturbent pas. Vérifié.
- Checks fonctionnels ad hoc : nouvelle DB → 3 index présents + `EXPLAIN` = SEARCH ;
  DB legacy (table seule) → `migrate_indexes` crée ce qui existe, saute le reste,
  idempotent au 2ᵉ passage.
- Suite complète : **772 + 7 = 779 passed, 0 échec**.

## Recheck demandé de `arbitrator.py` (1086 l.) et `prompts.py` (1038 l.)

Relecture intégrale ligne à ligne des deux gros fichiers.

### `prompts.py` — RAS
Fonctions pures d'assemblage de prompt, aucun accès DB, aucune conversion risquée
sur données LLM (les seuls `int()`/`float()`/`.format()` portent sur des valeurs
contrôlées). **Aucun défaut.**

### `arbitrator.py` — 1 bug latent corrigé : quantité d'inventaire non fiable
`_validate_inventory_change` faisait `quantity = int(change.get("quantity", 1))`
**avant** toute validation, sur du JSON LLM non fiable. Conséquences possibles :
- `int(None)` / `int("two")` / `int("2.5")` → **ValueError/TypeError non rattrapée**
  dans `process_turn` (step 7.5 hors `try`) → **le tour entier crashe** ;
- `quantity` négatif sur `add` → viol du `CHECK(quantity >= 0)` → crash en `_apply` ;
- `quantity` négatif sur `remove` → passait la validation et **ajoutait** des objets
  (`quantity - (-n)`), un « remove » devenait un add.

**Fix** : coercition défensive — `quantity` non entier → rejet propre
(« must be a whole number »), `quantity <= 0` → rejet (« must be a positive whole
number »). Un mauvais payload **rejette le changement** (→ hint de correction au
narrateur) au lieu de planter. Repli inchangé pour les cas valides ;
`quantity` absent vaut toujours 1.
+9 tests (`TestInventoryQuantityValidation` : valide, défaut=1, 5× non-entier
paramétrés, 2× non-positif). Ce chemin n'avait **aucun test** auparavant.

## Documentation Sphinx (`docs/`)
- Référence d'API : régénérée depuis les docstrings (autodoc). `arbitrator` et
  `db_helpers` sont déjà `:members:` → les docstrings mises à jour passent seules ;
  `_validate_inventory_change` est privée (exclue d'autodoc) → rien à publier.
- `schema.migrate_indexes` : `schema.py` n'est pas autodoc'd (comme les autres
  `migrate_*`) → pas de page à toucher, cohérent avec l'existant.
- **Aucune page hand-written rendue fausse** par ces changements (perf/hardening
  internes). Build `sphinx-build -W` re-vérifié (warnings = erreurs, comme la CI).

## Note (hors-scope, pas un défaut)

Quelques tests utilisent un vrai `VectorMemory` (embedding réel) plutôt que le
`_FakeEmbeddingFn` de `test_vector_memory`. Ce sont des **tests d'intégration
volontaires** qui passent ; leur flakiness CI est traitée à la source (cache HF
ci-dessus), pas en affaiblissant les tests. Mocker l'embedding dans
`test_ticket_fixes`/`test_session` serait une robustesse supplémentaire **optionnelle**,
laissée au choix utilisateur (ne rien casser > sur-ingénierie).
