# CHANGELOG — Audit moteur & corrections (2026-06-14)

Constat dans `RAPPORT.md`. Tous les items corrigés le même jour (feu vert « corrige tout »).
Branche `dev-win-compat`. Suite : **766 verts** (705 hors vector/Qt + 61 vector/Qt), +5 tests.

## Bugs

### B1 — Lore Book enfin injecté au LLM (`axiom/arbitrator.py`)
`_fetch_relevant_lore()` réécrit : **lecture SQL directe de `Lore_Book`** (table universe-level,
colonne `keywords`) avec ranking par recouvrement mots-clés/nom vs l'input du tour, top-k, filtre
stopwords (`_LORE_STOPWORDS`, sinon le « The » des noms matchait tout). Avant : passait par
VectorMemory en filtrant sur une clé `metadata.type` que `query()` ne produit jamais **et** le lore
n'était jamais vectorisé → toujours `[]` + une requête vectorielle gaspillée/tour. Vérifié en réel
sur Myria (5 entrées pertinentes sur « aicamed », `The Aicamed Federation` en tête).
+5 tests (`TestLoreBookRetrieval`). **Suite logique → TICKET-072** : le match mots-clés ne gère
ni synonymes ni proximité de sens ; passer la récupération du lore en **recherche sémantique
(vectorielle)** serait meilleur pour la narration (retenu « ça passe pour le moment »).

### B2 — Overlay de modifiers plus jamais périmé (`axiom/arbitrator.py`)
Suppression du cache inter-tours `_stats_cache` : `_fetch_effective_stats()` relit désormais
State_Cache + Active_Modifiers **à chaque tour**. Avant, un modifier expiré (purgé par `tick`) ou
ajouté restait « cuit » dans les stats effectives jusqu'à une invalidation (Chronicler/rewind).
`invalidate_stats_cache()` conservé en no-op (compat API, appelé par `session`).
+1 test (`TestEffectiveStatsFreshness`).

### B3 — Message de rejet correct (`axiom/arbitrator.py`)
`_validate_change` : `"the player does not have enough …"` → `"{entity_id} does not have enough …"`
(était faux pour les PNJ, et ce texte part dans le hint de correction au narrateur).

## Architecture / scaling

### A1 — `_load_history()` ne charge plus tout l'Event_Log (`axiom/session.py`)
Chargement borné aux derniers `HISTORY_TURN_CAP + buffer` tours (le prompt ne garde que les 10
derniers ; l'ancien contexte est couvert par le RAG). Avant : O(tours) par tour → O(tours²) sur la
partie. Constantes `_HISTORY_LOAD_BUFFER=5`. Repli `start=-1` en début de partie.

### A2 — Snapshots périodiques (`axiom/session.py`)
`resolve_tick` prend un snapshot tous les `_SNAPSHOT_INTERVAL_TURNS=25` tours (best-effort).
`take_snapshot_async`/`SnapshotTask` côté app n'étaient **jamais appelés** → `rebuild_state_cache`
repartait toujours du tour 0. Sans effet UX : `list_checkpoints()` liste l'Event_Log, pas les
Snapshots.

### A3 — Hot path lit State_Cache sans rebuild (`axiom/session.py`)
Nouvel helper `_read_state_cache()` (lecture directe, repli rebuild si cache vide). Utilisé par la
génération d'images et la décision du héros (Companion), à la place de `current_stats()` qui faisait
un `rebuild_state_cache` complet (DELETE+replay+INSERT) à chaque appel — jusqu'à 2×/tour. La méthode
publique `current_stats()` garde sa sémantique (rebuild) pour les appelants externes.

## Micro-optimisations

- **M1** — N+1 supprimé : `_load_defined_stats()` charge le set des stats définies **1×/tour**,
  passé à `_validate_change` (avant : une connexion + requête `Stat_Definitions` par state_change).
- **M2** — `VectorMemory.query()` utilise `collection.count()` (lecture métadonnée) au lieu de
  `collection.get(where=…)` qui matérialisait tous les chunks du save juste pour les compter.
- **M3** — Lectures « contexte prompt » (noms d'entités + persona joueur) fusionnées en **une**
  connexion dans `process_turn` (au lieu de deux). Le partage plus profond entre méthodes-helper a
  été laissé (signatures hors-scope, gain horloge négligeable face au LLM).
- **M4** — Imports locaux du hot path hissés en tête d'`arbitrator.py` (`json`, `re`,
  `build_timekeeper_prompt`, `get_spatial_context`) + suppression de l'import dupliqué
  `get_connection`. **Exception** : `load_config` laissé en import local dans `process_turn` —
  les tests patchent `axiom.config.load_config`, un hoist casserait le rebind.
- **M5** — `datetime.utcnow()` (déprécié 3.12+) → `datetime.now(timezone.utc)` (`db_helpers.py`).

## Documentation (site Sphinx `docs/`)
Seules 2 inexactitudes hand-written à corriger (la référence d'API se régénère depuis les
docstrings — déjà mises à jour là où le comportement a changé : `_fetch_relevant_lore`,
`invalidate_stats_cache`, `current_stats`/`_read_state_cache`) :
- `docs/index.md` — « lore retrieval backed by a local vector store » devenait faux (B1) : le
  Lore Book est désormais récupéré **par mots-clés depuis la base** ; seul le souvenir narratif
  long terme reste vectoriel.
- `docs/guides/saves.md` — commentaire `list_checkpoints() # turns with a snapshot` **déjà faux
  avant** (la méthode liste les tours de l'Event_Log, pas les Snapshots) → « every recorded turn
  you can rewind to ». Distinction d'autant plus utile depuis A2 (snapshots ≠ checkpoints).

`docs/_build/` est gitignoré (artefact régénéré au déploiement GitHub Pages) — non modifié.

## Tests
- +5 tests (`TestLoreBookRetrieval` ×4, `TestEffectiveStatsFreshness` ×1).
- 2 tests existants ajustés en chemin **par la correction A3** (pas affaiblis) : les tests de
  décision du héros seedaient des events en comptant sur le rebuild interne de `current_stats` ; le
  repli « rebuild si State_Cache vide » de `_read_state_cache` les couvre sans modification.
- Suite : **766 passed, 0 échec** (705 + 61), même découpage que la QA Linux (segfault TICKET-067
  contourné par lots, `QT_QPA_PLATFORM=offscreen`).
