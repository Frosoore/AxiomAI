# Custom Wallpaper Documentation

## Objective
Provide users with the option to set a custom background wallpaper in Axiom AI, replacing the flat `#1e1e2e` Catppuccin background.

## Technical Design
1. **Config**: Add `custom_wallpaper` string property to `AppConfig` in `axiom/config.py`.
2. **Settings GUI**:
   - Add a file selection field and "Browse" button under General section in `SettingsDialog`.
   - Use `QFileDialog` to choose local image files.
3. **MainWindow & QApplication Styling**:
   - Apply QSS styling with `background-image: url(...)` globally at the `QApplication` level rather than only on `QMainWindow` to ensure it propagates correctly to all child screens and sub-widgets (bypassing local stylesheet isolation).
   - Set stacked widgets, scroll areas, and container panels to transparent so the wallpaper shows through beautifully.
   - Style all interactive controls (buttons, comboboxes, spinboxes, active tabs) with a solid, premium deep navy blue (`#172554`) background and a light blue (`#89b4fa`) border when the custom wallpaper is active, preventing them from being drowned out by the background image.
   - Dynamically toggle custom-colored buttons (e.g. "Delete" on cards, "Delete Save" in setup view, "Cancel Generation" in the status bar) to use this deep blue background when the wallpaper is active, and revert them to their default inline styles when disabled.

