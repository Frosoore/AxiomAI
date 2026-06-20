# TODO - Custom Wallpaper Feature

- [x] Add `custom_wallpaper: str = ""` to `AppConfig` in `axiom/config.py`.
- [x] Add wallpaper path settings in the Settings Dialog (`ui/settings_dialog.py`).
  - [x] Add input field and browse button to General section.
  - [x] Add `_on_browse_wallpaper` slot for file selection.
  - [x] Implement translation for labels and placeholders.
  - [x] Read and write the setting in `load_config` and `collect_config`.
- [x] Add wallpaper application logic in `MainWindow` (`ui/main_window.py`).
  - [x] Implement `apply_wallpaper_styling(self)` to set `background-image` style on `QMainWindow`.
  - [x] Set background opacity/transparency on stacked views (`HubView`, `CreatorStudioView`, `TabletopView`, `SetupView`, `LoadingView`).
  - [x] Enable `Qt.WA_StyledBackground` on views.
  - [x] Call `apply_wallpaper_styling()` on startup and on settings saving/accepting.
- [x] Add localization keys in `core/locales/*.toml` (for all 10 languages: `en`, `fr`, `es`, `de`, `it`, `pt`, `ru`, `zh`, `ja`, `ko`).
  - [x] `custom_wallpaper`
  - [x] `wallpaper_placeholder`
  - [x] `select_wallpaper_title`
  - [x] `browse`
- [x] Test that the custom wallpaper loads and behaves properly.
