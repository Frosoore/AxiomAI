# Changelog - Feature Universe Description

## [Unreleased]

### Added
- Added universe description support in compiler (`axiom/compile.py`), decompiling (`axiom/decompile.py`), database helper methods (`axiom/db_helpers.py`), and library loader (`axiom/library.py`).
- Added word-wrapped description display in the Library Hub's card widget (`ui/widgets/universe_card.py` and `ui/hub_view.py`).
  - Truncated descriptions to 700 characters to avoid stretching the card.
  - Implemented hover tooltips displaying the full description on the library card.
  - Implemented dynamic card recreation when returning to the Hub, ensuring saved metadata (description, name, difficulty, last active) updates instantly without restarting the application.
- Added description editing text field in the Creator Studio Lore tab (`ui/creator_studio_view.py`).
- Localized all universe description field labels and help texts (`doc_creator_meta_description_t`, `doc_creator_meta_description`, `doc_creator_meta_description_d`, `universe_description_title`, `universe_description_placeholder`) across all 10 supported languages under `core/locales/*.toml`.
- Registered `creator_meta.description` in the interactive help system (`ui/help_system.py`).
