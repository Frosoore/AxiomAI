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

### État de la codebase & journal d'avancement

> **Ré-édition du 2026-06-23.** Ce document a été élagué : les sections déjà
> livrées (Phase A complète, Pilier 1, Pilier 5, Pilier 2 + portage moteur) sont
> remplacées par une ligne de log « ✅ FAIT ». Le détail de chaque étape livrée
> vit dans `maintenance/README.md` (index) et `maintenance/DONE.md`. De nouvelles
> sections, issues de l'**audit intégral de `axiom/arbitrator.py`** et de l'**audit
> concurrentiel** du 2026-06-23, ont été ajoutées en **PARTIE VIII**.

**Livré depuis la v1.0 du document (résumé) :**

- ✅ **Phase A — Stabilisation** (§1 bugs bloquants, §2 bugs logiques, §3 optimisations, §4 code mort) — *terminé* (A1→A5).
- ✅ **Pilier 1 — Moteur headless `axiom/`** (§5) + **publié sur PyPI** (`pip install axiomai-engine`).
- ✅ **Pilier 5 — Temps causal** (§6) — Timekeeper + Chronicler en minutes in-game.
- ✅ **Pilier 2 — Universe-as-Code** (§7) + portage moteur complet (B3/B4), CLI `axiom`, saves séparées `.axiomsave`.
- ✅ **Hors roadmap initiale** : chantier mémoire « Hindsight » (faits / croyances / mental-models, togglables), providers cloud (Gemini / Claude / OpenAI / Fireworks / …), génération d'images (SD / ComfyUI / Gemini), i18n 10 langues, doc Sphinx + doc intégrée, préparation bêta (univers Myria, clés intégrées, diagnostic).

**Restant à faire (cœur de ce document) :** Pilier 6 (plugins, §8), Pilier 4 (NPC memory + Actor Model, §9), Pilier 7 (harnais de test univers, §10), toute la Phase D visuelle (§11→16), réduction des dépendances (§17→19), hygiène/QA (§20→22), **et la PARTIE VIII** (fiabilité Arbitrator + gouvernance des coûts + veille concurrentielle).

---

# PARTIE I — STABILISATION (Phase A) — ✅ FAIT

> Livré (A1→A5). Couvrait : §1 bugs bloquants, §2 bugs logiques, §3 optimisations
> chirurgicales, §4 nettoyage du code mort. Détail : `maintenance/README.md` /
> `maintenance/DONE.md`.

---

# PARTIE II — ARCHITECTURE (Phase B)

Une fois la base saine, on attaque les changements structurels. **Durée
estimée : 6 à 8 semaines.**

## 5. Pilier 1 — Extraction `axiom-engine` headless — ✅ FAIT

> Moteur extrait dans `axiom/` (zéro Qt), API publique `Session` / `Universe`,
> CLI `axiom`, **publié sur PyPI** (`axiomai-engine`). Détail : `maintenance/README.md`.

## 6. Pilier 5 — Le Temps comme substrat causal — ✅ FAIT

> Timekeeper (estimation de durée par action, désactivable), horloge in-game en
> minutes, Chronicler paginé en minutes, une ligne Timeline par tour. Détail : DONE.md.

## 7. Pilier 2 — Universe-as-Code — ✅ FAIT

> Univers = arborescence texte TOML/MD versionnable ; `.db` = cache compilé ; saves
> séparées (`.axiomsave`). compile / decompile / pack / import / dev + portage moteur
> complet (B3/B4). Détail : `maintenance/README.md`.

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

> **MAJ 2026-06-23.** Phase A ✅ FAIT. Phase B : Piliers 1/5/2 ✅ FAITS, reste
> Pilier 6 (plugins). Phase C : tout reste à faire. Nouvelle **Phase F** ajoutée
> (PARTIE VIII : fiabilité Arbitrator + coûts + veille).

### Phase A — Stabilisation (1 semaine) — ✅ FAIT
- Section 1 : Bugs bloquants
- Section 2 : Bugs logiques
- Section 3 : Quick wins perf (3.1, 3.4, 3.5, 3.6)
- Section 4 : Nettoyage code mort

**Livrable :** une codebase saine, sans crash latents, perf de base correcte. ✅

### Phase B — Architecture (8 semaines) — 🔄 Piliers 1/5/2 ✅, reste Pilier 6
- Pilier 1 — Extraction engine (2 sem) — ✅ FAIT (+ PyPI)
- Pilier 5 — Temps causal (1 sem) — ✅ FAIT
- Pilier 2 — Universe-as-Code (4 sem) — ✅ FAIT (+ portage moteur complet)
- Pilier 6 — Plugins (3 sem, peut overlapper avec Pilier 2) — ⏳ à faire

**Livrable :** une architecture qui permet tout le reste, des univers
partageables sur GitHub, un écosystème de plugins amorçable.

### Phase C — Profondeur (6 semaines) — ⏳ à faire
- Pilier 4 — NPC memory + Actor model (3 sem) — *mémoire perspectiviste partiellement couverte par le chantier Hindsight ; l'Actor Model autonome reste à faire*
- Pilier 7 — Test harness (2 sem) — *instrument de mesure de la Phase F (§23)*
- Section 17 — Découplage embedding/vector (1 sem)

**Livrable :** Axiom AI fait des choses qu'aucun autre AI RPG ne fait. Tests
de qualité automatisés.

### Phase F — Fiabilité & coûts (PARTIE VIII, ~3 semaines) — ⏳ à faire *(NOUVEAU)*
- Pilier 8 — Fiabilité de l'Arbitrator (§23) : durcissement déterministe gratuit
  (sortie structurée, bornes/légalité, fix plot-armor), détecteur de divergence,
  option « résoudre puis raconter » (2 sem).
- Section 24 — Gouvernance des coûts : flags + presets de budget + estimateur (3 j).
- Section 25 — Veille concurrentielle : briefs d'agents + consolidation `PENDING.md`
  (transverse, en continu).

**Livrable :** le « pare-feu déterministe » tient sa promesse (cohérence
prose↔état), et l'utilisateur maîtrise sa facture LLM. Idéalement à séquencer
**avec/avant** Pilier 7 (qui mesure §23) et **avant** Pilier 4 (qui multiplie les
appels LLM, donc dépend de §24).

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

### Estimé initial : 25 semaines — Phases A + B (hors Pilier 6) livrées

≈ 6 mois full-time solo à l'origine. **Restant estimé (2026-06-23)** : Pilier 6
(~3 sem) + Phase C (~6 sem) + **Phase F (~3 sem)** + Phase D (~8 sem) + Phase E
(~2 sem) ≈ **22 semaines**, hors veille concurrentielle (continu).

## Séquencement conseillé du restant

L'ordre n'est plus « du début », puisque A et l'essentiel de B sont faits. Priorité
suggérée, des fondations vers le visible :

1. **Phase F — Fiabilité & coûts** *(en premier)* : §23 corrige le cœur de l'argument
   produit (déterminisme réel), §24 borne les coûts **avant** d'ajouter des appels LLM
   (Pilier 4). Le socle gratuit de §23.2 est rentable immédiatement.
2. **Pilier 7 (Phase C)** : juste après / en parallèle de §23, car il **mesure** la
   divergence prose↔état et donne une CI pour les univers communautaires.
3. **Pilier 6 (plugins)** : débloque l'extensibilité (backends, kinds) et l'écosystème.
4. **Pilier 4 (Actor Model)** : la profondeur différenciante (émergence NPC), une fois
   les coûts gouvernés (§24).
5. **Phase D (visuel)** puis **Phase E (polish)** : identité visuelle et release.

La **veille concurrentielle (§25)** tourne en continu et alimente `PENDING.md` au fil
de l'eau, indépendamment de l'ordre ci-dessus.

---

# PARTIE VIII — FIABILITÉ & COÛTS (audit du 2026-06-23)

> Issue de deux audits menés le 2026-06-23 : (1) lecture intégrale de
> `axiom/arbitrator.py` (1466 lignes), (2) veille concurrentielle (IVIE/PAYADOR,
> RPGBench, TALES, Generative Agents, Hindsight, Ian Bicking « Intra »…). Cette
> partie ajoute trois chantiers : durcir l'Arbitrator (§23), rendre les coûts
> gouvernables (§24), industrialiser la veille (§25).

## 23. Pilier 8 — Fiabilité de l'Arbitrator (cohérence prose↔état) 🏗

### 23.1 Constat (vérifié dans le code)

Pipeline réel d'un tour (`ArbitratorEngine.process_turn`) : le LLM produit **en un
seul jet** la prose (`narrative_text`) **et** un `tool_call` JSON
(`state_changes`, `inventory_changes`, `game_state_tag`, `scene_pace`). La prose est
**streamée au joueur, embeddée en mémoire et loggée comme event canonique** ; seuls
les `state_changes`/`inventory_changes` passent par la validation. Un changement
rejeté ne corrige **rien sur le tour courant** : il pose un `[NARRATOR HINT: …]`
injecté au **tour suivant**, puis effacé.

Conséquences (toutes confirmées dans le code) :

- **❶ La prose n'est jamais validée contre l'état.** Aucun check
  `narrative_text` ↔ `state_changes`. La narration est committée **avant** et
  **indépendamment** de toute validation. Le README (« *every narrative turn is
  validated … before being committed* ») est donc trompeur : seuls les deltas
  structurés sont validés, et a posteriori.
- **❷ Le firewall est en aval de la déclaration volontaire du LLM.**
  `state_changes = tool_call.get("state_changes", [])`. Si le LLM raconte « tu
  encaisses 10 dégâts » sans émettre de `state_change`, rien ne bouge → **drift
  silencieux**.
- **❸ Aucun décodage contraint.** Le `tool_call` est extrait par **regex** d'un bloc
  ```` ```json ```` dans le flux brut. JSON malformé/absent → zéro changement,
  silencieusement. Fragile surtout sur petits modèles locaux.
- **❹ Validation étroite.** `_validate_change` ne vérifie que : entité existe, stat ∈
  `Stat_Definitions`, **non-négativité** d'une ressource numérique. Pas de **bornes
  hautes** (`Health = 9999` accepté), pas de **légalité spatiale**
  (`_get_travel_distance` annote la timeline mais ne **rejette** jamais un téléport),
  et **toute valeur non-numérique passe** (« *always valid for the cache* »).
- **❺ Bug probable — « plot armor » Companion inopérant.** Quand le héros passerait
  sous 0, `_validate_change` retourne `(True, "")` → le delta négatif est **appliqué
  tel quel**. Le commentaire promet un clamp à 0 que le code n'implémente pas. *À
  corriger / vérifier (test associé).*

Ce qui, à l'inverse, est solidement déterministe et **ne doit pas être touché** :
`RulesEngine` (cascades de règles créateur, chaînage borné), event-sourcing +
reconstruction (batch transactionnel, `update_state_cache`), snapshots,
non-négativité des ressources, inventaire.

### 23.2 Cible — durcissement classé par coût

Principe directeur (cf. §24) : **le durcissement déterministe gratuit est ON et
NON-togglable** (c'est le socle de l'argument « moteur déterministe ») ; seuls les
mécanismes à appel LLM supplémentaire sont OFF par défaut et togglables.

| Mesure | Corrige | Coût | Défaut |
|---|---|---|---|
| **Sortie structurée** (`response_schema` Gemini ; *grammars* llama.cpp/Outlines en local) — remplace le parsing regex | ❸ | **gratuit** (gain net : zéro JSON cassé) | **ON, non-togglable** |
| **Bornes min/max + valeurs énumérées** déclarées dans `Stat_Definitions` ; rejet ou clamp | ❹ | gratuit | **ON, non-togglable** |
| **Légalité spatiale** : `Location` ∈ lieux connus, adjacence optionnelle via `Location_Connections` | ❹ | gratuit | **ON, non-togglable** |
| **Validation des valeurs non-numériques** (énums, lieux) au lieu de tout accepter | ❹ | gratuit | **ON, non-togglable** |
| **Fix plot-armor** (clamp à 0 en mode Companion) | ❺ | gratuit (bug) | **ON, non-togglable** |
| **Détecteur de divergence prose↔état** (scan heuristique du texte, zéro appel LLM) | ❶❷ | très bas | **ON, togglable** |
| **« Résoudre puis raconter »** (2 phases LLM) | ❶❷ | **élevé** (+1 appel/tour) | **OFF, togglable** |
| **Auditeur LLM** (passe de vérification dédiée) | ❶❷ | élevé (+1 appel/tour) | **OFF, togglable** |

### 23.3 « Résoudre puis raconter » (option *Fidélité*)

Aujourd'hui le LLM raconte **et** déclare en même temps ; on valide après. C'est la
cause-racine de la divergence ❶/❷. Le correctif structurel sépare les deux (comme
IVIE/PAYADOR) :

1. **Phase intention** : le LLM propose l'action + les `state_changes` voulus (pas de
   prose finale).
2. **Résolution déterministe** : on valide/applique (§23.2), on calcule le résultat
   réel (succès/échec/clamp).
3. **Phase narration** : le LLM rédige la prose **conditionnée sur le résultat
   validé** — il ne peut plus « mentir » sur ce qui s'est passé.

Coût : +1 appel LLM/tour (même ordre que le Timekeeper, déjà désactivable). → flag
`resolve_then_narrate_enabled`, OFF par défaut, inclus dans le preset *Fidélité*.

### 23.4 Détecteur de divergence (option *Équilibrée*, bon marché)

Sans 2ᵉ appel : après parsing, scanner `narrative_text` pour des **affirmations
chiffrées / d'inventaire** (« +N or », « tu perds X PV », « tu trouves <item> ») qui
**n'ont pas** de `state_change`/`inventory_change` correspondant. En cas d'écart :
soit re-prompt léger, soit marquer le tour `unreliable` (exploitable par le harnais
de test §10 et l'UI). Heuristique imparfaite mais zéro token. → flag
`divergence_detector_enabled`, ON par défaut, togglable.

### 23.5 Plan d'implémentation (ordre conseillé)

1. Sortie structurée + suppression du parsing regex (socle de tout le reste).
2. Bornes/énums/légalité dans `Stat_Definitions` + validation des valeurs.
3. Fix plot-armor + test de non-régression.
4. Détecteur de divergence (heuristique).
5. « Résoudre puis raconter » derrière son flag.
6. Brancher le tout sur le harnais de test (§10) pour **mesurer** le taux de
   divergence et sa dégradation sur parties longues (cf. TALES).

### 23.6 Liens

§10 (Pilier 7) **mesure** ce que §23 corrige ; §24 régit les flags introduits ici.
Inspirations : IVIE/PAYADOR (séparation créa/validation), TALES (dégradation du
grounding), RPGBench (vérification structurelle).

## 24. Gouvernance des coûts — tout togglable + presets de budget 🏗

### 24.1 Constat

Le moteur a déjà des flags de coût **ad hoc** (`timekeeper_enabled`,
`memory_mode_is_living`, `memory_beliefs_active`, `memory_mental_models_active`,
`memory_prompt_cache_enabled`). Avec §23 et les chantiers futurs (Pilier 4 acteurs
autonomes = appels LLM par NPC), le nombre d'appels LLM optionnels par tour va
exploser. Sans cadre, l'utilisateur (souvent néophyte) ne peut ni comprendre ni
maîtriser sa facture.

### 24.2 Cible — chaque appel LLM/outil optionnel = un flag + un coût documenté

Tout mécanisme qui ajoute un appel LLM, un embedding, ou un outil coûteux **doit** :
exposer un flag de config, déclarer son coût (ordre de grandeur en tokens/tour),
et **dégrader proprement** quand il est OFF (jamais de crash, juste « plus grossier »).

### 24.3 Presets de budget (au-dessus des flags)

Ne **pas** exposer 15 interrupteurs à un néophyte. Trois presets qui regroupent les
flags, sur **un seul axe que l'utilisateur comprend (le budget)** :

- **Économe** : tout appel LLM secondaire OFF (Timekeeper off → temps par pace, pas
  de résolution 2 phases, pas d'auditeur, mémoire « lite », pas d'acteurs NPC).
  Reste : le socle déterministe gratuit (§23.2).
- **Équilibré** *(défaut)* : détecteur de divergence ON, Timekeeper ON, mémoire
  vivante ON ; pas de 2ᵉ appel narratif coûteux.
- **Fidélité** : « résoudre puis raconter » + auditeur + acteurs NPC + mémoire
  complète.

Plus un **mode avancé** qui déverrouille les flags individuels pour les power-users.

### 24.4 Invariant — le socle déterministe gratuit reste NON-togglable

Les durcissements gratuits de §23.2 (sortie structurée, bornes, légalité, fix
plot-armor) ne sont **pas** derrière un flag : ce sont des corrections de
sécurité/correction, pas des options de confort. Les rendre optionnels reviendrait à
proposer « désactiver le pare-feu déterministe », ce qui viderait l'argument produit.

### 24.5 Surface UI

Settings → **Budget** : sélecteur de preset + (mode avancé) liste des flags avec, en
regard, le coût estimé. Idéalement un **estimateur « coût par tour »** recalculé
selon les flags actifs et le provider/modèle choisi.

### 24.6 Registre des coûts (à maintenir)

Une table unique `appel | quand | tokens approx | flag | preset minimal` —
documentée et testée — pour que l'estimateur et la doc restent synchronisés avec le
code.

## 25. Veille & « vol » concurrentiel (chantier transverse) 🏗

### 25.1 Constat

Aucun pilier d'Axiom n'est unique pris isolément (chaque brique a de l'art
antérieur : neuro-symbolique IF, generative agents, event sourcing, mémoire d'agent,
discrete-event sim). **Le moat = l'intégration complète, local-first, packagée.** Il
faut donc étudier méthodiquement les voisins pour leur prendre leurs meilleures idées
et repérer leurs manques.

### 25.2 Carte des cibles par domaine

- **A — Moteurs déterministes / neuro-symboliques** : IVIE/PAYADOR
  (arxiv 2606.13348), G-KMS (doi 10.3390/systems14020175), RPGBench
  (arxiv 2502.00595), DM Quarkus/LangChain4j, VirtualGameMaster.
- **B — Produits grand public** : Friends & Fables, Hidden Door (story-thread
  templates = garde-fou narratif), Questsmith (mémoire), NovelAI, AI Dungeon,
  SillyTavern/RisuAI.
- **C — Mémoire d'agent** : Hindsight (arxiv 2512.12818 ; déjà cloné — viser
  *reflect* + citations), Mem0, Zep, Memvid.
- **D — Agents génératifs / simulation de monde** : Generative Agents/Smallville
  (arxiv 2304.03442), Affordable Generative Agents, Character-LLM, RELATE-Sim.
- **E — Branches / timeline / event-sourcing** : WHAT-IF (arxiv 2412.10582),
  Narrative Studio (arxiv 2504.02426), Elsewise (arxiv 2601.15295).
- **F — State-tracking / grounding / world models** : TALES (arxiv 2504.14128),
  State Tracking (arxiv 2511.10457), R-WoM (arxiv 2510.11892),
  awesome-LLM-game-agent-papers (survey).
- **G — Temps in-game / discrete-event sim** : Ian Bicking « Intra » (design
  quasi-identique au Timekeeper, conçu indépendamment — à lire).
- **H — Génération contrainte** (techniques pour §23.2) : Outlines, llama.cpp
  grammars, Gemini `response_schema`.

### 25.3 Méthode

Un agent par cible. Brief type : « Étudie [cible]. Sors : (1) ce qu'ils font mieux
qu'Axiom sur [domaine], (2) la technique précise réutilisable, (3) ce qui leur manque
qu'Axiom a déjà. » Consolider les trouvailles en tickets `PENDING.md`.

### 25.4 Branchements vers les piliers existants

- **Domaine D → Pilier 4 (§9)** : l'Actor Model autonome = exactement Generative
  Agents (émergence sociale inter-NPC, que les *produits* commerciaux n'ont pas).
- **Domaine F → Pilier 7 (§10) + §23** : RPGBench/TALES = la métrique de grounding à
  adopter ; le harnais de test devient l'instrument de mesure de §23.
- **Domaine C → mémoire** : ajouter à la mémoire Hindsight déjà en place la
  **traçabilité/citations** (provenance des faits/croyances).
- **Domaine B (Hidden Door) → §23** : « story-thread templates » = garde-fou de
  cohérence *narrative*, complément de ce que l'Arbitrator (état) ne couvre pas.

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
| `core/config.py` | ~~Split EngineConfig / AppConfig~~ — abandonné (TICKET-004, cf. §5.3 Étape 3) | B | 5 |
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
