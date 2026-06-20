# CHANGELOG - Custom Wallpaper Feature

## [Unreleased]
### Added
- Created the feature step files (`TODO.md`, `CHANGELOG.md`, `DOC.md`).
- Added `custom_wallpaper` configuration setting to `AppConfig` in `axiom/config.py`.
- Integrated wallpaper line edit, browse button, and selection dialog inside settings dialog (`ui/settings_dialog.py`).
- Implemented `apply_wallpaper_styling` in `MainWindow` (`ui/main_window.py`) to render custom backgrounds with a premium glassmorphic transparency overlay for child views.
- Made layout containers (`QFrame`, `QTabWidget::pane`, `QScrollArea`, `QListWidget`, text browser, input boxes, status bar, and menu bar) transparent or semi-transparent using `!important` stylesheet overrides when the wallpaper is set, allowing it to show through beautifully across the entire application interface.
- Styled interactive controls (buttons, dropdowns, spinboxes, active tabs, and sliders) with a distinct dark blue background and light blue border theme when the custom wallpaper is active, preventing them from being visually drowned out by the background image.
- Translated all new keys (`custom_wallpaper`, `wallpaper_placeholder`, `select_wallpaper_title`, `browse`) into the 10 supported languages in `core/locales/*.toml`.
- Added unit test validation in `tests/test_settings_dialog.py` and `tests/test_config.py`.

### Fixed
- Fixed NameError crash by importing QFileDialog in `ui/settings_dialog.py`.
- Fixed styling inheritance blockage on HubView and other stacked views by applying custom wallpaper styling at the QApplication level instead of MainWindow, allowing it to correctly propagate to all child widgets.
- Fixed home page buttons and other custom-colored buttons not showing the deep blue background by dynamically toggling their stylesheets to match the wallpaper state.

