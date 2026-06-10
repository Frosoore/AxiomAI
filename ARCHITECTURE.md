# ARCHITECTURE — Axiom AI

> **À lire avant d'ajouter ou de modifier une feature** (humain ou assistant IA / Gemini CLI).
> Ce document explique **où va le code**, **les règles à respecter** et **pourquoi**. Le respecter
> évite que la logique de jeu se disperse dans l'UI et garde le moteur réutilisable.

---

## TL;DR (les 5 règles d'or)

1. **La logique de jeu vit dans `axiom/`** (le moteur). Pas dans `ui/`, pas dans `workers/`.
2. **`axiom/` est headless : il ne doit JAMAIS importer Qt (PySide6) ni `ui/` ni `workers/`.**
3. **La dépendance est à sens unique : `ui/` et `workers/` importent `axiom/`, jamais l'inverse.**
4. **Une seule source de vérité par feature.** Un worker Qt est une **coquille fine** qui lance la
   logique du moteur dans un thread et relaie sa progression — il ne contient pas la logique lui-même.
5. **Pour utiliser un helper côté moteur, on le DÉPLACE dans `axiom/`** (on ne fait pas
   `from workers... import` depuis `axiom/`).

Vérifier qu'on n'a rien cassé :
```bash
.venv/bin/python -m pytest tests/test_engine_headless.py tests/test_cli_play.py -q
.venv/bin/python debug/startup_check.py
```

---

## Les couches

```
axiom/        ← LE MOTEUR. Headless, zéro Qt. Toute la logique de jeu/LLM/DB.
                Réutilisable par n'importe quel frontend (GUI, CLI, serveur, notebook).
ui/           ← L'INTERFACE Qt. Widgets, dialogues, vues, style. Présentation uniquement.
workers/      ← Le PONT threading Qt. QThread/QRunnable qui exécutent la logique du
                moteur hors du thread principal et relaient la progression en signaux Qt.
core/         ← Reliquat applicatif : st_parser.py (parsing carte SillyTavern),
                multiplayer_queue.py (encore couplé Qt). NON-moteur.
database/     ← backup_manager.py (sauvegardes auto). NON-moteur.
main.py       ← Point d'entrée GUI.
```

Le moteur s'utilise **sans Qt** via l'API publique `Session` :
```bash
python -m axiom.cli play <univers.axiom>     # text-adventure terminal
```
```python
from axiom import Session, Universe
from axiom.config import load_config, build_llm_from_config
sess = Session("univers.axiom", save_id, llm=build_llm_from_config(load_config()))
sess.take_turn("J'ouvre la porte.", on_token=print)   # streaming
```

---

## Comment marche un tour (le pipeline)

`Session.take_turn(...)` est **la seule « machine à jouer un tour »**, partagée par le GUI et le CLI :

1. reconstruit l'historique depuis l'`Event_Log` (source canonique) ;
2. (mode Companion) décide l'action du héros ;
3. `Arbitrator.process_turn` : interroge la mémoire vectorielle (RAG), construit le prompt,
   **streame** la réponse du LLM, applique les règles + modifiers, écrit les events, embed la narration ;
4. renvoie un `ArbitratorResult`.

Côté GUI, `workers/narrative_worker.py` (`NarrativeWorker`) **enveloppe** cet appel dans un QThread.
Côté CLI, `axiom/cli/play.py` l'appelle directement. **Même code moteur**, deux frontends.

### Progression : callbacks, pas signaux Qt

Le moteur ne connaît pas Qt. Il expose des **callbacks** (`on_token`, `on_status`,
`on_hero_decision`). C'est le worker qui les **mappe vers des signaux Qt**. C'est le patron à suivre
pour toute logique longue.

---

## Où mettre une nouvelle feature ? (arbre de décision)

- **Logique de jeu / simulation / appel LLM / accès DB ?**
  → Implémente-la dans `axiom/` (méthode sur `Session`, ou nouveau module `axiom/xxx.py`).
  → Si elle est longue/bloquante et appelée par le GUI, ajoute un **worker-coquille** dans `workers/`
    qui la lance dans un QThread et relaie la progression (callbacks → signaux).
  → Branche l'UI dans `ui/` (widgets + connexions de signaux).

- **Pure présentation (widget, dialogue, style, layout) ?**
  → `ui/` uniquement. Pas de logique de jeu dedans.

### Exemple — le patron worker-coquille (à copier)

```python
# axiom/  : la logique, headless, testable, callbacks de progression
class Session:
    def do_something(self, arg, *, on_status=None, on_token=None):
        if on_status: on_status("Travail en cours…")
        ...  # LLM / DB / règles
        return result

# workers/  : coquille Qt fine — threade + relaie, AUCUNE logique métier
class SomethingWorker(QThread):
    status_update = Signal(str)
    token_received = Signal(str)
    done = Signal(object)
    def __init__(self, session, arg): super().__init__(); self._s, self._a = session, arg
    def run(self):
        res = self._s.do_something(self._a,
                                   on_status=self.status_update.emit,
                                   on_token=self.token_received.emit)
        self.done.emit(res)
```
Modèles existants à imiter : `workers/narrative_worker.py`, `workers/vector_worker.py`.

---

## ⚠️ Code encore NON migré dans le moteur (à terme, à porter dans `axiom/`)

Seul le **cœur de simulation + la boucle de tour** est dans `axiom/`. Ces features-là contiennent
encore de la logique **côté app** (Qt). **Quand tu touches l'une d'elles, l'idéal est d'en porter la
logique dans `axiom/`** (patron coquille ci-dessus) plutôt que d'en rajouter dans le worker :

> **🔴 IMPÉRATIF : cette table doit rester à jour.** C'est la source de vérité de ce qui reste à
> migrer. **Dès que tu portes une feature dans `axiom/`, retire sa ligne ici** (et inversement, si tu
> ajoutes une nouvelle logique côté app en attendant de la porter, ajoute-la). Une table périmée
> envoie le prochain dev (ou Gemini CLI) porter du code déjà porté, ou ignorer du code à porter —
> c'est exactement le désordre que ce document existe pour éviter. Mettre la table à jour fait partie
> de la migration, ce n'est pas optionnel.

| Feature (logique encore côté app)            | Fichier                              | Destination moteur visée |
|----------------------------------------------|--------------------------------------|--------------------------|
| *(vide — tout est porté au 2026-06-10, étape B4)* | | |

Dernier lot porté (B4) : création entité joueur → `axiom/db_helpers.py::create_player_entity`,
régénération de variante → `axiom/regenerate.py` (+ méthode `Session.regenerate_variant`),
Mini-Dico → `axiom/mini_dico.py`, file multijoueur → `axiom/multiplayer.py::ActionQueue`.
`workers/chronicler_worker.py` (coquille morte, jamais instancié — le Chronicler tourne dans
le moteur depuis le Pilier 5) a été **supprimé** le 2026-06-10 (feu vert utilisateur).

(Les autres `*Task` de `workers/db_tasks.py` qui ne font que **lire** la DB s'appuient déjà sur
`axiom/db_helpers.py` / `axiom/events.py` — ce ne sont pas de la logique à porter.)

---

## Carte des emplacements (ancien → actuel)

Les anciens modules `core/`, `database/`, `llm_engine/` du moteur ont été **supprimés** : tout est
sous `axiom/`. Si tu cherches un module moteur :

| Tu cherches…            | C'est maintenant…              |
|-------------------------|--------------------------------|
| `core.arbitrator`       | `axiom.arbitrator`             |
| `core.chronicler`       | `axiom.chronicler`             |
| `core.rules_engine`     | `axiom.rules`                  |
| `core.time_system`      | `axiom.time_system`            |
| `core.config`           | `axiom.config`                 |
| `core.paths`            | `axiom.paths`                  |
| `core.logger`           | `axiom.logger`                 |
| `core.localization`     | `axiom.localization`           |
| `database.schema`       | `axiom.schema`                 |
| `database.event_sourcing` | `axiom.events`               |
| `database.checkpoint`   | `axiom.checkpoint`             |
| `database.modifier_processor` | `axiom.modifiers`        |
| `database.presets`      | `axiom.presets`                |
| `llm_engine.base`       | `axiom.backends.base`          |
| `llm_engine.gemini_client` | `axiom.backends.gemini`     |
| `llm_engine.ollama_client` | `axiom.backends.ollama`     |
| `llm_engine.universal_client` | `axiom.backends.universal` |
| `llm_engine.vector_memory` | `axiom.memory`              |
| `llm_engine.prompt_builder` | `axiom.prompts`            |
| `workers.db_helpers`    | `axiom.db_helpers`             |

---

## Pourquoi tout ça ?

- **Réutilisable** : le moteur tourne en GUI, en CLI (`axiom play`), et demain en serveur/web ou en
  notebook — même code, sans Qt.
- **Testable** : pas de `QApplication`, les tests moteur sont rapides et déterministes.
- **Cleanup pas cher** : tant que la logique reste dans `axiom/` (et pas éparpillée dans l'UI),
  reprendre/refondre/déplacer une feature est trivial.
- **Distribution (plus tard)** : à terme `pip install axiom-engine`. **Pas maintenant** — on reste en
  **mono-repo** (un seul dépôt) tant que le projet évolue à plusieurs. Ne crée pas de second package
  ni de `pyproject.toml` de split.

## Ce qu'il NE faut PAS faire

- ❌ Mettre de la logique LLM/DB/règles dans un worker ou un widget « parce que c'est plus rapide ».
- ❌ `from workers... import` ou `from ui... import` depuis `axiom/` (casse le headless — un test le détecte).
- ❌ Réimplémenter dans un worker une logique déjà dans le moteur (duplication = drift).
- ❌ Importer Qt dans `axiom/`.
- ❌ Recréer `core/arbitrator.py` & co : ils ont déménagé sous `axiom/` (cf. table).
