# Audit moteur intégral — 2026-06-14

Revue qualité/optimisation du moteur `axiom/` (≈14k LoC), hot path de tour de jeu en
priorité. **Constat global : le moteur est sain et bien structuré.** Aucun des points
ci-dessous n'est une régression du portage Windows récent (branche `dev-win-compat` =
propre, cf. QA Linux). Ce sont des dettes **préexistantes**. Classés par gravité.

Rien n'a été modifié — rapport seul, en attente de feu vert.

---

## 🐞 BUGS (correction réelle)

### B1 — Le Lore Book n'arrive JAMAIS au LLM (feature morte + requête RAG gaspillée/tour)
`arbitrator._fetch_relevant_lore()` (l.793-810) renvoie **toujours `[]`**, donc
`lore_book_subset` injecté dans le prompt narratif est toujours vide. Double cause :
- `VectorMemory.query()` renvoie des dicts avec les clés `text/turn_id/chunk_type/distance/score`
  — **jamais de clé `"metadata"`**. Or le filtre fait `r.get("metadata", {}).get("type") == "lore"`
  → `{}` → `None == "lore"` → toujours faux.
- Côté embed, `embed_chunk()` n'est appelé **qu'avec `chunk_type="narrative"`** (arbitrator l.537,
  vector_worker défaut) : **aucune entrée de lore n'est jamais vectorisée**. La table `Lore_Book`
  est peuplée (compile/populate) mais jamais poussée dans le store vectoriel.

Conséquence : le « Lore Book RAG » annoncé dans le prompt ne fait rien, **et** chaque tour paie une
requête vectorielle complète (`_fetch_relevant_lore`) dont le résultat est intégralement jeté.
Le même bug de clé touche `arbitrator.py:199` / `session.py:598` (`...get("type") != "lore"`),
inoffensif là (ne garde que du narratif, ce qu'on veut), mais c'est la même incohérence
`metadata`/`chunk_type` et `type`/`chunk_type`.

**Piste :** soit retirer le Lore Book RAG (et la requête) si on ne le veut pas, soit (a) vectoriser
le lore avec `chunk_type="lore"` à la compilation/au populate, et (b) faire que `query()` expose le
`chunk_type` réellement filtrable (renommer le filtre `type`→`chunk_type`, supprimer le `metadata`
fantôme). Décision produit requise.

### B2 — Overlay de modifiers périmé via `_stats_cache`
`arbitrator._fetch_effective_stats()` met en cache les stats **effectives** (base + overlay des
`Active_Modifiers`) en fin de tour (`self._stats_cache = all_stats`, l.559) et les réutilise telles
quelles au tour suivant **sans relire `Active_Modifiers`**. Or `tick_modifiers()` (étape 9) purge les
modifiers expirés. Résultat : quand un buff/debuff **expire** (ou qu'un nouveau modifier est ajouté en
cours de partie), la valeur effective en cache garde l'ancien delta « cuit » jusqu'à la prochaine
invalidation — et `invalidate_stats_cache()` n'est appelé **qu'après un Chronicler ou un rewind**
(session.py:207/320), jamais après un tour normal. Donc un bonus temporaire peut rester actif
plusieurs tours après son expiration.

**Piste :** ne cacher que les stats **de base** et ré-appliquer l'overlay modifiers à chaque tour
(une requête, cf. `_fetch_effective_stats` déjà groupé), ou invalider le cache quand un `tick`
purge ≥1 modifier. Confiance : élevée sur l'incohérence logique, moyenne sur l'impact joueur
(dépend de l'usage réel des modifiers).

### B3 — Message de rejet codé en dur « the player »
`_validate_change()` (l.903) renvoie `"the player does not have enough {stat_key}"` pour **n'importe
quelle entité**, NPC compris. Ce texte part dans la boucle de correction (`[NARRATOR HINT…]`) → le
narrateur peut décrire « le joueur manque de X » alors que c'est un PNJ. Cosmétique mais visible.

---

## 🏛️ ARCHITECTURE / SCALING (O(N²) sur une partie longue)

### A1 — `_load_history()` recharge TOUT l'Event_Log à chaque tour
`session._load_history()` fait `get_events(start_turn_id=-1)` (tout l'historique) à chaque tour, puis
`build_narrative_prompt()` **ne garde que les 10 derniers tours** (`conversation_turns[-HISTORY_TURN_CAP:]`,
prompts.py:787). On charge et reconstruit donc N tours pour n'en utiliser que 10 → **O(N) par tour,
O(N²) sur la partie**. Le contexte ancien est déjà couvert par le RAG.
**Piste :** ne charger que `start_turn_id = turn_id - HISTORY_TURN_CAP - marge`. Appelé aussi par la
décision du héros (Companion) → double gain.

### A2 — Aucun snapshot par tour → `rebuild_state_cache` rejoue depuis le tour 0
`workers/db_worker.take_snapshot_async()` (et `SnapshotTask`) existe mais **n'est appelé nulle part**.
Les seuls snapshots créés sont au tour 0 (création de save) et au fork. Donc en jeu,
`EventSourcer.rebuild_state_cache()` repart **toujours du tour 0** = replay complet de l'historique.
Couplé à A3, chaque tour avec images (et/ou Companion) fait 1 à 2 replays complets → **O(N²)**.
**Piste :** câbler un snapshot périodique (toutes les ~25-50 min in-game ou N tours — le task existe
déjà), ce qui borne aussi le coût des rewinds.

### A3 — `current_stats()` reconstruit le cache à chaque appel (souvent inutilement)
`session.current_stats()` fait `rebuild_state_cache()` (DELETE + replay + INSERT massif) **à chaque
appel**, alors que `EventSourcer.update_state_cache()` maintient déjà le `State_Cache` à jour de façon
incrémentale après chaque tour (TICKET-002). Appelée par la génération d'images (chaque tour si activée)
et par `_get_hero_decision` (Companion) → travail O(historique) redondant sur le hot path.
**Piste :** en jeu normal, lire directement `State_Cache` (déjà frais) au lieu de rebuild ; réserver
`rebuild` aux cas de réconciliation (post-Chronicler/rewind, déjà gérés). Bonus : l'image-gen pourrait
réutiliser le snapshot stats déjà en mémoire dans l'arbitrator.

---

## ⚡ MICRO-OPTIMISATIONS

### M1 — N+1 sur `Stat_Definitions` dans `_validate_change`
Une connexion + requête `SELECT 1 FROM Stat_Definitions WHERE LOWER(name)=?` est ouverte **par
state_change** (arbitrator l.862-869). Charger une fois par tour le set des noms de stats définis
(ils ne changent pas en cours de partie) et valider en mémoire.

### M2 — `VectorMemory.query()` matérialise TOUS les chunks du save juste pour les compter
`query()` (memory.py:210) fait `self._collection.get(where=where_cond)` — qui charge documents+metadatas
de **tous** les chunks du save — uniquement pour calculer `available` et clamper `fetch_k`. Sur une
partie longue (milliers de chunks), 2-3× par tour. Chroma clampe déjà `n_results > available` ;
sinon passer `include=[]` pour ne ramener que les ids.

### M3 — Multiples `get_connection()` par tour (~10-15)
`process_turn` ouvre/ferme une connexion par lecture (stats, noms, persona, temps, spatial, events
programmés, timeline, +N pour la validation). Avec `_ClosingConnection`, chaque ouverture rejoue les
PRAGMA WAL. Plusieurs lectures pourraient partager une connexion. Impact horloge faible (le LLM domine)
mais hygiène facile.

### M4 — Imports locaux répétés sur le hot path
`process_turn`/`resolve_tick` ré-importent à chaque tour : `from axiom.config import load_config`,
`from axiom.db_helpers import get_connection` (redondant — déjà importé en tête depuis `axiom.schema`),
`import re, json`, `build_timekeeper_prompt`, `get_spatial_context`… Cache `sys.modules` donc quasi
gratuit, mais à hisser en tête de module pour la lisibilité.

### M5 — `datetime.utcnow()` déprécié (Python 3.12+)
`db_helpers.py:155` (et signalé par les warnings de la suite). Remplacer par
`datetime.now(datetime.UTC)`.

---

## Ce qui est BON (pour cadrer)
- Event sourcing propre, `update_state_cache` incrémental, batch d'events en une transaction.
- `_fetch_effective_stats` déjà groupé (2 requêtes globales au lieu de N round-trips).
- Filtrage d'entités pertinentes pour économiser des tokens, stop-sequences anti-impersonation.
- `parse_tool_call` résilient (fences + fallback heuristique), dégradation gracieuse VectorMemory.
- Portage Windows récent : sûr, no-op sous POSIX (cf. QA Linux du jour).
