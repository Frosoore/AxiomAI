> ⚠ **Unreliable document (review of 2026-10-03).** Written by an agent; several claims are false.
> The actual state is in `ETAT_REEL.md` (French), the roadmap in `TODO.md`.

# TODO — Modding System Roadmap (`.axmod`)

## Phase 0 — Sanitize Engine (without mods) (✅ COMPLETED)
- [x] 0a. Golden step harness (scripted LLM mock, N turns -> rewind -> fork -> export -> comparison)
- [x] 0b. Single end-of-turn in `Session` (unified Qt/Web living memory, auto-canonize)
- [x] 0c. Single rewind + save data registry (eradication of the 5 manual table lists)
- [x] 0d. Transactional turn + session epochs (`TurnWriteBatch`, `SessionEpochManager`)
- [x] 0e. Open configuration (`mod_settings`) + schema versions + migrations
- [x] 0f. Splitting `process_turn` into named modular steps

## Phase 1 — Core Kernel (✅ COMPLETED)
- [x] Loader + manifest `mod.toml` + registry (exclusive / chain / collect) + hooks + `ModContext`
- [x] Storage policies + modpack + safe mode + CLI `axiom mods`
- [x] First official mod extracted (`core.stat_dynamics`) to validate

## Phase 2 — Official Feature Mods (✅ COMPLETED)
- [x] `axiom.world` & `axiom.turn` (world model and turn pipeline)
- [x] `axiom.time` & `axiom.inventory` (causal time and container trees)
- [x] `axiom.rag` & `axiom.living_memory` (semantic vector memory and symbolic living memory)
- [x] `axiom.providers` & `axiom.illustrations` (LLM inference drivers, image generation, Universe-as-Code hooks)
- [x] User Interfaces (`axiom.ui.web`, `axiom.ui.qt`, `axiom.cli`) & cross-cutting extensions (i18n, help, safe-mode)

## Phase 3 — Tooling & Patches System (✅ COMPLETED)
- [x] `@patchable` trampolines (before, after, around) and `ShortCircuit` sentinel
- [x] Fallback mechanism via bytecode swapping (`__code__` swapping) preserving object identity
- [x] Reversible registration via `ctx.patch()` and full restoration at `ctx.cleanup()` (D11)
- [x] Per-step execution freeze (§6.2.3, `step_patch_freeze()`, `PatchingDuringStepError`)
- [x] CLI inspection (`axiom mods patches`) and static validation (`axiom mod validate`)

## Phase 4 — Mod Authoring Tools & LLM Creator (✅ COMPLETED)
- [x] Scaffolding: `axiom mod new` (`axiom/kernel/scaffold.py`) supporting hook, slot, and data archetypes
- [x] Unified mod tester: `axiom mod test` (`axiom/kernel/tester.py`) with manifest validation, D4 UI import detection, sandboxed execution and pytest runner
- [x] Live hot-reload: `axiom mod dev` (`axiom/kernel/dev.py`) with mtime watcher, D11 unstacking and module reload
- [x] LLM mod creator: `axiom mod generate` & Web API (`axiom/kernel/llm_creator.py`) with sandbox staging, diffs, automated tests, and interactive confirmation gates (§12, D14)

## Phase 5 — Store, Dependencies, Licensing & Distribution (✅ COMPLETED)
- [x] Remote Store protocol (`axiom/kernel/store.py`): index catalog, search, installation, strict SHA-256 hash verification (`ModIntegrityError`)
- [x] Declarative lightweight Python dependencies (`axiom/kernel/dependencies.py`, `[python].requires`, Rule D-7)
- [x] Legal boundary and mod licensing (`docs/licensing_mods.md`, `NOTICE`, Rule D-9 & §14)
- [x] PyPI headless micro-kernel packaging (`export_engine.py`, exclusion of mods/UI, Rule D-8) and version 1.0.0 bump
- [x] CLI subcommands (`axiom mods search`, `axiom mods install`, `axiom mods update`)
- [x] Web API endpoints (`GET /api/store/search`, `POST /api/store/install`)
- [x] Official reference catalog (`dist/mods/store_index.json`)
- [x] Dedicated test suite (`tests/test_mod_store_and_packaging.py`) — 9/9 tests green
