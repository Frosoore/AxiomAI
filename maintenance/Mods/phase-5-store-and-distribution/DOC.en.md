# DOC — Phase 5: Store, Dependencies, Licensing & Distribution

## 1. Overview & Architectural Goals

Phase 5 completes the vision of an open modular ecosystem for Axiom AI by realizing the three founding promises (§1.1, §1.2, §14 of `DOC.md`) and decisions D-7, D-8, and D-9:

1. **Remote Store Protocol (Index, Search & Secure Installation)**:
   - Implementation of a decentralized/remote registry of `.axmod` packages (`axiom/kernel/store.py`).
   - Full-text search filterable by tags, API compatibility, and mod identifiers.
   - Systematic cryptographic SHA-256 integrity verification (§6.12): any corrupted or tampered download triggers a `ModIntegrityError` and aborts installation.
   - Initial reference catalog generated at `dist/mods/store_index.json` for all official and demonstration mods.

2. **Lightweight Python Dependencies Contract (D-7)**:
   - Manifest `mod.toml` extended with declarative table `[python].requires = [...]`.
   - Non-blocking static verification at load time (`axiom/kernel/dependencies.py`) via `importlib.metadata.version` and `packaging.specifiers.SpecifierSet`.
   - No heavy `pip` background installer. If a required Python package is missing, the loader logs a clear warning and disables the mod safely without crashing the engine.

3. **Legal Boundary and Mod Licensing (D-9, §14)**:
   - Documentation in `docs/licensing_mods.md` and updated `NOTICE`.
   - Explicit formalization of the boundary between the AGPLv3 core engine and independent third-party mods.
   - Mods interacting solely via public APIs (`ModContext`, hooks, slots, services, `.axmod` format) constitute independent works free to choose their own license (MIT, Apache 2.0, proprietary, etc.) under Section 7(b) of AGPLv3.
   - Conversely, intrusive in-memory monkeypatches modifying private kernel internals remain bound by AGPLv3 source reciprocity obligations.

4. **PyPI Headless Packaging Sanitization (`axiomai-engine`) (D-8)**:
   - Export script `export_engine.py` strictly isolates the headless micro-kernel (`axiom/`).
   - Formal exclusion of all mods (`mods/`), graphical/web UIs (`ui/`, `web/`, `main_web.py`), application workers, and game universes.
   - Automated verification of headless integrity (`check_headless`).
   - Version officially bumped to `1.0.0` in `axiom/__init__.py`.

5. **Unified User Experience (CLI & Web API)**:
   - CLI commands: `axiom mods search`, `axiom mods install`, `axiom mods update`.
   - Web API endpoints: `GET /api/store/search`, `POST /api/store/install`.

---

## 2. Technical Architecture of New Modules

```
axiom/
├── kernel/
│   ├── dependencies.py     # Python dependencies verification [python].requires (D-7)
│   ├── store.py            # Remote Store client, SHA-256 verification & installation
│   └── manifest.py         # Extended support for ModManifest.python_requires
├── cli/
│   └── mods_cmd.py         # Commands search, install, update
docs/
└── licensing_mods.md       # Legal specification of the AGPLv3 / Third-Party Mods boundary
dist/
└── mods/
    └── store_index.json    # Official Store catalog index
```

---

## 3. CLI Command Guide

### A. Searching the Store
```bash
axiom mods search "inventory"
axiom mods search "" --tag official
```

### B. Installing a mod from the Store
```bash
axiom mods install community.lockpicking --index dist/mods/store_index.json
```

### C. Updating installed mods
```bash
axiom mods update --index dist/mods/store_index.json
```

---

## 4. Web API Endpoints (`main_web.py`)

- `GET /api/store/search?q=<query>&tag=<tag>`: Queries the store index and returns available mods.
- `POST /api/store/install`:
  - **Request**: `{"mod_id": "community.lockpicking", "index_url": "..."}`
  - **Response**: `{"status": "success", "installed_path": "mods/community.lockpicking", "manifest": {...}}`
