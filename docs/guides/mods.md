# The Modding System (`.axmod`)

*[Lire ce guide en Français](mods.fr.md)*

Axiom AI adopts an **extensible micro-kernel architecture** (`axiomai-engine 1.0.0`): the base engine carries zero hardcoded tabletop RPG business logic. All gameplay mechanics, narrative orchestration, cognitive memory, AI inference backends, and user interfaces are packaged as modular **mods** using the `.axmod` archive format.

This guide provides a comprehensive reference on the architecture, system topology, directory of 12 official mods, authoring workflow, and compliance metrics.

---

## 1. Fundamental Vision & Architectural Promises

The modding system fulfills three core founding promises (§1.2):

1. **Versatility without Bloat:** The core (`axiom/`) contains zero RPG business logic, no hardcoded prompts, and no undeclared heavy third-party dependencies.
2. **Plug and Play, including for an LLM:** Scaffolding (`scaffold`), testing harness (`tester`), live hot-reload (`dev`), and the LLM creator (`llm_creator`) allow generating sandbox-tested and verified extensions with explicit human-readable diffs.
3. **Reversibility and Simplicity:** All registrations go through `ModContext`; disabling a mod restores the prior state with zero memory leaks or database corruption.

---

## 2. Mod System Architecture Map

```
                     ┌──────────────────────────────────────────────┐
                     │          Remote Store / JSON Index           │
                     │         (axiom mods search / install)        │
                     └──────────────────────┬───────────────────────┘
                                            │ SHA-256 Hash
                                            ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                             MOD ECOSYSTEM (.axmod)                               │
├──────────────────────┬─────────────────────────────┬─────────────────────────────┤
│     WORLD MODEL      │       TURN PIPELINE         │           MEMORY            │
│     axiom.world      │        axiom.turn           │    axiom.rag (ChromaDB)     │
│  (Stats, Entities)   │    (Engine Fabric API)      │ axiom.living_memory (Facts) │
├──────────────────────┼─────────────────────────────┼─────────────────────────────┤
│    GAME MECHANICS    │     PROVIDERS & ART         │         INTERFACES          │
│      axiom.time      │       axiom.providers       │        axiom.ui.web         │
│   axiom.inventory    │     axiom.illustrations     │        axiom.ui.qt          │
│  core.stat_dynamics  │    (Gemini, Ollama, SD)     │         axiom.cli           │
└───────────┬──────────┴──────────────┬──────────────┴──────────────┬──────────────┘
            │ Hooks                   │ Slots (Collect, Chain, Excl)│ Patches (@patchable)
            ▼                         ▼                             ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                            MICRO-KERNEL (axiomai-engine 1.0.0)                    │
├──────────────────────────────────────────────────────────────────────────────────┤
│ • Loader & DAG Resolver (Topology, Conflicts, User ordering)                     │
│ • Central Registry (Hooks, Typed Slots, Inter-mod Services)                      │
│ • Execution Bus & Step Freezing (step_patch_freeze, KernelStepContext)           │
│ • Transactional Persistence (TurnWriteBatch, Session Epochs)                     │
│ • Declarative Save Registry (EVENTS, STEP_KEYED, VERSIONED_KV, CUSTOM)           │
│ • CLI & Safe Mode (Native headless --safe-mode)                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Directory of the 12 Extracted Official Mods

| Mod ID | Role & Responsibility | Key Anchor Points | Persistence Policy |
| --- | --- | --- | --- |
| **`axiom.world`** | Entities, base stats, RulesEngine logic, and spatial location graph. | Hooks `gather_context`, `arbitrate_mutations`; Slot `entity_types`. | `versioned_kv` |
| **`axiom.turn`** | Narrative pipeline, correction loop, and tool-call routing. | Hook `execute_step`; Slots `prompt_sections`, `output_fields`, `stream_filter`, `final_text_filter`, `llm_backend`. | `events` (`Event_Log`) |
| **`core.stat_dynamics`** | Passive temporal evolution, rest, fatigue, and gauge decay. | Hooks `arbitrate_stats`, `after_step`. | `step_keyed_table` (`Modifier_Snapshots`) |
| **`axiom.time`** | Diegetic clock, Timekeeper, Timeline, and off-screen Chronicler. | Hook `after_step`; Service `time`; Slot `output_fields` (`time_elapsed_minutes`). | `step_keyed_table` (`Timeline`, `Scheduled_Events`) |
| **`axiom.inventory`** | Nested item and container tree (maximum depth 5). | Service `inventory`; Slot `output_fields` (`inventory_changes`). | `step_keyed_table` (`Inventory_Snapshots`) |
| **`axiom.rag`** | Local vector memory backed by ChromaDB and Sentence-Transformers. | Hook `after_step`; Slot `prompt_sections`; Service `rag`. | `custom` (surgical vector rollback) |
| **`axiom.living_memory`** | Symbolic distillation of facts, beliefs, and entity mental models. | Hook `after_step` (epoch guard); Service `living_memory`. | `step_keyed_table` (`Facts`, `Observations`, `Mental_Models`) |
| **`axiom.providers`** | Inference drivers (Gemini, Ollama, OpenAI-compatible) & connectivity tests. | Slot `axiom.turn:llm_backend`; Open slot `axiom.providers:drivers`. | None (stateless) |
| **`axiom.illustrations`** | Per-turn visual generation (Stable Diffusion / ComfyUI). | Hook `after_step` (post-commit callback); Service `illustrations`. | `custom` (PNG cleanup on rewind) |
| **`axiom.ui.web`** | Local HTTP server and Tabletop / Studio SPA Web interface. | Service `web_ui`; Open slots `side_panel`, `settings_tab`, `action_button`. | None |
| **`axiom.ui.qt`** | Native PySide6 desktop GUI application. | Service `qt_ui`; Open slots `sidebar_widget`, `settings_tab`. | None |
| **`axiom.cli`** | Interactive terminal-based text adventure (`axiom play`). | Service `cli_play`. | None |

---

## 4. Mod Author Reference Guide

Mod authors have three complementary approaches to develop official or third-party mods:

### A. Via LLM-assisted generation
```bash
axiom mod generate "Add a thirst mechanic that increases when traveling through the desert"
```
The engine stages the mod in a sandbox (`~/.cache/AxiomAI/staged_mods/`), validates its manifest, runs unit tests, and prints a color-coded diff before prompting for confirmation.

### B. Via manual scaffolding & live development
```bash
# 1. Create scaffold
axiom mod new myauthor.myfeature --type slot

# 2. Start live hot-reload development
axiom mod dev mods/myauthor.myfeature/

# 3. Validate and test archive
axiom mod test mods/myauthor.myfeature/
axiom mod pack mods/myauthor.myfeature/
```

### C. Canonical `main.py` template
```python
from axiom.kernel.context import ModContext

def init(ctx: ModContext) -> None:
    # 1. Contribute to turn prompt
    def inject_prompt(step_ctx):
        return ("system", 50, "Special rule: The player is thirsty.")
    ctx.contribute_slot("axiom.turn:prompt_sections", inject_prompt)

    # 2. Intercept LLM outputs
    def handle_output(data, turn_ctx):
        # Atomic staging into TurnWriteBatch
        turn_ctx.write_batch.stage_event("thirst_update", {"value": 10})
    ctx.contribute_slot("axiom.turn:output_fields", {"thirst_level": handle_output})

    # 3. Reversible surgical patch if needed (D11)
    def patch_prompt(orig_fn, *args, **kwargs):
        messages = orig_fn(*args, **kwargs)
        messages[0]["content"] += "\n(Scorching Desert)"
        return messages
    ctx.patch("axiom.prompts:build_narrative_prompt", "around", patch_prompt)
```

---

## 5. Dependencies and Licensing Boundary

- **Lightweight Python Dependencies (`[python].requires`):** Mods declare required third-party Python packages in their `mod.toml`. The loader verifies them statically at boot time and gracefully disables the mod with an informative warning if requirements are unsatisfied (Rule D-7), avoiding invasive pip installations.
- **Third-party mod licensing: open question.** No licensing exception for mods has been decided yet; until the authors decide (after legal advice), the project's AGPL-3.0-or-later license applies as-is. `docs/licensing_mods.md` is an unvalidated draft.

---

## 6. CLI Mod Management & Store Commands

```bash
# List installed mods, status, and API version
axiom mods list

# Enable or disable a mod
axiom mods enable community.lockpicking
axiom mods disable community.lockpicking

# Search the remote store catalog
axiom mods search "lockpicking"
axiom mods search "" --tag official

# Securely install a mod from the store with SHA-256 integrity verification
axiom mods install community.lockpicking

# Update installed mods
axiom mods update

# Launch in safe mode (disables all non-official / third-party mods)
axiom play MyWorld.db --safe-mode
```

---

## 7. Compliance & Robustness Review

* **Regression Tests:** **96 integration, unit, and end-to-end tests** pass cleanly (100%) with zero blocking warnings.
* **Golden Step Harness:** Critical lifecycle operations (10 consecutive turns, Rewind to $T-2$, Timeline Forking, Export and bit-for-bit Reimportation of `.axiomsave` archives) run with a **strictly zero diff**.
* **Headless PyPI Contract:** `export_engine.py` guarantees that the `axiomai-engine 1.0.0` distribution package has zero leaks to `ui/`, `workers/`, `web/`, or `mods/`.
* **Safety Status:** Emergency startup via the `--safe-mode` flag is fully operational across all interfaces, instantly neutralizing third-party mods in case of fatal error.
