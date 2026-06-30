# Documentation - Feature Universe Description

This feature adds a user-facing description field to universes.

## Key Changes

### Compiler & Decompiler
- Compiled from `[meta].description` inside `universe.toml` to `universe_description` field in the database table `Universe_Meta`.
- Decompiled from `universe_description` field in the database back to `[meta].description` inside `universe.toml`.

### Database & Library
- `provision_blank_universe` initializes `universe_description` to `""`.
- `read_universe_card_metadata` fetches the description, returning it as part of a 4-tuple.
- `axiom/library.py` maps the description field to `universe_description` inside the returned library entry dictionaries.

### UI
- The Library Card widget wraps description text nicely below the difficulty badge.
- Creator Studio has a new text field under the Metadata tab allowing creation and modification of the description.

### Localization & Help System
- 10 languages supported: English, French, Spanish, German, Italian, Portuguese, Russian, Chinese, Japanese, Korean.
- Integrated help system documentation registered in `ui/help_system.py`.
