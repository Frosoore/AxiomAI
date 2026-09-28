# CHANGELOG — Phase 5: Store, Dependencies, Licensing & Distribution

## [Phase 5] - 2026-09-27

### Added

- **Remote Store Client (`axiom/kernel/store.py`)**:
  - `StoreModEntry`: Data model for distributed `.axmod` packages.
  - `calculate_sha256(path)`: Secure streaming SHA-256 computation in 64 KB chunks.
  - `fetch_store_index(url_or_path)`: Index resolver for remote HTTP/HTTPS and local catalog files.
  - `search_store(query, index, tag)`: Full-text search and tag filtering engine.
  - `install_mod_from_store(mod_id, index, target_mods_dir)`: Secure download with SHA-256 verification, `ModIntegrityError` rejection on tamper, and atomic extraction.
  - `publish_mod_to_store_spec(archive_path, download_url, tags)`: Catalog entry generator.

- **Lightweight Python Dependencies Verification (`axiom/kernel/dependencies.py` & `axiom/kernel/loader.py`)**:
  - `ModManifest.python_requires: list[str]` loaded from `[python].requires` in `mod.toml`.
  - `check_python_requirement(req_str)`: Non-invasive static check via `importlib.metadata` and `packaging.specifiers` (Rule D-7).
  - `check_mod_python_dependencies(manifest)`: Dependency diagnosis report.
  - Graceful loader skip: Informative warning and safe mod disable without crashing the engine.

- **Legal Licensing Framework (`docs/licensing_mods.md` & `NOTICE`)**:
  - Permissive extensibility terms under AGPLv3 Section 7(b).
  - Freedom for third-party modders using public APIs (`ModContext`, hooks, slots) to select any license.
  - Reciprocal AGPLv3 copyleft terms for private in-memory monkeypatching.

- **Headless PyPI Packaging (`axiomai-engine 1.0.0`)**:
  - Official version bump to `1.0.0` in `axiom/__init__.py`.
  - Sanitized export via `export_engine.py` excluding `mods/`, `web/`, `ui/`, `workers/`, and `universes/` (Rule D-8).
  - Headless check passes with zero forbidden import warnings.

- **CLI Subcommands (`axiom/cli/mods_cmd.py`)**:
  - `axiom mods search`, `axiom mods install`, `axiom mods update`.

- **Web API Endpoints (`main_web.py`)**:
  - `GET /api/store/search`, `POST /api/store/install`.

- **Dedicated Test Suite (`tests/test_mod_store_and_packaging.py`)**:
  - 9/9 tests passing (100% green).
