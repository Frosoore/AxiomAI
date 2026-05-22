# Axiom AI — Upgrade Details

> Document de référence détaillant l'ensemble des modifications, corrections,
> refactorings et nouvelles directions architecturales du projet Axiom AI.
>
> **Version du document :** 1.0
> **Statut :** Spécification — à exécuter par phases.
> **Audience :** dev principal du projet + futurs contributeurs.

---

## Préambule

### Pourquoi ce document existe

Axiom AI est un projet ambitieux : un moteur de RPG sandbox local, déterministe,
piloté par LLM, avec event sourcing, arbitrage des actions, simulation du monde
hors-écran, rewind temporel, mémoire vectorielle, et un éditeur d'univers complet.
La base technique (~23 900 lignes Python, 320+ tests) est saine. Mais elle souffre
de :

- **Bugs latents** qui crashent à des moments précis (Chronicler trigger, rewind…).
- **Couplage UI/moteur** qui empêche tout usage hors PySide6.
- **UI sans personnalité** qui ne reflète pas la nature narrative du produit.
- **Dépendances lourdes** (torch + chromadb) qui plombent l'expérience d'install.
- **Manque de moddabilité** structurelle (univers en blob binaire, pas de plugins).
- **Pas de système de test pour les univers** créés par la communauté.

Ce document est le plan complet pour adresser tout ça **par phases successives**,
avec priorité claire et descriptions techniques exploitables directement.

### Conventions

- **Pilier** : changement architectural majeur. Numérotés P1 à P7.
- **Phase** : regroupement temporel de plusieurs items. A → D.
- Les **références de code** sont notées `chemin/fichier.py:ligne`.
- Les blocs marqués **⚠ Bloquant** sont des bugs qui produisent un crash garanti.
- Les blocs **🎯 Quick win** sont des changements <1 jour à fort ROI.
- Les blocs **🏗 Chantier** sont des refontes >1 semaine.

### État de la codebase à date

```
Source (Python)       : 23 903 lignes
Tests                 :  4 584 lignes
Langues localisation  : 10 (en, fr, es, de, it, pt, ru, zh, ja, ko)
Tables SQLite         : 19
Workers QThread       : 11
Onglets Creator Studio:  9
Backends LLM          :  3 (universal OpenAI-compat, gemini, ollama-legacy)
```

---

# PARTIE I — STABILISATION (Phase A)

Avant d'ajouter de la complexité, on assainit. Cette phase ne change AUCUNE
fonctionnalité visible — elle élimine les bugs et nettoie. **Durée estimée :
1 semaine.**

## 1. Bugs bloquants à corriger en priorité

### 1.1 ⚠ `ChroniclerEngine` instancié avec un seul argument

**Fichier :** `ui/tabletop_view.py:612`
**Symptôme :** Crash garanti dès qu'on franchit le seuil `chronicler_interval`
(50 turns par défaut).

```python
# Actuel (cassé)
self._chronicler = ChroniclerEngine(self._db_path)
```

Mais la signature exige `llm, event_sourcer, db_path, trigger_interval`
(`core/chronicler.py:73-79`).

**Fix :**
```python
from database.event_sourcing import EventSourcer
cfg = load_config()
self._chronicler = ChroniclerEngine(
    llm=self._llm,
    event_sourcer=EventSourcer(self._db_path),
    db_path=self._db_path,
    trigger_interval=cfg.chronicler_interval,
)
```

**Tests à ajouter :** un test d'intégration qui force `_last_chronicle_turn = 0`
puis envoie 50 turns et vérifie qu'aucune exception ne remonte.

### 1.2 ⚠ Méthode `rewind_to_checkpoint` inexistante

**Fichier :** `ui/tabletop_view.py:728`
**Symptôme :** AttributeError au moindre clic sur "Rewind" / Ctrl+Z.

```python
# Actuel (cassé)
self._db_worker.rewind_to_checkpoint(self._save_id, target_id)
```

La méthode réelle dans `workers/db_worker.py:131` s'appelle `execute_rewind`.

**Fix :** renommer l'appel en `execute_rewind`, OU exposer un alias
`rewind_to_checkpoint` dans `DbWorker` qui délègue vers `execute_rewind`.

**Recommandation :** renommer l'appel côté UI. Le nom `execute_rewind` est plus
explicite et matche le pattern des autres méthodes (`execute_*`).

### 1.3 ⚠ Suppression aveugle d'un widget au statusbar

**Fichier :** `ui/main_window.py:320`
**Symptôme :** quand l'utilisateur ferme Settings, un widget aléatoire du
statusbar est supprimé. Bug subtil parfois invisible, parfois cassant le slider
volume.

```python
# Actuel
self._status_bar.removeWidget(self._status_bar.findChild(QWidget))  # Hacky, but works
```

**Fix :** mémoriser explicitement les références aux widgets ajoutés au statusbar
dans `_setup_volume_slider`, et supprimer seulement ceux qu'on a ajoutés.

```python
# Cible
def _setup_volume_slider(self) -> None:
    if hasattr(self, "_volume_container"):
        self._status_bar.removeWidget(self._volume_container)
        self._volume_container.deleteLater()
    # ... rest
```

(Une partie du fix est déjà là mais `_show_settings` court-circuite la logique.)

### 1.4 ⚠ `tick_modifiers` ticke 1 minute fixe

**Fichier :** `core/arbitrator.py:412`
**Symptôme :** les modifiers (buffs/debuffs) n'expirent jamais correctement,
quel que soit le temps in-game réellement écoulé.

```python
# Actuel
self._modifier_processor.tick_modifiers(save_id)  # default = 1 minute
```

Mais le temps in-game avance souvent de 15+ minutes par tour, parfois beaucoup
plus si l'action est un voyage.

**Fix lié au Pilier 5** (temps causal) : passer le `elapsed_minutes` réel du
tour. Cf. section 6.

### 1.5 ⚠ `TimekeeperWorker` importé jamais instancié

**Fichier :** `ui/tabletop_view.py:45` (import) + `:524` (hardcode).

```python
# Import présent mais inutilisé
from workers.timekeeper_worker import TimekeeperWorker

# Plus loin, dans _on_send_message :
self._current_time += 15  # hardcoded
```

Le `TimekeeperWorker` est conçu pour analyser le narratif via LLM et estimer
le temps écoulé. C'est du code complet, fonctionnel, mais branché à rien.

**Fix lié au Pilier 5.**

### 1.6 ⚠ Race condition sur les Entity_Stats en `save_full_universe`

**Fichier :** `workers/db_worker.py:315-323`

```python
conn.execute("DELETE FROM Entity_Stats;")
conn.execute("DELETE FROM Entities;")
for e in entities:
    conn.execute("INSERT INTO Entities ...")
    for sk, sv in e.get("stats", {}).items():
        conn.execute("INSERT INTO Entity_Stats ...")
```

Avec FK + ON DELETE CASCADE, `DELETE FROM Entities` cascade déjà sur
`Entity_Stats`. Le `DELETE FROM Entity_Stats` séparé en premier est inutile et
potentiellement bug-prone si les FKs sont temporairement off.

**Fix :** supprimer la ligne `DELETE FROM Entity_Stats`. Laisser la cascade
faire son job.

**Risque associé connexe :** un renommage d'entity_id côté Creator Studio
**perd silencieusement** tous les events de `Event_Log` qui référencent l'ancien
ID (puisque `Event_Log.target_entity` n'a pas de FK). À documenter dans le
schéma : `entity_id` est immuable une fois créé. Idéalement, ajouter une UI
"Rename" qui appelle un UPDATE explicite sur Event_Log.

### 1.7 ⚠ `get_translations_dict()` n'existe pas

**Fichier :** `debug/test_translations.py:14` importe `get_translations_dict`
depuis `core.localization` — mais cette fonction n'existe pas dans le fichier
réel (vérifié, le fichier finit à `tr()`).

**Fix :** ajouter dans `core/localization.py` :

```python
def get_translations_dict() -> dict:
    """Expose the internal translations dictionary (debug/testing only)."""
    return _TRANSLATIONS
```

### 1.8 ⚠ `CreatePlayerEntityTask` dupliquée

**Fichier :** `workers/db_tasks.py:751-833`

La classe est définie deux fois consécutivement. La seconde écrase la première,
mais c'est du bruit visuel et un piège pour un mainteneur.

**Fix :** supprimer la seconde définition (lignes 793-833).

### 1.9 ⚠ `MapEditor` affiche "m" mais stocke "km"

**Fichier :** `ui/widgets/map_editor.py:98, 118`

```python
self.text_item = QGraphicsTextItem(f"{distance}m")
self.text_item.setPlainText(f"{distance}m")
```

Le schéma stocke `distance_km` (et le Phase 18 du Changelog l'explicite).
L'affichage est faux d'un facteur 1000.

**Fix :** remplacer `f"{distance}m"` par `f"{distance} km"`.

### 1.10 ⚠ Tests dans `debug/` jamais exécutés par pytest

`debug/test_db_logic.py`, `debug/test_audio_logic.py`, `debug/test_llm_logic.py`,
`debug/test_populate_async.py` sont des `unittest.TestCase` qui :

1. Ne sont pas dans `tests/` donc pytest ne les ramasse pas
2. Utilisent `unittest.main()` au lieu de fixtures pytest
3. Polluent `debug/` qui contient aussi de vrais scripts utilitaires

**Fix :** soit les déplacer vers `tests/` et les convertir, soit les supprimer
s'ils dupliquent des tests existants. Audit nécessaire un par un.

## 2. Bugs logiques (pas crash mais comportement incorrect)

### 2.1 Déduplication O(N²) dans le RulesEngine chaining

**Fichier :** `core/arbitrator.py:357-368`

```python
for action in triggered_actions:
    action_id = f"{entity_id}_{action.get('type')}_{action.get('stat')}_{action.get('value')}"
    if any(f"{entity_id}_{a.get('type')}_{a.get('stat')}_{a.get('value')}" == action_id
           for a in triggered_rules):
         continue
```

Recompose la signature à chaque comparaison. Sur des chaînes de rules avec 5
itérations × 20 entités × 5 actions, ça scale mal.

**Fix :** maintenir un `set[str]` de signatures vues, lookup en O(1).

```python
_seen_signatures: set[str] = set()
for action in triggered_actions:
    action_id = f"{entity_id}_{action.get('type')}_{action.get('stat')}_{action.get('value')}"
    if action_id in _seen_signatures:
        continue
    _seen_signatures.add(action_id)
    # ... process action
```

### 2.2 Disconnect-then-reconnect du signal `rewind_complete`

**Fichier :** `ui/tabletop_view.py:729, 734`

À chaque rewind, le slot `_on_rewind_done` est connecté **puis déconnecté**
dans son propre exécution. Pattern fragile si l'utilisateur lance plusieurs
rewinds rapprochés.

**Fix :** connecter le signal une fois pour toutes au setup, et utiliser un
flag d'état `_rewind_in_progress` pour ignorer les exécutions redondantes.

### 2.3 Compatibilité `Signal(dict)` mais slot `@Slot()` sans param

**Fichier :** `workers/db_worker.py:46`, branché à `ui/tabletop_view.py:729`.

```python
rewind_complete = Signal(dict)
# ...
self._db_worker.rewind_complete.connect(self._on_rewind_done)
# où _on_rewind_done est @Slot() sans dict
```

Marche par tolérance Qt (les args supplémentaires sont droppés), mais c'est sale.

**Fix :** typer le slot proprement : `@Slot(dict) def _on_rewind_done(self, summary: dict)`.

## 3. Optimisations chirurgicales (perf immediate)

### 3.1 🎯 N+1 connexions SQLite dans `_fetch_effective_stats`

**Fichier :** `core/arbitrator.py:519-532` + `database/event_sourcing.py:259` +
`database/modifier_processor.py:203`.

Aujourd'hui, pour 20 entités, on ouvre 40+ connexions par tour :
- 1 pour lister les entity_ids
- 1 par entité pour `get_current_stats` (ouverture conn + SELECT)
- 1 par entité pour `apply_modifiers._fetch_modifiers` (ouverture conn + SELECT)

**Fix :** une seule connexion partagée + deux requêtes globales.

```python
def _fetch_effective_stats(self, save_id: str) -> dict[str, dict[str, str]]:
    with get_connection(self._db_path) as conn:
        # 1 requête pour TOUTES les stats
        rows = conn.execute("""
            SELECT entity_id, stat_key, stat_value
            FROM State_Cache
            WHERE save_id = ?;
        """, (save_id,)).fetchall()

        base: dict[str, dict[str, str]] = {}
        for r in rows:
            base.setdefault(r["entity_id"], {})[r["stat_key"]] = r["stat_value"]

        # 1 requête pour TOUS les modifiers actifs
        mod_rows = conn.execute("""
            SELECT entity_id, stat_key, delta
            FROM Active_Modifiers
            WHERE entity_id IN (SELECT DISTINCT entity_id FROM State_Cache WHERE save_id = ?);
        """, (save_id,)).fetchall()

    # Overlay en mémoire (pas de DB)
    effective = {eid: dict(stats) for eid, stats in base.items()}
    for r in mod_rows:
        if r["entity_id"] in effective:
            current_raw = effective[r["entity_id"]].get(r["stat_key"], "0")
            try:
                current = float(current_raw)
                effective[r["entity_id"]][r["stat_key"]] = fmt_num(current + r["delta"])
            except ValueError:
                pass  # non-numeric stat
    return effective
```

**Gain estimé :** 40 ouvertures de connexion → 1. Sur SQLite WAL, chaque
ouverture coûte ~100 µs + le PRAGMA setup. Économie réelle ~4 ms par tour,
peut-être 10× plus sur disk lent. Plus crucial : moins de contention WAL.

### 3.2 🎯 Batch des `append_event` dans une transaction unique par tour

**Fichier :** `database/event_sourcing.py:67-78`

Chaque `append_event` ouvre conn + INSERT + commit. Un tour Arbitrator émet
typiquement 5-10 events (user_input, state_changes ×N, rule_triggers ×M,
narrative_text, hero_intent). Donc 5-10 fsync WAL par tour.

**Fix :** ajouter une API `append_events_batch` qui prend une liste et fait
une seule transaction. Mettre à jour `Arbitrator.process_turn` pour collecter
tous les events en mémoire puis appeler le batch à la fin (sauf le user_input
initial qui peut rester séparé pour logging immédiat).

```python
def append_events_batch(self, events: list[tuple]) -> list[int]:
    """events: list of (save_id, turn_id, event_type, target, payload) tuples."""
    rows = [(s, t, e, tg, json.dumps(p)) for s, t, e, tg, p in events]
    with get_connection(self._db_path) as conn:
        cursor = conn.executemany(
            "INSERT INTO Event_Log (save_id, turn_id, event_type, target_entity, payload) "
            "VALUES (?, ?, ?, ?, ?);",
            rows,
        )
        conn.commit()
    # Note: lastrowid après executemany n'est pas portable. Si on a besoin des
    # event_ids retour, faire un SELECT MAX(event_id) avant + after, ou append
    # un par un dans une transaction commune.
```

### 3.3 🎯 `WorldState` cache mémoire invalidé par dernier event_id

Aujourd'hui chaque refresh de la sidebar Tabletop fait un SELECT complet sur
`State_Cache`. Sur un univers avec 50 entités et 200 stats, c'est ~250 lignes
relues à chaque turn.

**Fix :** maintenir un cache mémoire dans `Arbitrator` (ou dans une classe
`WorldState`) qui :
- Est seedé au début de session par un SELECT initial
- Est mis à jour incrémentalement à chaque event appliqué
- Est invalidé proprement sur rewind

Pour la concurrence : tag le cache avec `last_event_id` ; si à la lecture
suivante le `MAX(event_id)` SQL est plus grand, on refait un load complet.

**Gain :** lecture stats côté UI passe de "I/O SQLite" à "dict lookup". Sidebar
plus réactive, surtout avec stats fréquemment refreshées (toutes les 1-2 sec
en cours de turn).

### 3.4 🎯 `print()` → `logger`

**17 occurrences identifiées** dans :
- `core/arbitrator.py:195, 609, 622`
- `core/chronicler.py:238`
- `workers/db_helpers.py:326, 378`
- `workers/db_tasks.py:43, 261, 684`
- `workers/timekeeper_worker.py:84`
- `database/schema.py:481, 484, 536, 539`

Solution déjà disponible : `from core.logger import logger`.

**Fix mécanique :**
- `print(f"[X] ...")` → `logger.debug(f"...")` ou `logger.error(...)` selon la
  nature (erreur dans except → error, info de debug → debug).
- Le file handler du logger (`~/.cache/AxiomAI/axiom_ai.log`) capte tout en
  DEBUG, la console reste en INFO.

### 3.5 🎯 Cache du `pip install` dans `run.sh`

**Fichier :** `run.sh:88-89`

Actuellement, `pip install -r requirements.txt` tourne **à chaque lancement**.
Sur un système où torch+chromadb+sentence-transformers sont déjà installés,
le `pip install` prend quand même 3-5 secondes pour vérifier.

**Fix :** marker file basé sur le hash de `requirements.txt`.

```bash
REQ_HASH=$(sha256sum requirements.txt | cut -d' ' -f1)
MARKER="$VENV_DIR/.deps_hash"

if [ ! -f "$MARKER" ] || [ "$(cat "$MARKER")" != "$REQ_HASH" ]; then
    echo "Installing/updating dependencies..."
    python3 -m pip install --upgrade pip
    python3 -m pip install -r requirements.txt
    echo "$REQ_HASH" > "$MARKER"
else
    echo "Dependencies up to date (skip)."
fi
```

**Gain :** ~3 secondes au lancement quand rien n'a changé. Pour l'utilisateur
qui lance l'app 10× par jour : ~30 sec/jour récupérées.

### 3.6 🎯 Pré-chargement de `sentence_transformers` au démarrage

**Fichier :** `debug/startup_check.py:64`

```python
core_modules = [
    # ...
    ('sentence_transformers', 'sentence-transformers'),
    # ...
]
```

Ce check importe sentence_transformers (qui charge torch en chaîne, ~500 MB
en mémoire) **avant que la fenêtre n'apparaisse**. C'est probablement la
principale cause perçue de "lenteur au démarrage".

**Fix :** retirer `sentence_transformers` (et `chromadb`) de la liste de
modules verifiés au startup_check. Le check actuel se contente d'un
`__import__`, ce qui suffit à charger torch. Le check est plus utile sous
forme d'un "Settings → Diagnostics" lancé à la demande.

Alternative : retarder le check par un `QTimer.singleShot(2000, run_checks)`
après que la fenêtre soit visible.

## 4. Nettoyage code mort

| Fichier | Action |
|---|---|
| `workers/db_tasks.py:793-833` | Supprimer définition dupliquée de `CreatePlayerEntityTask` |
| `ui/tabletop_view.py:45` | Retirer import `TimekeeperWorker` (réintégré au Pilier 5) |
| `debug/test_db_logic.py` | Évaluer : merge dans `tests/test_schema.py` ou supprimer |
| `debug/test_audio_logic.py` | Évaluer : merge dans `tests/test_ambiance_manager.py` |
| `debug/test_llm_logic.py` | Évaluer : doublon avec `tests/test_llm_base.py` ? |
| `debug/test_populate_async.py` | Idem |
| Commentaires `# Hacky, but works` | Identifier et corriger ou retirer |

---

# PARTIE II — ARCHITECTURE (Phase B)

Une fois la base saine, on attaque les changements structurels. **Durée
estimée : 6 à 8 semaines.**

## 5. Pilier 1 — Extraction `axiom-engine` headless 🏗

### 5.1 Constat

Aujourd'hui, le moteur (Arbitrator, Chronicler, EventSourcing, RulesEngine,
ModifierProcessor, VectorMemory, prompt building) est mélangé avec PySide6 :
- Les workers vivent dans `workers/` et importent Qt
- `core/paths.py` utilise des paths Qt-friendly
- Le tabletop_view orchestre la logique de turn directement

Conséquences :
- Impossible de jouer en CLI / scripted
- Impossible de tester l'engine sans `QApplication()` (cf. `tests/conftest.py`)
- Impossible d'embarquer Axiom dans un autre projet
- Difficulté à reasonner clairement sur la frontière "engine vs UI"

### 5.2 Cible

Séparer le repo en **deux packages distincts** :

```
axiom-engine/                 ← pip-installable, ZERO Qt dependency
  axiom/
    __init__.py
    universe.py               ← Universe class (load .axiom, list saves)
    session.py                ← Session class (turn loop, state holder)
    arbitrator.py             ← (depuis core/arbitrator.py)
    chronicler.py             ← (depuis core/chronicler.py)
    rules.py                  ← (depuis core/rules_engine.py)
    events.py                 ← (depuis database/event_sourcing.py)
    checkpoint.py             ← (depuis database/checkpoint.py)
    modifiers.py              ← (depuis database/modifier_processor.py)
    schema.py                 ← (depuis database/schema.py)
    memory.py                 ← VectorMemory abstracted (Protocol)
    time_system.py            ← (depuis core/time_system.py)
    config.py                 ← AppConfig minimal (sans GUI fields)
    backends/
      __init__.py             ← @register_backend
      base.py                 ← LLMBackend Protocol
      universal.py
      gemini.py
    prompts/                  ← (depuis llm_engine/prompt_builder.py, split)
      narrative.py
      chronicler.py
      mini_dico.py
      populate.py
    cli/
      __init__.py
      play.py                 ← `axiom play universe.axiom`
      compile.py              ← `axiom compile src_dir → .axiom`
      test_runner.py          ← `axiom test scenarios/*.yaml`
  pyproject.toml
  README.md

axiom-app/                    ← Le projet actuel, réduit à l'UI
  ui/
  workers/
  assets/
  main.py
  pyproject.toml              ← dépend de axiom-engine
```

### 5.3 Plan de migration

**Étape 1.** Ajouter un package `axiom/` au sein du repo actuel. Y copier
(d'abord) puis déplacer (après tests verts) les modules engine.

**Étape 2.** Remplacer tous les imports dans `ui/` et `workers/` :
- `from core.arbitrator import ...` → `from axiom.arbitrator import ...`
- `from database.schema import ...` → `from axiom.schema import ...`
- etc.

**Étape 3.** Identifier les fuites Qt dans le code engine :
- `core/paths.py` doit devenir abstrait. L'engine reçoit un `data_dir: Path`
  en paramètre, l'app le résout via Qt.
- `core/config.py` : split en deux. `EngineConfig` (backends, LLM params) reste
  dans `axiom/`. `AppConfig` (font_size, enable_audio, language) reste côté
  app.

**Étape 4.** Définir l'API publique de `axiom-engine` :

```python
# axiom/session.py
class Session:
    """High-level wrapper that an app uses to run a game."""

    def __init__(self, universe_path: str, save_id: str, llm: LLMBackend,
                 vector_memory: VectorMemory, data_dir: Path):
        self.universe = Universe.load(universe_path)
        self.save_id = save_id
        self._arbitrator = ArbitratorEngine(...)
        self._chronicler = ChroniclerEngine(...)
        # ...

    def take_turn(self, player_input: str, *,
                  player_id: str = "player",
                  on_token: Callable[[str], None] | None = None,
                  ) -> ArbitratorResult:
        """Execute one turn. Synchronous. Stream tokens via callback."""
        # ...

    def rewind(self, target_turn: int) -> RewindSummary:
        # ...

    def list_checkpoints(self) -> list[int]:
        # ...

    def current_stats(self) -> dict[str, dict[str, str]]:
        # ...

    @property
    def turn_id(self) -> int:
        # ...
```

L'app construit une `Session` au démarrage de tabletop, et appelle
`session.take_turn()` depuis un QThread worker (le worker actuel `NarrativeWorker`
devient un simple wrapper de threading + signal/slot autour de la `Session`).

### 5.4 Ce que ça débloque

1. **Mode CLI** : `axiom play universes/my_world.axiom`. Text adventure dans
   le terminal. Utile pour :
   - Joueurs minimalistes / SSH
   - Tests intégration
   - Démos sans GUI
   - Modders qui veulent itérer sans relancer Qt

2. **Tests 10× plus rapides** : pas de `QApplication`, les tests engine se
   lancent en parallèle.

3. **Frontend alternatif** : quelqu'un peut bâtir une UI web qui parle à un
   serveur HTTP wrappant l'engine. Local-first préservé (serveur localhost).

4. **Modding programmatique** : `import axiom` dans un Jupyter notebook pour
   explorer un univers, générer du contenu par script.

5. **Distribution** : `pip install axiom-engine` rend l'engine accessible à
   d'autres projets (mods, outils communautaires).

### 5.5 Coût estimé

~2 semaines de refactoring + adaptation des tests. Risque bas si on procède
par étapes (copy avant move, tests à chaque étape).

---

## 6. Pilier 5 — Le Temps comme substrat causal 🏗

### 6.1 Constat

Le code actuel contient **tous les ingrédients d'un système temporel cohérent**,
mais ils sont déconnectés :

- `core/time_system.py` : `TimeSystem` + `CalendarConfig` (calendrier custom)
- `workers/timekeeper_worker.py` : analyse LLM du temps écoulé — **mort**
- `database/schema.py` : table `Timeline` (turn_id, in_game_time, description)
- `database/schema.py` : table `Scheduled_Events` (trigger_minute)
- `core/chronicler.py:89-105` : `should_trigger(current_time, last_chronicle_time)`
  basé sur des minutes — mais appelé via `turn_id` dans `tabletop_view.py:609`
- `core/arbitrator.py:412` : `tick_modifiers(save_id)` qui ticke 1 minute par défaut
- `ui/tabletop_view.py:524` : `self._current_time += 15` hardcoded

C'est un **système temporel à moitié réalisé**. Le Pilier 5 le finit.

### 6.2 Cible

Le **LLM** est responsable de déclarer le temps écoulé pendant son tour, via
une extension du schéma tool_call.

```json
{
  "state_changes": [...],
  "inventory_changes": [...],
  "elapsed_minutes": 45,
  "scene_pace": "deliberate",
  "game_state_tag": "exploration"
}
```

`scene_pace` est purement descriptif (combat | conversation | travel |
deliberate | montage), utilisable par d'autres systèmes (audio, image gen)
sans impact direct sur le temps.

### 6.3 Plan d'implémentation

**Étape 1.** Étendre `NARRATIVE_TOOL_CALL_SCHEMA` dans `prompt_builder.py` pour
inclure `elapsed_minutes` (integer, default 1) et `scene_pace`.

**Étape 2.** Côté Arbitrator (`core/arbitrator.py`), parser ces champs et les
retourner dans `ArbitratorResult` (nouveau champ `elapsed_minutes: int`).

**Étape 3.** Côté `NarrativeWorker` / `tabletop_view._on_turn_complete` :
remplacer `self._current_time += 15` par
`self._current_time += result.elapsed_minutes`.

**Étape 4.** `tick_modifiers(save_id, elapsed_minutes=result.elapsed_minutes)`
au lieu de tick fixe.

**Étape 5.** Chronicler trigger basé sur le temps :
```python
# Avant (turns)
if (self._turn_id - self._main_window._last_chronicle_turn) >= cfg.chronicler_interval:

# Après (minutes)
if self._chronicler.should_trigger(self._current_time, self._last_chronicle_time):
    self._last_chronicle_time = self._current_time
    # ...
```

(Le `should_trigger` existe déjà, il suffit de l'utiliser.)

**Étape 6.** `Scheduled_Events` se déclenchent quand `current_time >= trigger_minute`.
Déjà géré dans `arbitrator._fetch_triggered_events`.

**Étape 7.** Réactiver `TimekeeperWorker` comme **fallback** quand le LLM ne
renvoie pas `elapsed_minutes` :
- L'Arbitrator détecte `elapsed_minutes is None` dans le tool_call
- Lance `TimekeeperWorker` qui re-prompte le LLM sur le narrative_text seul
  pour extraire le temps écoulé
- Si toujours rien : default à `scene_pace_defaults[pace]` (combat = 2 min,
  travel = 60 min, etc.)

### 6.4 Edge cases

- **Voyage explicite** : si le LLM applique `state_change` sur `Location` du
  player, et qu'il existe une `Location_Connections.distance_km` entre source
  et destination, on peut **valider** que `elapsed_minutes` est cohérent avec
  la distance (avec une fenêtre large). Si l'écart est de 100×, queue une
  correction.
- **Time skip narratif** : si `elapsed_minutes > 480` (8h), trigger le
  Chronicler **avant** de retourner le résultat, pour que le monde évolue
  pendant le voyage.
- **Conversion calendar** : tout passage par `TimeSystem.get_time_string()`
  utilise le calendar custom de l'univers. Les `Scheduled_Events` qui
  réfèrent à des dates absolues du calendar doivent rester corrects après
  changement de calendar params.

### 6.5 Ce que ça débloque

- **Vraie cohérence narrative** : un voyage prend une journée, pas 15 min
- **Buffs/debuffs justes** : "Empoisonné 30 min" expire après 30 min, pas après
  30 turns
- **Chronicler activé sur les bons rythmes** : un long voyage déclenche
  plusieurs World Turns successifs, simulant l'évolution du monde
- **Scheduled events fiables** : "Le festival commence Jour 7, 10h00" se
  déclenche pile au bon moment
- **Topbar affichage cohérent** : "Day 3, Aries 7, 14:32 (Afternoon)" devient
  une info crédible

### 6.6 Coût

3 à 5 jours. C'est principalement de la rigueur et du câblage. Le code dormant
existe déjà.

---

## 7. Pilier 2 — Universe-as-Code 🏗

### 7.1 Constat

Un univers Axiom AI est aujourd'hui un blob binaire `.db` (SQLite). Ce format :
- Est **opaque** : impossible à inspecter sans l'app
- N'est **pas diffable** : git voit "fichier binaire modifié"
- N'est **pas mergeable** : pas de collaboration entre créateurs
- N'est **pas éditable hors-app** : tout passe par le Creator Studio
- N'est **pas reviewable** : pas de PR possible

Or, **un univers est essentiellement une définition de contenu** (entités,
règles, lore, locations) — donc fondamentalement du texte structuré. La forme
SQLite ne devrait être qu'**un cache compilé** pour la performance runtime.

### 7.2 Cible

Définition d'univers en **arborescence de fichiers texte versionnable**.

```
my_universe/                          ← directory, git-friendly
  universe.toml                       ← metadata: name, lore, system_prompt, calendar
  README.md                           ← description for humans / GitHub
  CHANGELOG.md                        ← versioning by the author
  LICENSE
  cover.png                           ← optional thumbnail

  stats/
    definitions.toml                  ← Stat_Definitions

  entities/
    player_hero.toml
    bob_blacksmith.toml
    iron_brotherhood.toml             ← entity_type = faction
    _index.toml                       ← optional manifest

  rules/
    death.toml
    combat_critical.toml
    poisoning.toml

  locations/
    map.toml                          ← hierarchy + connections

  lore/
    history.md                        ← Markdown for rich content
    factions/red_guard.md
    magic_system.md
    glossary.md

  events/
    festival_of_lights.toml
    war_declaration.toml

  setup/
    questions.toml                    ← Story_Setup (initialization questions)

  items/
    sword_excalibur.toml
    potion_healing.toml

  assets/                             ← optional, bundled with .axiom
    portraits/
      bob.png
    audio/
      tavern/
        celtic_jig.mp3

  plugins.toml                        ← required & optional plugin dependencies
  .axiom-cache/                       ← gitignored, compiled .db
    universe.db
    cache_hash.txt
```

### 7.3 Format des fichiers

#### `universe.toml`
```toml
[meta]
name = "Drakthar"
version = "1.2.0"
author = "Garen"
license = "CC-BY-SA-4.0"
engine_version = ">=0.5.0,<2.0.0"

[narrative]
system_prompt = """
You are the narrator of Drakthar, a dark fantasy world.
The tone is grim, the magic dangerous, the gods absent.
"""
global_lore_file = "lore/history.md"     # multi-line content in dedicated file
first_message_file = "lore/intro.md"
world_tension_level = 0.4

[llm_defaults]
temperature = 0.7
top_p = 1.0
verbosity = "balanced"

[calendar]
minutes_per_hour = 60
hours_per_day = 24
month_names = ["Forge", "Smelt", "Anvil", "Ember", "Cinder", "Ash",
               "Frost", "Bone", "Hollow", "Veil", "Dusk", "Pyre"]
days_per_month = [30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30]
start_day = 1
start_hour = 8
start_minute = 0

[companion]
enabled = false
hero_id = ""
```

#### `entities/bob_blacksmith.toml`
```toml
entity_id = "bob_blacksmith"
entity_type = "npc"
name = "Bob the Blacksmith"
description = "A gruff but kind dwarven smith with a reputation for honest work."

[stats]
Health = 80
Strength = 14
Reputation_Brotherhood = 25
Location = "drakthar_capital_smithy"
Status = "Working"
```

#### `rules/death.toml`
```toml
rule_id = "death_below_zero"
priority = 0
target_entity = "*"

[conditions]
operator = "AND"
[[conditions.clauses]]
stat = "Health"
comparator = "<="
value = 0

[[actions]]
type = "stat_set"
stat = "Status"
value = "Dead"

[[actions]]
type = "trigger_event"
event = "player_death"
```

#### `locations/map.toml`
```toml
[[locations]]
location_id = "drakthar"
name = "Drakthar"
scale = "country"
description = "A grim kingdom of forges and feuds."
x = 500
y = 500

[[locations]]
location_id = "drakthar_capital"
name = "Drakthar City"
parent_id = "drakthar"
scale = "city"
description = "The capital. A maze of soot and stone."
x = 300
y = 400

[[locations]]
location_id = "drakthar_capital_smithy"
name = "The Iron Smithy"
parent_id = "drakthar_capital"
scale = "building"
description = "Bob's workshop. Hot, loud, and welcoming."

[[connections]]
source_id = "drakthar"
target_id = "northern_wastes"
distance_km = 240
```

### 7.4 Pipeline de compilation

```
Source (arborescence)  →  Compiler  →  .axiom-cache/universe.db
                                ↓
                          Hash check  →  skip if unchanged
```

Implémentation : `axiom/compile.py` (côté engine, accessible en CLI).

```python
def compile_universe(src_dir: Path, output_db: Path, force: bool = False) -> None:
    """Compile a source directory into a runtime SQLite database."""
    src_hash = _hash_directory(src_dir)
    cache_hash_file = src_dir / ".axiom-cache" / "cache_hash.txt"

    if not force and cache_hash_file.exists():
        if cache_hash_file.read_text().strip() == src_hash:
            return  # cache is up to date

    # Parse all .toml + .md files
    universe_meta = _parse_universe_toml(src_dir / "universe.toml")
    entities = _parse_entity_dir(src_dir / "entities")
    rules = _parse_rule_dir(src_dir / "rules")
    locations, connections = _parse_locations(src_dir / "locations" / "map.toml")
    lore_book = _parse_lore_book(src_dir / "lore")
    # ...

    # Build the DB
    create_universe_db(str(output_db))
    _populate_db(output_db, universe_meta, entities, rules, locations,
                 connections, lore_book, ...)

    # Write cache hash
    cache_hash_file.parent.mkdir(exist_ok=True)
    cache_hash_file.write_text(src_hash)
```

### 7.5 Format `.axiom` rebooté

Un `.axiom` devient un **zip de l'arborescence + cache compilé** :

```
my_universe.axiom (zip)
├── universe.toml
├── entities/
├── rules/
├── locations/
├── lore/
├── assets/
└── .axiom-cache/
    └── universe.db        ← prebuilt for instant load
```

À l'import :
1. Décompresse dans `~/AxiomAI/universes/<name>/`
2. Vérifie le hash : si correspond au cache embarqué, utilise le `.db` directement
3. Sinon, recompile

### 7.6 Saves restent binaires (séparés)

L'arborescence est la **définition immuable**. Les saves (état runtime,
Event_Log, State_Cache, Vector Memory) restent dans des DBs séparées :

```
~/AxiomAI/
├── universes/
│   └── drakthar/                ← source (mutable)
│       ├── universe.toml
│       └── ...
└── saves/
    └── drakthar/
        ├── save_<uuid>.db       ← state only (Event_Log, Saves, State_Cache)
        └── vector/<save_id>/    ← ChromaDB persist
```

Avantage : on peut **mettre à jour la définition d'univers** sans casser les
saves existants (tant que les entity_ids et rule_ids restent compatibles). Le
patch d'un univers par son auteur ne brique pas les parties en cours.

### 7.7 Mode dev avec hot reload

```bash
axiom dev universes/drakthar/
```

Watch le filesystem. À chaque modification :
1. Recompile (incrémental — uniquement les sous-arbres modifiés)
2. Notifie l'app qui re-charge le contexte (entités, rules, lore)
3. La partie en cours continue avec les nouvelles règles

C'est le **vrai mode "moddeur"** : éditer Bob.toml dans VS Code et voir
l'effet instantané dans le jeu.

### 7.8 Plugins déclarés par l'univers

```toml
# my_universe/plugins.toml
[required]
weather_system = ">=1.0.0"
combat_grid = ">=0.3.0"

[optional]
tts_piper = ">=0.1.0"
comfyui_scenes = ">=0.2.0"
```

Au chargement, l'app vérifie. Manquants → propose d'installer. Cf. Pilier 6.

### 7.9 AI-assisted authoring

Avec une arborescence texte, un LLM agentique (Claude Code, Cursor, etc.) peut
**éditer un univers** :

> "Add three rival merchants in the capital who compete for Bob's apprenticeship."

→ Le LLM crée `entities/merchant_alice.toml`, `entities/merchant_zog.toml`,
`entities/merchant_petra.toml`, écrit du lore dans
`lore/merchants/apprenticeship_rivalry.md`, ajoute une rule
`rules/apprentice_choice.toml`. Visible en diff git, approuvable par l'humain.

### 7.10 Migration des univers existants

Outil : `axiom decompile <universe.db> <output_dir>`.

Lit le .db, écrit l'arborescence équivalente. Préserve les UUIDs et les
relations. Une migration en une commande.

### 7.11 Coût

3 à 4 semaines :
- 1 semaine pour le compiler (toml/md parsing → DB)
- 1 semaine pour le decompiler (DB → toml/md)
- 1 semaine pour adapter Creator Studio (lire/écrire l'arborescence)
- 1 semaine pour mode dev / hot reload / packaging .axiom v2

Risque : casse les .axiom v1. À mitiger par compat backward (importer
v1 → décompile → recompile en v2).

---

## 8. Pilier 6 — Système de plugins 🏗

Reprise et formalisation détaillée de la réponse précédente sur les plugins.

### 8.1 Constat

Aujourd'hui :
- Backends LLM hardcodés (`if backend == "universal": ... elif "gemini": ...`)
- Aucune extensibilité communautaire
- Toute feature future = code core
- Pas de capabilities multimodales (image gen, TTS, STT) faute d'architecture
- Pas de moyen pour la communauté d'ajouter des outils ou rules

### 8.2 Cible : 11 "kinds" d'extension

Un plugin déclare son **kind** parmi 11 types prédéfinis. Un même package peut
en bundler plusieurs.

#### Kind 1 — `backend` : Nouveaux fournisseurs LLM

Implémente l'interface `LLMBackend`. Décorateur + config schema auto-génère
l'onglet Settings.

```python
@axiom.plugin(kind="backend", name="claude")
class ClaudeBackend:
    display_name = "Anthropic Claude"
    config_schema = {
        "api_key": {"type": "secret", "required": True},
        "model": {"type": "string", "default": "claude-sonnet-4-6"},
        "max_retries": {"type": "integer", "default": 3, "min": 0, "max": 10},
    }

    def __init__(self, config: dict):
        from anthropic import Anthropic
        self.client = Anthropic(api_key=config["api_key"])
        self.model = config["model"]

    def complete(self, messages, **kwargs) -> LLMResponse: ...
    def stream_tokens(self, messages, **kwargs) -> Iterator[str]: ...
    def is_available(self) -> bool: ...
```

**Exemples plausibles :** Claude, Mistral La Plateforme, OpenRouter, llama.cpp
direct, vLLM, TabbyAPI, Groq, DeepSeek, Exllama, Together AI.

#### Kind 2 — `embedding` : Modèle d'embedding pour le RAG

```python
@axiom.plugin(kind="embedding", name="ollama_embed")
class OllamaEmbedding:
    config_schema = {
        "endpoint": {"type": "string", "default": "http://localhost:11434"},
        "model": {"type": "string", "default": "nomic-embed-text"},
    }

    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...

    @property
    def dimensions(self) -> int: return 768
```

**Pourquoi c'est crucial :** un utilisateur de KoboldCPP peut **virer
sentence-transformers + torch** (~500 MB) en utilisant un embedding via
Ollama ou un modèle ONNX léger.

**Alternatives possibles :** `nomic_local`, `bge_onnx`, `openai_embed`,
`model2vec` (10× plus rapide, no-torch).

#### Kind 3 — `vector_store` : Backend de stockage vectoriel

```python
@axiom.plugin(kind="vector_store", name="sqlite_vec")
class SQLiteVecStore:
    def embed_chunk(self, save_id, turn_id, text, metadata) -> str: ...
    def query(self, save_id, query, k, **filters) -> list[dict]: ...
    def rollback(self, save_id, target_turn_id) -> int: ...
```

**Alternatives :** `chromadb` (default), `sqlite-vec`, `faiss-cpu`,
`qdrant_local`.

#### Kind 4 — `tool` : Nouveaux outils que le LLM peut appeler ⭐

**Le plus puissant.** Étend la palette d'actions narratives sans toucher au
core.

Aujourd'hui le LLM peut faire `state_changes` et `inventory_changes`. Un plugin
tool ajoute un nouveau champ au tool_call et fournit le handler.

```python
@axiom.plugin(kind="tool", name="weather")
class WeatherTool:
    schema = {
        "name": "change_weather",
        "description": "Change the weather at a location.",
        "parameters": {
            "location_id": "string",
            "weather": ["sunny", "rainy", "stormy", "snowy", "foggy"],
            "duration_minutes": "integer",
        },
    }

    def validate(self, session, params) -> tuple[bool, str]:
        if params["location_id"] not in session.locations:
            return False, f"Unknown location: {params['location_id']}"
        if params["weather"] not in {"sunny", "rainy", "stormy", "snowy", "foggy"}:
            return False, f"Unknown weather: {params['weather']}"
        return True, ""

    def apply(self, session, params):
        session.events.append("weather_change", params["location_id"], params)
        session.set_stat(params["location_id"], "Weather", params["weather"])
```

Le `prompt_builder` lit la liste des tools enregistrés, leur schema est injecté
dans le `NARRATIVE_TOOL_CALL_SCHEMA`. L'Arbitrator au Step 7 voit le champ
`change_weather` dans le tool_call, retrouve le handler, valide, applique.

**Exemples envisageables :** `weather`, `summon_npc`, `time_skip`,
`dispatch_quest`, `dice_roll`, `teleport`, `discover_lore`, `apply_curse`,
`spawn_loot`, `change_faction_relation`.

#### Kind 5 — `rule_action` : Nouveaux types d'action pour le RulesEngine

Aujourd'hui : `stat_change`, `stat_set`, `trigger_event`, `set_status`. Un
plugin peut ajouter `give_item`, `apply_buff`, `spawn_entity`, etc.

```python
@axiom.plugin(kind="rule_action", name="apply_buff")
class ApplyBuffAction:
    def execute(self, session, entity_id: str, params: dict):
        session.modifiers.add(
            entity_id,
            params["stat"],
            params["delta"],
            params["minutes"],
        )
```

Référencé dans une rule TOML :
```toml
[[actions]]
type = "apply_buff"
target = "player"
params = {stat = "Strength", delta = 5, minutes = 60}
```

#### Kind 6 — `capability` : Fonctionnalités optionnelles (multimodal)

Pour les features lourdes/optionnelles : image gen, TTS, STT, traduction.

```python
@axiom.plugin(kind="capability", subtype="image_gen", name="comfyui")
class ComfyUIImages:
    config_schema = {
        "endpoint": {"type": "string", "default": "http://localhost:8188"},
        "trigger_tags": {"type": "list", "default": ["combat", "scene_change"]},
        "style_lora": {"type": "string", "default": ""},
    }

    async def generate(self, narrative_text: str, context: dict) -> bytes | None:
        """Return PNG bytes that get embedded in the chat, or None."""
        ...
```

La `NarrativeView` (Pilier 3) interroge les capabilities `image_gen` actives
et insère l'image inline si tag de scène match. Si aucun plugin actif → rien
ne se passe, app fonctionne pareil.

**Subtypes possibles :** `image_gen`, `tts`, `stt`, `translation`, `music_gen`,
`portrait_gen`.

**Exemples :**
- `comfyui_scenes` : Stable Diffusion via ComfyUI local
- `piper_tts` : narration audio locale
- `whisper_stt` : entrée vocale
- `auto_translator` : narratif traduit en temps réel

#### Kind 7 — `importer` : Nouveaux formats d'import

```python
@axiom.plugin(kind="importer", extensions=[".lorebook.json"], name="novelai_lorebook")
class NovelAIImporter:
    display_name = "NovelAI Lorebook"

    def parse(self, filepath: str) -> UniverseData:
        """Parse the file and return a structure ready for the universe compiler."""
        ...
```

**Exemples :** NovelAI lorebook, AI Dungeon scenarios, World Anvil exports,
Foundry VTT modules (subset), Twine scenarios.

#### Kind 8 — `hook` : Réactions aux événements du cycle de vie ⭐⭐

**Le plus polyvalent.** Permet de réagir à n'importe quel événement sans
toucher au code core. C'est ici qu'on implémente des **systèmes de jeu entiers
comme plugins**.

```python
@axiom.plugin(kind="hook", name="hp_warning")
class HPWarning:
    listens_to = ["turn_complete", "stat_changed"]

    def on_turn_complete(self, session, result):
        player = session.get_entity("player")
        if player and int(player.stats.get("HP", 100)) < 20:
            session.notify("⚠ Low HP", level="warning", duration_ms=3000)

    def on_stat_changed(self, session, entity_id, stat_key, old, new):
        if stat_key == "Sanity" and int(new) < int(old) - 10:
            session.log_to_timeline("Sanity dropped sharply.")
```

**Événements lifecycle disponibles :**

| Event | Quand | Payload |
|---|---|---|
| `session_started` | Au chargement d'un save | `session` |
| `session_ending` | Avant fermeture | `session` |
| `turn_starting` | Avant Arbitrator | `session, user_input` |
| `turn_complete` | Après Arbitrator+Rules | `session, result` |
| `state_change_applied` | Pour chaque change validé | `session, change` |
| `state_change_rejected` | Pour chaque change rejeté | `session, change, reason` |
| `rule_triggered` | Quand une rule fire | `session, rule_id, action` |
| `chronicler_tick` | Avant Chronicler run | `session, current_minute` |
| `chronicler_complete` | Après Chronicler run | `session, result` |
| `player_death` | Sur trigger_event:player_death | `session` |
| `entity_created` | Création runtime | `session, entity_id` |
| `entity_deleted` | Suppression runtime | `session, entity_id` |
| `rewind_executed` | Après rewind | `session, target_turn` |
| `variant_switched` | Switch de variant narratif | `session, turn_id, index` |
| `scheduled_event_fired` | Trigger d'un Scheduled_Event | `session, event` |
| `location_changed` | Player change de Location | `session, old, new, distance_km` |

**Systèmes entiers comme plugins hook :**
- Faim/soif/sommeil (decay stats périodique via `chronicler_tick`)
- Économie (markets, prix dynamiques)
- Météo dynamique
- Système de quêtes avec compteur d'objectifs
- Journal automatique
- Système de niveaux et XP
- Reputation tracking entre factions

#### Kind 9 — `view` : Nouveaux panneaux UI

```python
@axiom.plugin(kind="view", target="tabletop_sidebar", name="combat_tracker")
class CombatTracker:
    title = "Combat"
    icon = "sword.svg"

    def build(self, parent: QWidget, session: Session) -> QWidget:
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)
        # ...
        session.subscribe("turn_complete", lambda _, r: self._update(r))
        return widget

    def _update(self, result):
        # Update visual
        ...
```

**Targets possibles :**
- `tabletop_sidebar` : nouvel onglet dans la sidebar (à côté de Stats/Inventory/Timeline)
- `tabletop_header` : zone topbar étendue
- `creator_studio_tab` : nouvel onglet Creator Studio
- `hub_extra_panel` : panneau additionnel sur la Hub
- `settings_section` : section additionnelle dans Settings

#### Kind 10 — `theme` : Identité visuelle alternative

```
plugins/themes/parchment/
  manifest.toml
  theme.qss
  narrative_view.toml         ← config pour le NarrativeView (typo, drop caps, ...)
  fonts/
    EBGaramond-Regular.ttf
    EBGaramond-Italic.ttf
  audio/
    tavern/
      celtic_jig.mp3
      celtic_lament.mp3
  icons/
    sword.svg
    ...
```

```toml
# manifest.toml
name = "parchment"
display_name = "Parchment & Ink"
description = "Old-world editorial theme."
[fonts]
serif = "EB Garamond"
sans = "IM Fell English"
mono = "JetBrains Mono"

[narrative_view]
drop_caps = true
pull_quote_indent = 24
dialog_in_italic = false  # uses quote marks instead

[audio_replacements]
"tavern" = "./audio/tavern"

[qss]
file = "theme.qss"
```

Switchable depuis Settings → Appearance.

#### Kind 11 — `localization` : Langues additionnelles ou overrides

```python
@axiom.plugin(kind="localization", lang="ja_kansai")
class KansaiJapanese:
    extends = "ja"
    overrides = {
        "send": "送るで",
        "ready": "ええで",
        # ...
    }
```

Ou en TOML pur :
```toml
# manifest.toml
[localization]
lang = "ja_kansai"
extends = "ja"

[strings]
send = "送るで"
ready = "ええで"
```

### 8.3 Ce qu'un plugin NE peut PAS faire (limites par design)

| Limite | Pourquoi |
|---|---|
| Modifier rétroactivement le `Event_Log` | Append-only. Invariant qui rend le rewind fiable. |
| Bypasser la validation de l'Arbitrator | Les state_changes plugin passent par `validate_change` aussi. Sinon les univers deviennent incohérents. |
| Accéder aux données d'un autre save | L'API `session` est scopée au save courant. |
| Désactiver le Hardcore deletion | Trop dangereux. C'est un engagement de design (irrévocable). |
| Bloquer le main thread > 5 sec | Tout hook a un timeout. Si dépassé → killé, warning logué, jeu continue. |
| Lire les secrets d'un autre plugin | Chaque plugin a son namespace de config dans `settings.json`. |
| Écrire directement dans le schema SQL | Toute persistance passe par l'API `session`. |

**Pas de sandbox Python réel** (impossible en pratique sans sous-processus
isolé) : le modèle de confiance = "tu installes du code Python comme un
`pip install`". Mitigations :

- Le `manifest.toml` déclare les **permissions demandées** :
  `permissions = ["network", "filesystem.read", "filesystem.write", "subprocess", "ui"]`
- L'UI d'installation **montre ces permissions** à l'utilisateur
- Une signature des plugins "officiels" via keyring Axiom (v2, optionnelle)
- Logs : tout appel `subprocess.*` d'un plugin est logué pour audit

### 8.4 Anatomie d'un plugin

```
my_plugin/
  manifest.toml                   ← obligatoire
  __init__.py                     ← ou plugin.py
  README.md
  config_defaults.toml            ← optionnel
  assets/                         ← optionnel
    icons/
    qss/
```

`manifest.toml` :
```toml
name = "weather_system"
version = "1.0.0"
author = "Garen"
license = "MIT"
homepage = "https://github.com/garen/axiom-weather"
engine_version = ">=0.5.0,<2.0.0"
permissions = ["filesystem.read"]
description = "Adds dynamic weather to locations."

[entry_points]
tools = ["WeatherTool"]
rule_actions = ["ApplyWeatherEffect"]
hooks = ["WeatherDecay"]
views = ["WeatherSidebarPanel"]

[dependencies]
# autres plugins requis
combat_grid = ">=0.3.0"
```

`plugin.py` :
```python
from axiom.plugin_api import tool, hook, view

@tool(name="change_weather")
class WeatherTool:
    schema = {...}
    def validate(self, session, params): ...
    def apply(self, session, params): ...

@hook(name="weather_decay", listens_to=["chronicler_tick"])
class WeatherDecay:
    def on_chronicler_tick(self, session, current_minute): ...

@view(target="tabletop_sidebar", title="Weather", icon="cloud.svg")
class WeatherSidebarPanel: ...
```

### 8.5 Deux modes d'installation

**A. Folder install (zéro setup)**
1. Copier le dossier dans `~/.config/AxiomAI/plugins/`
2. Redémarrer Axiom (ou bouton "Reload Plugins" dans Settings)

**B. pip-installable (pour partage propre)**

Le plugin déclare un entry point :
```toml
# pyproject.toml du plugin
[project.entry-points."axiom.plugins"]
weather = "axiom_weather:WeatherPlugin"
```

```bash
pip install axiom-weather
```

Découvert via `importlib.metadata.entry_points(group="axiom.plugins")` au
démarrage.

### 8.6 API `session` exposée au plugin

Le plugin reçoit un objet `Session` curated, **pas l'accès direct à la DB**.
C'est ça qui définit la "surface" stable et versionnée.

```python
class Session:  # ce que le plugin voit
    # === Read ===
    entities: dict[str, EntityView]
    locations: dict[str, LocationView]
    current_time: int                       # in-game minutes
    turn_id: int
    save_id: str
    universe_meta: dict

    def stats_of(self, entity_id: str) -> dict[str, str]: ...
    def history(self, last_n: int = 10) -> list[Event]: ...
    def rag_query(self, text: str, k: int = 5) -> list[Chunk]: ...
    def get_entity(self, entity_id: str) -> EntityView | None: ...

    # === Write (via pipeline normal, donc validation + event log) ===
    def set_stat(self, entity_id: str, key: str, value: str | int | float): ...
    def apply_delta(self, entity_id: str, key: str, delta: float): ...
    def add_modifier(self, entity_id: str, key: str, delta: float, minutes: int): ...
    def add_item(self, entity_id: str, item_id: str, quantity: int): ...
    def remove_item(self, entity_id: str, item_id: str, quantity: int): ...
    def create_entity(self, spec: dict) -> str: ...
    def log_to_timeline(self, description: str, time_offset: int = 0): ...
    def append_event(self, event_type: str, target: str, payload: dict): ...

    # === UI side-effects ===
    def notify(self, message: str, level: str = "info", duration_ms: int = 3000): ...
    def update_audio_tag(self, tag: str): ...
    def request_image(self, prompt: str): ...

    # === Subscription ===
    def subscribe(self, event_name: str, callback: Callable): ...
    def unsubscribe(self, subscription_id: int): ...

    # === Plugin's own storage ===
    def plugin_storage(self, plugin_name: str) -> dict:
        """Persisted in Universe_Meta under plugin namespace."""
        ...
```

L'API est **versionnée**. Si on casse l'API en v2.0, le plugin doit déclarer
compat (`engine_version` dans manifest).

### 8.7 UI Settings → Plugins

```
┌─────────────────────────────────────────────────────────┐
│  Installed Plugins                                       │
├─────────────────────────────────────────────────────────┤
│  [✓] Weather System            v1.0.0   [Configure ⚙]   │
│      Adds dynamic weather to locations.                  │
│      Permissions: filesystem.read                        │
│                                                          │
│  [✓] Claude Backend            v2.1.0   [Configure ⚙]   │
│      Anthropic Claude LLM provider.                      │
│      Permissions: network                                │
│                                                          │
│  [ ] ComfyUI Scenes            v0.3.0   [Configure ⚙]   │
│      Auto-generate scene illustrations.                  │
│      Permissions: network                                │
├─────────────────────────────────────────────────────────┤
│  [Install from folder…]  [Install from Git URL…]         │
│  [Browse community plugins…]                             │
└─────────────────────────────────────────────────────────┘
```

Chaque plugin a son propre dialog de config généré depuis `config_schema`.

### 8.8 Cycle de vie d'un plugin

1. **Discovery** au startup :
   - Scan `~/.config/AxiomAI/plugins/*/manifest.toml`
   - `importlib.metadata.entry_points(group="axiom.plugins")`
2. **Validation** :
   - `engine_version` compatible ?
   - Dépendances présentes ?
   - Permissions acceptables ?
3. **Loading** :
   - Import du module
   - Instanciation des classes décorées (kind par kind)
   - Registration dans le plugin registry global
4. **Activation** :
   - Si plugin enabled dans config : hooks attachés, tools enregistrés
   - Sinon : reste en standby
5. **Reload** :
   - Triggerable via bouton UI
   - Tear down propre (subscriptions, threads)
   - Re-import dynamique

### 8.9 Ordre d'implémentation des kinds

Par utilité immédiate vs complexité :
1. `backend` (déjà presque là, refactor minimal)
2. `embedding` + `vector_store` (débloque la simplification deps)
3. `hook` (polyvalent, base pour le reste)
4. `tool` (étend le pouvoir narratif)
5. `rule_action` (extension naturelle du RulesEngine)
6. `view` + `capability` (visuel/multimodal)
7. `importer` + `theme` + `localization` (nice-to-have)

### 8.10 Coût total estimé

3 à 4 semaines pour le système complet :
- 1 semaine : registry, manifest parsing, discovery, lifecycle
- 1 semaine : kinds backend/embedding/vector_store + refactor existant
- 1 semaine : kinds hook + tool + rule_action
- 0.5 semaine : kinds view + capability (peut être lazy après)
- 0.5 semaine : UI Settings → Plugins + doc modder

---

# PARTIE III — PROFONDEUR DU GAMEPLAY (Phase C)

Une fois l'architecture en place, on attaque ce qui rend Axiom **unique**.
**Durée estimée : 4 à 6 semaines.**

## 9. Pilier 4 — Mémoire par NPC + Actor Model 🏗

### 9.1 Constat

Aujourd'hui :
- Le RAG est **partagé par save** : toutes les entités voient les mêmes
  chunks narratifs. Pas de "ce que sait Bob" vs "ce que sait Alice".
- Le Chronicler est **monolithique** : un seul appel LLM voit toutes les
  entités et décide pour toutes simultanément.
- Les NPCs n'ont **pas de mémoire propre**. Le joueur peut tuer Karl à
  l'autre bout du monde, Bob l'apprend instantanément (ou jamais, selon
  le hasard du RAG).

C'est limité par rapport au potentiel d'un jeu narratif. Le Pilier 4 résout
ça en **inversant le paradigme** : la mémoire et l'agentivité deviennent
**par-entité**.

### 9.2 Cible — Mémoire perspectiviste

Chaque NPC a son propre namespace dans la VectorMemory.

```python
# Schema metadata étendu
{
    "save_id": "uuid",
    "turn_id": 42,
    "chunk_type": "narrative" | "lore" | "rumor",
    "perspective": "bob_blacksmith",        # NEW
    "witnessed": True,                       # NEW : témoin direct ou hearsay ?
    "source": "first_hand" | "from:alice",  # NEW : si hearsay, de qui
    "confidence": 1.0,                       # NEW : décroît avec le hearsay
}
```

**Embedding pipeline modifié :**

À chaque turn de l'Arbitrator, après génération du narrative :
1. Déterminer **qui est présent à la scène** :
   - Le player (toujours)
   - Les NPCs dont `stats.Location == player.stats.Location`
   - Les factions mentionnées dans le narratif
2. Pour chaque témoin, embed le chunk avec `perspective=entity_id`,
   `witnessed=True`, `source="first_hand"`, `confidence=1.0`.

**Query pipeline modifié :**

Quand l'Arbitrator construit le prompt pour un turn où le joueur interagit
avec Bob :
- Le RAG query est scopé à `perspective IN ("player", "bob_blacksmith", "world_general")`
- Bob ne sait pas ce qu'il n'a pas vécu
- Le `world_general` namespace contient les événements publics (annonces du
  Chronicler par exemple)

### 9.3 Propagation de rumeurs

À chaque `chronicler_tick`, un sous-système "Rumor Propagation" :

1. Pour chaque paire d'entités au même `Location` :
   - Avec probabilité `P(spread) = sociability_A * sociability_B * 0.1`
   - Sample N chunks récents de A's memory (où `witnessed=True`)
   - Embed dans B's memory avec :
     - `witnessed=False`
     - `source=f"from:{A}"`
     - `confidence=A.confidence * decay_factor`

Le `decay_factor` (par exemple 0.7) modélise la déformation de l'info.

Au bout de 4-5 transmissions, `confidence < 0.1` → le chunk peut devenir
faux/déformé. À ce moment, le système peut soit drop le chunk, soit le
**re-générer via LLM** avec instruction "déforme cette info comme une rumeur
embellie".

### 9.4 NPCs comme acteurs autonomes (remplacement du Chronicler monolithique)

Remplacer le Chronicler unique par des **NPCAgents** individuels.

```python
@dataclass
class NPCAgent:
    entity_id: str
    persona: str                    # description statique
    agenda: str                     # 1 ligne objectif courant : "Avenger mon frère"
    mood: str                       # state machine simple
    importance: int                 # 0-10, drive la fréquence de tick
    last_acted_at_minute: int

    def tick(self, session: Session, current_minute: int) -> ChroniclerResult:
        # Récupérer mémoire propre
        own_memory = session.rag_query(
            query=self.agenda,
            perspective=self.entity_id,
            k=5,
        )

        # Build prompt micro
        prompt = build_npc_agent_prompt(
            persona=self.persona,
            agenda=self.agenda,
            mood=self.mood,
            current_stats=session.stats_of(self.entity_id),
            current_location=session.locations[self.location_id],
            recent_memory=own_memory,
            elapsed_since_last_tick=current_minute - self.last_acted_at_minute,
        )

        # Petit LLM call (extraction_model — léger)
        response = session.llm_extraction.complete(prompt, max_tokens=200)
        # ...
```

**Fréquence de tick par importance :**
- Importance 10 (chef de faction) : chaque chronicler_tick (≈ 30 min)
- Importance 5 (NPC nommé) : 1 tick sur 3 (≈ 1h30)
- Importance 1 (figurant) : 1 tick sur 20 (≈ 10h)

**Budget global :** sur 30 NPCs nommés, ~10 ticks par chronicler trigger.
Chaque tick = 1 appel LLM 200 tokens ≈ 1-2 sec sur modèle local 8B. Total
~10-20 sec en arrière-plan. Acceptable.

### 9.5 Carte mentale d'un NPC

Chaque `NPCAgent` maintient une **carte mentale légère** (persistée en
`Universe_Meta` ou table dédiée) :

```toml
[bob_blacksmith.mental_map]
"player" = {opinion = 0.7, last_seen_turn = 42, known_facts = ["wields_excalibur", "killed_karl"]}
"alice" = {opinion = -0.2, last_seen_turn = 30, known_facts = ["merchant_in_capital"]}
"iron_brotherhood" = {opinion = 0.9, last_seen_turn = 0, known_facts = ["my_faction"]}
```

Quand Bob est consulté par le LLM (apparition dans une scène), sa carte
mentale est injectée comme contexte. Le LLM sait **exactement ce que Bob sait
ou pense**.

### 9.6 Émergence des plots

Avec ce système, des phénomènes émergent **sans script** :
- Bob entend par Alice (qui l'a entendu par un voyageur) que le joueur a
  insulté l'Iron Brotherhood. Bob (faction = Iron Brotherhood) baisse son
  opinion du joueur de 0.7 à 0.1.
- Au prochain craft, Bob refuse la commande du joueur. Le joueur s'étonne :
  "Pourquoi ?" — Bob répond : "J'ai entendu ce que vous avez fait à la
  capitale."
- Le joueur n'a *jamais explicitement* dit ça à Bob. C'est émergé du système.

C'est ça qui ferait d'Axiom AI un **vrai** RPG narratif vivant.

### 9.7 Plan d'implémentation

**Étape 1.** Étendre `VectorMemory` pour supporter `perspective` dans les
metadata + filter dans `query()`. 2 jours.

**Étape 2.** Modifier l'Arbitrator pour embedder un chunk par perspective
(player + NPCs présents). 2 jours.

**Étape 3.** Remplacer le Chronicler monolithique par un `NPCAgent` manager.
Garder le monolithique en fallback pour les "world news" macro. 4 jours.

**Étape 4.** Système de propagation de rumeurs (rumor decay). 3 jours.

**Étape 5.** Mental map persistée. 2 jours.

**Étape 6.** Prompt builder pour NPCAgent. 2 jours.

**Étape 7.** Tests d'intégration : scénario scripté qui valide l'émergence. 3 jours.

Total : ~3 semaines.

### 9.8 Coût LLM par turn

Hypothèse : 30 NPCs nommés, modèle local 8B (Ollama / KoboldCPP).
- Avant : 1 chronicler ~ 1500 tokens prompt, 500 tokens response → 1 appel
- Après : 10 NPCAgent × (300 prompt + 100 response) → 10 appels, mais
  context window plus petit par appel
- Total tokens similaire, mais **parallélisable** (les NPCAgents tickent
  indépendamment)

Sur cloud (Gemini, Claude) : surcoût acceptable, ~10× plus d'appels mais
courts. À budgeter selon le pricing.

---

## 10. Pilier 7 — Harnais de test déterministe pour univers 🏗

### 10.1 Constat

Aujourd'hui :
- Tests pytest couvrent l'engine (266+ tests) — bon
- Tests UI quasi inexistants (juste `test_chat_buffer.py`)
- **Aucun moyen de tester un UNIVERS** : rules incohérentes, FK orphelines,
  prompts qui matchent mal le système, etc.
- Conséquence : un mod buggué casse à l'utilisateur final

### 10.2 Cible — Format de scénario YAML

```yaml
# scenarios/death_in_combat.yaml
name: "Death in combat triggers Status=Dead"
universe: "./universes/drakthar"
seed: 42                              # determinism for randomness

initial_state:
  player_persona: "A weary mercenary."
  setup_answers:
    race: "Human"
    background: "Soldier"

scripted_turns:
  - turn: 1
    input: "I attack the goblin chief."
    llm_response: |
      You charge forward and swing your blade with all your strength.
      The goblin chief is impaled. He collapses, lifeless.

      ~~~json
      {
        "state_changes": [
          {"entity_id": "goblin_chief", "stat_key": "HP", "delta": -150}
        ],
        "elapsed_minutes": 2,
        "game_state_tag": "combat"
      }
      ~~~

expectations:
  - after_turn: 1
    assert:
      - entity: "goblin_chief"
        stats:
          Status: "Dead"           # via low_hp_death rule
          HP: 0                    # clipped to 0
      - timeline_contains: "goblin_chief"

  - after_turn: 1
    timeline_should_have_event: "rule_trigger"
    with_payload:
      stat: "Status"
      value: "Dead"
```

### 10.3 Runner CLI

```bash
axiom test scenarios/death_in_combat.yaml
# ✓ Universe loaded
# ✓ Save initialized
# ✓ Turn 1 LLM response injected
# ✓ State changes applied
# ✓ Death rule fired
# ✓ Status set to Dead
# ✗ Expected HP=0, got HP=-150 (Arbitrator should clip negative resources?)
# ──
# Result: 5/6 passed.
```

```bash
axiom test scenarios/                  # run all scenarios in folder
axiom test --watch                     # rerun on file changes (modder mode)
```

### 10.4 Mock LLM injection

Le harnais utilise un `ScriptedLLM` qui implémente l'interface `LLMBackend`
mais répond avec des réponses pré-écrites :

```python
class ScriptedLLM(LLMBackend):
    def __init__(self, scripted_responses: list[str]):
        self._responses = list(scripted_responses)
        self._index = 0

    def complete(self, messages, **kwargs) -> LLMResponse:
        if self._index >= len(self._responses):
            raise IndexError("Scenario exhausted: more LLM calls than scripted.")
        raw = self._responses[self._index]
        self._index += 1
        narrative, tool_call = self.parse_tool_call(raw)
        return LLMResponse(narrative_text=narrative, tool_call=tool_call,
                          finish_reason="stop")

    def stream_tokens(self, messages, **kwargs):
        yield self._responses[self._index]
```

Combiné avec `_FakeEmbeddingFn` (déjà présent dans les tests), le scénario
tourne en **moins d'une seconde** sans réseau.

### 10.5 Types d'assertions disponibles

```yaml
assert:
  - entity: "bob"
    stats:
      Health: 50                       # exact match
      Status: { not: "Dead" }          # negation
      Reputation: { gte: 0, lte: 100 } # range
  - timeline_contains: "Arrived at Hemlock"
  - rag_should_have_chunk:
      perspective: "bob"
      contains_text: "killed Karl"
  - rule_did_trigger: "death_rule"
  - rule_did_not_trigger: "fallback_resurrection"
  - chronicler_did_run: true
  - elapsed_total_minutes: { gte: 60 }
  - error_should_be_raised: false
```

### 10.6 Scenarios stockés dans l'univers

Un univers peut **livrer ses scénarios de test** :

```
my_universe/
  ...
  tests/
    death_basic.yaml
    faction_betrayal.yaml
    hardcore_full_run.yaml
```

Le compiler peut exécuter `axiom test` automatiquement à la fin pour valider.

### 10.7 CI GitHub Actions pour univers communautaires

```yaml
# .github/workflows/test.yml dans un repo d'univers
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install axiom-engine
      - run: axiom test tests/
```

C'est ça qui permet une **vraie communauté** : on peut accepter ou refuser
des PRs sur un univers selon que les tests passent.

### 10.8 Coût

1 à 2 semaines :
- ScriptedLLM : 1 jour
- YAML parser + runner : 3 jours
- Assertions library : 3 jours
- CLI integration : 2 jours
- Docs + exemples : 2 jours

---

# PARTIE IV — REFONTE VISUELLE (Phase D)

L'UI actuelle est fonctionnelle mais générique. Cette phase la transforme en
**identité visuelle forte, éditoriale, immersive**. **Durée estimée : 6 à 8
semaines.**

## 11. Pilier 3 — `NarrativeView` (custom visual framework) 🏗

### 11.1 Constat

Le chat actuel (`ui/widgets/chat_display.py`) est un `QTextBrowser` avec un
peu de parsing markdown (italic, bold). Il sait afficher des images HTTP
asynchrones, gérer des liens de variants, masquer les blocs `~~~json`. Bon
travail. Mais **visuellement plat**. Aucune signature.

Or, **la narration est le cœur d'Axiom AI**. Le composant qui l'affiche doit
être **le composant signature** du projet.

### 11.2 Cible — Spécification du `NarrativeView`

Un widget custom (QML + QPainter delegate, ou full QtWidgets avec
QGraphicsView, à arbitrer en POC) qui fait :

#### Typographie éditoriale

- **Police principale** : serif optique pour la prose (EB Garamond, Spectral,
  Cormorant Garamond, ou Lora — à choisir).
- **Police méta** : sans-serif moderne pour topbar, footer, méta-éléments
  (Inter, IBM Plex Sans, Source Sans).
- **Police mono** : pour les stats inline, les IDs, les codes de jeu (JetBrains
  Mono, Fira Code).
- Tailles configurables (déjà fait dans Settings : `ui_font_size`).
- Line-height généreux (1.6-1.8 pour la prose narrative).
- Mesure de paragraphe **éditoriale** : max-width 650-720px pour le confort
  de lecture. Le narratif n'occupe pas toute la largeur du chat.

#### Drop caps

Première lettre du premier paragraphe de chaque turn agrandie (3-4 lignes
de haut), couleur d'accent du thème. Comme un livre ancien.

```
A
   Aria pénétra dans la grange. L'air sentait
   le foin sec et la peur. Au fond, une silhouette
   bougea — un éclair de métal.
```

Implémentation : QPainter custom delegate qui détecte le premier caractère
et le rend séparément avec une fonte plus grosse, positionné en flow.

#### Pull quotes pour les dialogues

Les dialogues (texte entre guillemets) sont **mis en relief** :
- Indentation gauche subtile (+24 px)
- Police légèrement plus petite
- Couleur d'accent (vs gris pour le narratif standard)
- Filet vertical fin à gauche

```
Aria s'approcha lentement.

  | « Qui êtes-vous ? » demanda-t-elle, la voix
  | tremblante.

L'inconnu ne répondit pas tout de suite.
```

#### Marginalia (méta-éléments en marge)

`[HERO INTENT]`, world news Chronicler, rules rejected, time skips → en marge
gauche, plus petits, plus pâles. Ne perturbent pas la lecture mais sont là.

```
[INTENT]    | Aria approche prudemment de la
            | porte. Elle tourne la poignée...
            |
            | La porte s'ouvre sur une pièce
[2 min]     | sombre. Une silhouette se dresse
            | au fond.
            |
[HP -5]     | Aria reçoit un coup à l'épaule.
```

#### Entity tooltips

Tout nom d'entité reconnu (via lookup `Entities` table) devient hoverable :
- Soulignement subtil au survol
- Hover → mini-carte flottante : portrait (si plugin image_gen actif),
  current stats, dernière interaction, opinion sur le player
- Click → ouvre un panneau lateral détaillé

#### Page metaphor

- Transition entre turns animée :
  - Le nouveau turn slide-in depuis le bas (12 px de offset, 200 ms
    ease-out)
  - Fade-in opacity de 0 à 1 (300 ms)
- Optionnel "page turn" plus marqué quand `scene_pace = "montage"` ou time
  skip > 1h.

#### Scene blocks

Quand le LLM produit une description de scène (heuristique : début de turn
sans dialogue, paragraphe long, descriptif) :
- Affiché dans un **panneau plus large** (max-width 850 px au lieu de 720)
- Fond légèrement texturé (parchemin subtil, ou simple variation de luminosité)
- Drop cap plus prononcé
- Cadre fin

#### Reading mode

Bouton dédié ou F11 :
- Cache topbar, sidebar, mini-dico
- Centre le NarrativeView, max-width 800 px
- Background opaque au thème
- Seul l'input reste, en bas, minimaliste
- Esc pour revenir au mode normal

#### Background ambiance par tag

`game_state_tag` (exploration, combat, dialogue, tension) → overlay très
subtil :
- `exploration` : neutre, tons normaux
- `combat` : très léger tinté rouge (5% opacity), peut-être un faint pulse
- `dialogue` : très léger tinté bleu chaud
- `tension` : ambient grain texture qui s'intensifie

Pas brutal. Juste assez pour que l'œil perçoive l'atmosphère.

#### Variant navigation

Au lieu du `[1] [2] [3] [⟳ Regenerate]` minimaliste actuel :
- Petite bande discrète en bas du turn
- Animation de switch entre variants (cross-fade le contenu, pas juste
  changer le texte)
- Tooltip sur chaque variant indiquant la longueur, le tone

#### Player input

Au lieu du `QTextEdit` simple en bas :
- Champ avec **prompt suggestions** (3-4 actions plausibles dérivées du contexte
  via LLM extraction) en pills cliquables
- Auto-complétion sur les noms d'entités présentes
- Bouton inline "Dictate" si plugin STT actif (Whisper)
- Compteur de mots subtil (visible sous concentration)

### 11.3 Architecture technique

**Option A — QML + QPainter delegate** : permet animations natives, déclaratif,
moderne. Coût : courbe d'apprentissage QML, intégration avec workers Python à
designer.

**Option B — QGraphicsScene** : full Qt Widgets, contrôle pixel-perfect. Coût :
plus verbeux, animations à la main.

**Option C — QTextBrowser custom + QTextDocument heavily customized** : reste
proche de l'existant, ajoute drop caps via QTextCharFormat custom, marges via
QTextBlockFormat. Coût : limité par les capacités de QTextDocument (pas de
vraies marges latérales hybrides).

**Recommandation : Option A (QML)** pour la beauté et les animations, avec
fallback Option C pour le MVP rapide. Décision finale après un POC d'une
semaine.

### 11.4 Plan d'implémentation

**Étape 1 (POC, 1 semaine).** Drop caps + pull quotes + typographie de base.
Comparer les 3 options techniques sur un sample turn.

**Étape 2 (2 semaines).** Implémentation MVP avec :
- Typography settings
- Drop caps
- Pull quotes / dialogues mis en relief
- Marginalia (3 catégories minimum)
- Scene blocks détection heuristique
- Reading mode

**Étape 3 (1 semaine).** Entity tooltips + soulignements + lookup hover.

**Étape 4 (1 semaine).** Animations transitions + page metaphor + variant
crossfade.

**Étape 5 (0.5 semaine).** Background ambiance par tag.

**Étape 6 (0.5 semaine).** Input enrichi (suggestions, autocompletion).

**Étape 7 (1 semaine).** Polish, accessibilité (font-size global respecté
partout, contraste, lecteur d'écran si possible).

### 11.5 Coût

~6 semaines pour la version complète et polie. Un MVP suffisant peut sortir
en 2-3 semaines.

---

## 12. Système de tokens visuels & typographie

### 12.1 Constat

Aujourd'hui :
- `_DARK_QSS` est inline dans `main.py:23-242` (≈ 220 lignes)
- 15+ `setStyleSheet(...)` inline éparpillés (`tabletop_view.py:139,142,184,599`,
  `hub_view.py:96,205`, `creator_studio_view.py:70`, `entity_editor.py:86`, etc.)
- Aucune source de vérité unique pour les couleurs / espacements / radii
- Aucun système de **theme switching**

### 12.2 Cible — Tokens TOML centralisés

```toml
# assets/themes/mocha/tokens.toml
[colors]
bg_base = "#1e1e2e"
bg_raised = "#181825"
bg_overlay = "#11111b"

text_primary = "#cdd6f4"
text_secondary = "#a6adc8"
text_muted = "#585b70"

accent = "#89b4fa"
accent_hover = "#74c7ec"
accent_pressed = "#94e2d5"

success = "#a6e3a1"
warning = "#f9e2af"
danger = "#f38ba8"
info = "#89dceb"

border = "#313244"
border_focus = "#89b4fa"

[colors.entity_type]
player = "#cba6f7"
npc = "#89b4fa"
faction = "#fab387"
world = "#94e2d5"

[colors.rarity]
common = "#ffffff"
rare = "#4fa3ff"
epic = "#a335ee"
legendary = "#ff8000"

[typography]
font_serif = "EB Garamond"
font_sans = "Inter"
font_mono = "JetBrains Mono"

[typography.sizes]
xs = 10
sm = 11
md = 12
lg = 14
xl = 18
xxl = 24

[spacing]
xs = 2
sm = 4
md = 8
lg = 12
xl = 16
xxl = 24

[radii]
sm = 4
md = 6
lg = 8
xl = 12

[shadows]
sm = "0 1px 2px rgba(0, 0, 0, 0.15)"
md = "0 4px 8px rgba(0, 0, 0, 0.2)"
lg = "0 8px 16px rgba(0, 0, 0, 0.25)"

[animation]
fast = 150            # ms
normal = 300
slow = 500
ease = "ease-out"
```

### 12.3 QSS généré

Un module `core/theme.py` lit `tokens.toml` et **génère** le QSS au démarrage :

```python
def generate_qss(theme_name: str) -> str:
    tokens = _load_theme(theme_name)
    template = (Path("assets/themes") / theme_name / "template.qss").read_text()
    # Simple Jinja-like substitution
    return _substitute(template, tokens)
```

`template.qss` utilise des placeholders :
```css
QWidget {
    background-color: {{colors.bg_base}};
    color: {{colors.text_primary}};
    font-family: "{{typography.font_sans}}";
    font-size: {{typography.sizes.md}}pt;
}

QPushButton {
    background-color: {{colors.bg_raised}};
    color: {{colors.text_primary}};
    border: 1px solid {{colors.border}};
    border-radius: {{radii.md}}px;
    padding: {{spacing.sm}}px {{spacing.lg}}px;
    min-height: 28px;
}
QPushButton:hover { background-color: {{colors.accent}}; }
```

### 12.4 Suppression des setStyleSheet inline

Tous les `setStyleSheet(...)` éparpillés sont remplacés par des **classes CSS**
appliquées via `setObjectName` ou `setProperty("class", "primary-button")`,
gérées par le QSS global.

```python
# Avant
self._add_btn.setStyleSheet("background-color: #27ae60; font-weight: bold;")

# Après
self._add_btn.setProperty("class", "primary-action")
```

Dans le QSS :
```css
QPushButton[class="primary-action"] {
    background-color: {{colors.success}};
    color: {{colors.bg_overlay}};
    font-weight: bold;
}
```

### 12.5 Theme switching

Settings → Appearance → liste les themes installés (Mocha par défaut, +
themes plugins) → click switch instantané (regenerate QSS + `app.setStyleSheet()`).

### 12.6 Coût

1 semaine :
- Designer les tokens : 1 jour
- Écrire template QSS : 1 jour
- Migration des setStyleSheet inline : 2 jours
- Theme switching infrastructure : 1 jour

---

## 13. Refonte de la Hub

### 13.1 Constat

Le screenshot actuel montre une carte unique alignée en haut-gauche d'un grand
espace vide. La grille 3-colonnes ne sert pas tant qu'il n'y a pas 3 univers
installés. Aucune mise en valeur du dernier joué.

### 13.2 Cible

```
┌──────────────────────────────────────────────────────────────────┐
│  Axiom AI · Universe Library      [Import ST] [Import] [+ New]   │
│ ──────────────────────────────────────────────────────────────── │
│                                                                  │
│   ┌─ Continue last session ──────────────────────────────────┐  │
│   │  Drakthar — Aria the Mercenary  ·  Day 47, 14:32         │  │
│   │  [resume]                  [edit]   [delete]              │  │
│   └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│   Your Universes                                                 │
│                                                                  │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│   │ [cover.png] │  │ [cover.png] │  │ [cover.png] │             │
│   │             │  │             │  │             │             │
│   │ Drakthar    │  │ Skyholm     │  │ Ferrum Aeon │             │
│   │ ·············  │ ·············  │ ············· │             │
│   │ Dark fantasy│  │ Steampunk   │  │ Sci-fi noir │             │
│   │             │  │             │  │             │             │
│   │ ▸ 3 saves   │  │ ▸ 1 save    │  │ ▸ no saves  │             │
│   │ [play] [⋯]  │  │ [play] [⋯]  │  │ [play] [⋯]  │             │
│   └─────────────┘  └─────────────┘  └─────────────┘             │
│                                                                  │
│   Community (browse)                                             │
│   ┌─ Featured ─┐                                                 │
│   │ ...        │                                                 │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**Éléments clés :**
- **Continue last session** mis en avant si une save récente existe
- **Cover image** par univers (depuis `cover.png` dans la définition)
- **Genre tag** dérivé du Universe_Meta
- **Nb saves** par univers indiqué
- **[⋯] menu** pour Edit / Export / Delete (au lieu de 4 boutons)
- Section future **Community** pour browser des univers en ligne (v2)

### 13.3 Coût

1 semaine.

---

## 14. Refonte du Creator Studio

### 14.1 Constat

9 onglets : Metadata, Stats, Entities, Map, Rules, Events, Story Setup, Lore
Book, Populate. C'est dense et intimidant pour un nouveau créateur.

### 14.2 Cible — Regroupement en 5 sections logiques

```
┌─────────────────────────────────────────────────────────────────┐
│  ◀ Hub  ·  Drakthar  [Save Ctrl+S]              [Test ▶ Play]   │
│ ─────────────────────────────────────────────────────────────── │
│                                                                 │
│   ╔═══════════════════════════════════════════════════════════╗ │
│   ║ Overview │ World │ Systems │ Narrative │ AI Assist        ║ │
│   ╚═══════════════════════════════════════════════════════════╝ │
│                                                                 │
│   [content of selected tab]                                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Tab 1 — Overview** : ancien Metadata + cover image
- Universe name, author, version, license
- Global lore (large text area, syntax-highlighted Markdown)
- System prompt override
- First message (with variant editor)
- World tension slider
- LLM defaults (temp, top_p, verbosity)

**Tab 2 — World** : ancien Map + Locations subtab + Entities subtab
- Sub-tab "Map" (le map_editor actuel)
- Sub-tab "Entities" (entity_editor)
- Sub-tab "Items"
- Liés visuellement : sélectionner une location filtre les entités présentes

**Tab 3 — Systems** : ancien Stats + Rules + Modifiers
- Sub-tab "Stat Definitions"
- Sub-tab "Rules"
- Sub-tab "Item Definitions"

**Tab 4 — Narrative** : ancien Lore Book + Scheduled Events + Story Setup
- Sub-tab "Lore Book"
- Sub-tab "Scheduled Events"
- Sub-tab "Story Setup Questions"

**Tab 5 — AI Assist** : ancien Populate
- Plus exposé que aujourd'hui, valorisé comme un workflow
- Wizard guidé : "Quel système voulez-vous générer ?" → AI prompt → review

### 14.3 Améliorations transverses

- **Save indicator** : * dans le titre si modif non sauvé
- **Auto-save toggle** dans settings (sauve toutes les 30 sec, ou jamais)
- **Undo/redo** au niveau du Creator (Ctrl+Z annule la dernière action de
  modification, pas un rewind de partie)
- **Validation en temps réel** : indicators visuels sur les onglets si
  problème détecté (e.g., rule référence un stat inexistant → red badge sur
  Rules tab)
- **Live preview** : un panneau latéral optionnel qui simule le rendu LLM
  prompt avec les données courantes (pour les rédacteurs lore)

### 14.4 Coût

2 semaines.

---

## 15. Refonte du Tabletop View (hors NarrativeView)

### 15.1 Topbar nettoyée

Actuellement 7+ éléments en topbar (save label, turn, time, player selector,
verbosity slider, rewind, hub). Trop dense.

**Cible :**
```
┌────────────────────────────────────────────────────────────────┐
│ ◀ Drakthar · Day 47, 14:32       [Aria ▾]    [⏪ Rewind] [⋯]  │
└────────────────────────────────────────────────────────────────┘
```
- **Universe name + time** comme un title
- **Active player** en dropdown compact
- **Rewind** comme bouton dédié (Ctrl+Z aussi)
- **[⋯] menu** : Verbosity, Settings universe params, Hub return

### 15.2 Sidebar enrichie

3 onglets actuels (Stats, Inventory, Timeline). Ajouts possibles :
- **Quests** (si plugin quest_system actif)
- **Map** (mini-carte de la location courante)
- **NPCs** (liste des NPCs présents à la scène avec opinion/mood)
- **Mental notes** (espace pour notes du joueur)

Sidebars repliables (collapse à 24 px) pour libérer la zone narratif.

### 15.3 Mini-Dico repensé

Actuellement à droite, panneau étroit, sous-utilisé. Cible :
- Slide-in overlay (Ctrl+L pour ouvrir)
- Search-as-you-type dans le lore
- Résultats avec snippets pertinents
- Bouton "Ask Mini-Dico" pour question libre

### 15.4 Coût

1.5 semaines.

---

## 16. Modes Game / Studio (split de personnalité visuelle)

### 16.1 Constat

L'UI de la Hub, du Creator Studio et du Tabletop a aujourd'hui le **même look**.
Or, ce sont **3 expériences mentales différentes** :
- Hub : choix, browsing
- Creator Studio : édition dense, tableur, productivité
- Tabletop : narration, immersion

### 16.2 Cible — 2 langages visuels distincts

**Mode "Game" (Tabletop, Hub)** :
- Typographie serif dominante
- Couleurs plus chaudes
- Espacement généreux
- Animations subtiles
- Background optional textured

**Mode "Studio" (Creator Studio, Settings)** :
- Typographie sans-serif moderne
- Tons plus neutres
- Espacement compact (productivité)
- Pas d'animation superflue
- Look "professional tool"

Les deux modes partagent les mêmes tokens de base (couleurs accent, accent
hover, etc.) mais varient sur la typographie, l'espacement, les animations.

### 16.3 Implémentation

Deux fichiers QSS distincts dérivés des tokens :
- `template_game.qss` → appliqué quand l'utilisateur est sur Hub ou Tabletop
- `template_studio.qss` → appliqué quand il est sur Creator Studio ou Settings

Switch au changement de vue via `MainWindow.show_xxx()`.

### 16.4 Coût

Inclus dans le Pilier 3 et la section 12 (tokens). Surcoût ~3 jours pour
les deux templates.

---

# PARTIE V — RÉDUCTION DES DÉPENDANCES

## 17. Découplage embedding & vector store

### 17.1 Constat

`requirements.txt` actuel inclut :
- `chromadb >= 1.0.0` (~80 MB + dépendances : onnxruntime, posthog, opentelemetry...)
- `sentence-transformers >= 2.2.0` (charge torch ~500 MB)

Pour un utilisateur de KoboldCPP / LM Studio qui n'a aucune utilité pour
torch en local, c'est **800 MB de wheels** dont ~500 MB de torch inutilisé.

### 17.2 Cible

Avec le Pilier 6 (plugins) :
- `chromadb` devient le **plugin `vector_store` par défaut** mais peut être
  remplacé par `sqlite_vec` (≈ 500 KB).
- `sentence-transformers` devient le **plugin `embedding` par défaut** mais
  peut être remplacé par `ollama_embed` (0 MB additionnel) ou `model2vec`
  (~50 MB).

`requirements.txt` minimum :
- PySide6
- httpx
- Pillow

`requirements-recommended.txt` :
- PySide6
- httpx
- Pillow
- chromadb
- sentence-transformers
- google-genai

L'utilisateur choisit son install :
```bash
# Minimal (BYO LLM + embeddings via plugins)
pip install -r requirements.txt

# Full (recommended for most users)
pip install -r requirements-recommended.txt
```

### 17.3 Refactor concret

1. Extraire l'interface `Embedding` dans `axiom/memory.py` (Protocol).
2. Extraire l'interface `VectorStore` idem.
3. `VectorMemory` actuel devient un wrapper qui prend une `VectorStore` +
   une `Embedding` en injection.
4. Les plugins `chromadb_store` + `sentence_transformers_embed` sont des
   **plugins built-in** activés par défaut s'installés.
5. Si aucun embedding/store actif → l'app fonctionne (le RAG est désactivé,
   la narration continue sans mémoire vectorielle). Documenté comme "memoryless
   mode".

### 17.4 Coût

1 semaine (dépend du Pilier 6 être en place).

## 18. Lazy imports

### 18.1 `google-genai` lazy

**Fichier :** `llm_engine/gemini_client.py:23-24`

```python
from google import genai
from google.genai import types as genai_types
```

Charge ~30 MB de grpc + protobuf au démarrage, même si l'utilisateur n'utilise
pas Gemini.

**Fix :** déplacer l'import dans le `__init__` du `GeminiClient`.

```python
class GeminiClient(LLMBackend):
    def __init__(self, api_key, model_name=_DEFAULT_MODEL):
        from google import genai  # lazy
        from google.genai import types as genai_types
        # ...
```

### 18.2 `sentence_transformers` deferred

Déjà partiellement fait via `_EmbeddingSingleton` (`vector_memory.py:35-44`),
mais `debug/startup_check.py:64` force l'import au démarrage.

**Fix :** retirer `sentence_transformers` du check startup (section 3.6).

### 18.3 `chromadb` deferred

Idem : `_ensure_connected` retarde l'import, mais le startup_check le force.

### 18.4 Coût

1 jour total.

## 19. Caching du pip install

Cf. section 3.5.

---

# PARTIE VI — HYGIÈNE & QUALITÉ DE VIE

## 20. Discipline du logger

Cf. section 3.4 — `print()` → `logger`.

Complément :
- Établir des **niveaux clairs** :
  - `DEBUG` : flux d'événements internes
  - `INFO` : événements utilisateur-visibles (session start, save, etc.)
  - `WARNING` : situations dégradées récupérables (LLM lent, hint LLM mal formé)
  - `ERROR` : erreurs nécessitant action utilisateur
  - `CRITICAL` : crashs

- Ajouter un **viewer de logs** dans Settings → Diagnostics → "View recent
  log entries". Permet à l'utilisateur de copier-coller un log pour bug
  report sans aller chercher `~/.cache/AxiomAI/axiom_ai.log`.

- Filter UI : "Show only WARN+" pour ne pas se noyer.

## 21. Tests UI

### 21.1 Constat

`tests/` couvre l'engine (266+ tests) mais quasi rien côté UI :
- `test_chat_buffer.py` : 2 tests sur le JSON fence buffer
- Le reste : 0

### 21.2 Cible

Ajouter une **suite pytest-qt** pour les widgets critiques :
- `test_universe_card.py` : signal emission, retranslate
- `test_entity_editor.py` : add/delete entity, sync stats, collect_data round-trip
- `test_rule_editor.py` : add condition/action, OR/AND switch, collect_data
- `test_lore_book_editor.py` : populate, category switch
- `test_map_editor.py` : add location, drag, connection, collect_data
- `test_chat_display.py` : append_token, JSON fence filtering, variant nav, image inline

Pas besoin de tests UI exhaustifs — focus sur les **round-trips
populate/collect_data** qui sont les points où les bugs se cachent (cf. les
bugs de sync identifiés en Phase 6 du Changelog).

### 21.3 Coût

1.5 semaine pour une couverture raisonnable.

## 22. Documentation modder

### 22.1 Cible

Créer `docs/` à la racine avec :

```
docs/
  00_quickstart.md            ← Install + premier univers en 10 min
  01_universe_format.md       ← Spec complète de Universe-as-Code (Pilier 2)
  02_writing_rules.md         ← Tutoriel sur les rules JSON/TOML
  03_lore_and_rag.md          ← Comment le lore book + RAG marchent
  04_calendar_and_time.md     ← Custom calendars + scheduled events
  05_plugins_overview.md      ← Vue d'ensemble plugins
  06_plugin_authoring.md      ← Tutoriel pour écrire un plugin
  07_plugin_api_reference.md  ← Référence complète de Session API
  08_testing_universes.md     ← Pilier 7, harnais de test
  09_publishing.md            ← Comment publier un univers sur GitHub
  10_advanced/
    01_npc_agents.md
    02_rumor_propagation.md
    03_engine_internals.md
```

Format : Markdown, peut générer un site statique via mkdocs ou similaire.

### 22.2 Coût

2 semaines (en parallèle ou en fin de chantier).

---

# PARTIE VII — ROADMAP

## Ordre conseillé et estimations

### Phase A — Stabilisation (1 semaine)
- Section 1 : Bugs bloquants
- Section 2 : Bugs logiques
- Section 3 : Quick wins perf (3.1, 3.4, 3.5, 3.6)
- Section 4 : Nettoyage code mort

**Livrable :** une codebase saine, sans crash latents, perf de base correcte.

### Phase B — Architecture (8 semaines)
- Pilier 1 — Extraction engine (2 sem)
- Pilier 5 — Temps causal (1 sem)
- Pilier 2 — Universe-as-Code (4 sem)
- Pilier 6 — Plugins (3 sem, peut overlapper avec Pilier 2)

**Livrable :** une architecture qui permet tout le reste, des univers
partageables sur GitHub, un écosystème de plugins amorçable.

### Phase C — Profondeur (6 semaines)
- Pilier 4 — NPC memory + Actor model (3 sem)
- Pilier 7 — Test harness (2 sem)
- Section 17 — Découplage embedding/vector (1 sem)

**Livrable :** Axiom AI fait des choses qu'aucun autre AI RPG ne fait. Tests
de qualité automatisés.

### Phase D — Visuel (8 semaines)
- Pilier 3 — NarrativeView (6 sem)
- Section 12 — Tokens & typo (1 sem, en parallèle)
- Section 13 — Hub refonte (1 sem)
- Section 14 — Creator Studio refonte (2 sem)
- Section 15 — Tabletop topbar/sidebar (1.5 sem)
- Section 16 — Modes Game/Studio (3 j, en parallèle)

**Livrable :** Axiom AI ne ressemble plus à aucune autre app. Identité visuelle
forte, narrative-first.

### Phase E — Polish (2 semaines)
- Section 18 — Lazy imports
- Section 20 — Logger discipline (continu mais finalisé)
- Section 21 — Tests UI
- Section 22 — Documentation modder

**Livrable :** prêt pour une release publique grand public.

### Total estimé : 25 semaines

≈ 6 mois full-time solo. Confortable à 2.

## Découpe alternative — Sprint court

Si tu veux livrer du visible vite avant de t'engager sur 6 mois :

**Sprint 1 — 1 semaine "Fix & shine"**
- Phase A complète
- Section 12 (tokens) MVP
- Section 17 décrit (pas encore implémenté)

**Sprint 2 — 2 semaines "Beauté immédiate"**
- Pilier 3 POC (drop caps + typo + reading mode minimum)
- Section 13 (Hub refonte)

**Sprint 3 — 2 semaines "Cohérence"**
- Pilier 5 (temps)
- Section 14 (Creator Studio refonte)

À ce stade, **5 semaines passées**, l'app est déjà transformée visuellement
et techniquement saine, sans avoir encore engagé les chantiers vraiment
lourds (Engine extraction, Universe-as-Code, Plugins, NPC actors).

Tu peux alors décider si tu continues vers Phase B/C complète, ou si tu fais
release en l'état.

---

# ANNEXES

## Annexe A — Fichier-par-fichier : qu'est-ce qui change

| Fichier actuel | Changement | Phase | Section |
|---|---|---|---|
| `main.py` | Extraire `_DARK_QSS` → tokens.toml | D | 12 |
| `core/arbitrator.py` | N+1 fix, batch events, print→logger, dedup O(N) | A | 3.1, 3.2, 3.4, 2.1 |
| `core/arbitrator.py` | Déplacer vers `axiom/arbitrator.py` | B | 5 |
| `core/arbitrator.py` | Étendre tool_call schema avec elapsed_minutes | B | 6 |
| `core/arbitrator.py` | Per-perspective embedding | C | 9 |
| `core/chronicler.py` | Remplacement par NPCAgent manager | C | 9 |
| `core/chronicler.py` | Déplacer vers `axiom/chronicler.py` | B | 5 |
| `core/config.py` | Split EngineConfig / AppConfig | B | 5 |
| `core/localization.py` | Ajouter `get_translations_dict()` | A | 1.7 |
| `core/time_system.py` | Déplacer vers `axiom/time_system.py` | B | 5 |
| `database/event_sourcing.py` | `append_events_batch` | A | 3.2 |
| `database/event_sourcing.py` | Déplacer vers `axiom/events.py` | B | 5 |
| `database/schema.py` | print→logger, déplacer vers `axiom/schema.py` | A, B | 3.4, 5 |
| `llm_engine/vector_memory.py` | Découpler Embedding/Store via protocols | B/C | 17 |
| `llm_engine/vector_memory.py` | Ajouter `perspective` metadata | C | 9 |
| `llm_engine/gemini_client.py` | Lazy import google.genai | E | 18.1 |
| `llm_engine/prompt_builder.py` | Étendre NARRATIVE_TOOL_CALL_SCHEMA | B | 6 |
| `workers/db_tasks.py` | Supprimer dup `CreatePlayerEntityTask` | A | 1.8 |
| `workers/db_tasks.py` | print→logger | A | 3.4 |
| `workers/db_worker.py` | Renommer `execute_rewind`→`rewind_to_checkpoint` (ou inverse) | A | 1.2 |
| `workers/narrative_worker.py` | Adapter pour utiliser axiom.Session | B | 5 |
| `workers/timekeeper_worker.py` | Réactiver comme fallback | B | 6 |
| `ui/main_window.py` | Fix `findChild(QWidget)` hack | A | 1.3 |
| `ui/main_window.py` | Hub refonte intégration | D | 13 |
| `ui/main_window.py` | Mode Game/Studio switch | D | 16 |
| `ui/hub_view.py` | Refonte complète | D | 13 |
| `ui/tabletop_view.py` | Fix ChroniclerEngine() args | A | 1.1 |
| `ui/tabletop_view.py` | Fix rewind method call | A | 1.2 |
| `ui/tabletop_view.py` | Retirer TimekeeperWorker import inutilisé | A | 1.5 |
| `ui/tabletop_view.py` | Utiliser `result.elapsed_minutes` | B | 6 |
| `ui/tabletop_view.py` | Topbar refonte | D | 15.1 |
| `ui/creator_studio_view.py` | Refonte 9→5 onglets | D | 14 |
| `ui/widgets/chat_display.py` | Remplacement par NarrativeView | D | 11 |
| `ui/widgets/map_editor.py` | Fix "m"→"km" affichage | A | 1.9 |
| `ui/widgets/*` | Migrer setStyleSheet inline → classes QSS | D | 12.4 |
| `debug/startup_check.py` | Retirer sentence_transformers du check | A | 3.6 |
| `debug/test_*.py` | Évaluer / merger / supprimer | A | 1.10, 4 |
| `run.sh` | Marker file pour pip install | A | 3.5 |
| `requirements.txt` | Split minimal/recommended | E | 17 |
| `assets/themes/` | NEW : mocha/parchment/... | D | 12 |
| `docs/` | NEW : doc modder complète | E | 22 |
| `axiom/` (new package) | NEW : engine headless | B | 5 |
| `axiom/plugin_api.py` | NEW : API plugins | B | 8 |
| `axiom/cli/` | NEW : play/compile/test commands | B | 5, 7, 10 |

## Annexe B — Glossaire

- **Arbitrator** : moteur qui valide les state_changes proposés par le LLM
  et applique les rules. Le "firewall déterministe" du Changelog.
- **Chronicler** : agent de simulation du monde hors-écran. Tourne périodiquement.
- **Engine** : tout ce qui n'est pas UI. Devient `axiom-engine` au Pilier 1.
- **Event sourcing** : pattern où tout changement d'état est un event immutable
  loggé, l'état courant étant reconstruit par replay.
- **Hook** : kind de plugin qui s'abonne à des événements lifecycle.
- **Kind (de plugin)** : type de plugin parmi 11 (backend, embedding, tool, hook, etc.)
- **NarrativeView** : custom widget qui remplace ChatDisplayWidget, signature
  visuelle d'Axiom AI.
- **NPCAgent** : remplacement du Chronicler monolithique par un agent par NPC.
- **Perspective** : metadata sur un chunk de mémoire, indiquant qui en est
  témoin / connaisseur.
- **Pilier** : changement architectural majeur. Numérotés P1-P7.
- **Plugin** : extension externe (Python) à Axiom AI, déclarée par manifest.
- **RAG** : Retrieval-Augmented Generation. Le système qui injecte des chunks
  pertinents dans le prompt LLM.
- **Rules Engine** : moteur déterministe qui applique des rules JSON sur les
  stats d'une entité.
- **Save** : état runtime persisté (Event_Log + State_Cache + VectorMemory),
  séparé de la définition d'univers.
- **Session** : la classe haut-niveau de `axiom-engine` qui orchestre un turn.
- **Tool (LLM)** : champ JSON dans la réponse LLM qui demande une action
  validée (state_change, inventory_change, ...). Extensible via plugins kind `tool`.
- **Universe** : définition immuable (entités, rules, lore, locations).
  Distincte des saves.
- **Universe-as-Code** : représentation d'un univers en arborescence de
  fichiers texte versionnable.

## Annexe C — Notes de migration

### C.1 Migration des univers `.db` v1 vers `.axiom` v2 (Universe-as-Code)

L'outil `axiom decompile <my_world.db> <output_dir/>` génère l'arborescence à
partir d'un `.db` existant. Préserve :
- Toutes les entity_ids
- Tous les rule_ids
- Le calendrier
- Le lore book complet
- Les locations et connections
- Les scheduled events
- Les story setup questions

L'utilisateur peut alors :
1. Continuer à utiliser le `.db` direct (compat backward)
2. Ou migrer vers la version texte et recompiler

### C.2 Migration des saves au passage Pilier 5 (temps causal)

Les saves existants ont des Timeline entries avec des `in_game_time` calculés
en `+= 15 min/turn`. Après migration :
- Les saves restent valides
- Mais les nouveaux turns auront un `elapsed_minutes` variable
- Le `last_chronicle_time` est initialisé à `MAX(in_game_time)` du save pour
  ne pas re-trigger immédiatement le Chronicler

### C.3 Migration de l'embedding/vector store (Section 17)

Les saves existants ont un dossier `~/AxiomAI/vector/<save_id>/` géré par
ChromaDB. Si l'utilisateur switch sur `sqlite_vec` :
- Outil `axiom migrate-vector <save_id> --from chromadb --to sqlite_vec`
- Lit tous les chunks chromadb, ré-embed avec le nouveau modèle, insère dans
  la nouvelle store
- Conserve les anciens embeddings en backup `<save_id>.chromadb-backup/`

### C.4 Migration vers plugin-based backends

Le backend Gemini hardcoded devient un plugin built-in. Les utilisateurs avec
une config existante (`config.llm_backend = "gemini"`) sont automatiquement
migrés vers le plugin Gemini sans intervention.

---

## Conclusion

Ce document décrit **25 semaines de travail** pour transformer Axiom AI d'un
projet ambitieux mais isolé en :
1. Un moteur de RPG narratif sain et performant
2. Une plateforme moddable avec écosystème
3. Une expérience visuelle signature
4. Un outil pour créateurs et joueurs avec workflow propre
5. Une base pour une vraie communauté

Chaque pilier est indépendant et délivre de la valeur. La roadmap permet de
moduler l'engagement selon le temps et l'énergie disponibles.

**Le prochain pas concret :** commencer par la Phase A (1 semaine de
stabilisation). Personne ne devrait construire le Pilier 4 (NPC actors) sur
une base qui crashe au turn 50 à cause du bug `ChroniclerEngine`.

Bon courage. Ça vaut le coup.
