"""
ui/mods_dialog.py

Graphical Mods Manager dialog for Axiom AI.
Allows users to:
- View all installed official and third-party mods (.axmod archives and directories).
- Enable and disable mods with immediate config persistence.
- Inspect mod metadata, short descriptions, and categorized system impacts
  (what hooks, slots, patches, services, and tables it modifies).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QUrl, Slot
from PySide6.QtGui import QDesktopServices, QFont, QIcon
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from axiom.cli.mods_cmd import discover_installed_mods
from axiom.config import load_config, save_config
from axiom.kernel.loader import disable_mod_hot, is_mod_active, is_mod_enabled
from axiom.kernel.manifest import ModManifest
from core.localization import tr


def categorize_mod(manifest: ModManifest) -> tuple[str, str]:
    """Return a tuple of (category_label, icon_emoji) for a mod manifest."""
    provides = manifest.ordering.provides
    mid = manifest.id.lower()

    if "world" in mid or "world_model" in provides:
        return (tr("category_world_model"), "🌍")
    if "turn" in mid or "turn_pipeline" in provides:
        return (tr("category_turn_pipeline"), "🔄")
    if "time" in mid or "time" in provides:
        return (tr("category_time"), "⏳")
    if "inventory" in mid or "inventory" in provides:
        return (tr("category_inventory"), "🎒")
    if "rag" in mid or "living_memory" in mid or "memory" in mid:
        return (tr("category_memory"), "🧠")
    if "providers" in mid or "driver" in mid or "llm" in mid:
        return (tr("category_providers"), "🤖")
    if "illustrations" in mid or "images" in mid or "art" in mid:
        return (tr("category_illustrations"), "🎨")
    if "ui" in mid or "cli" in mid:
        return (tr("category_ui"), "🖥️")
    if "stat_dynamics" in mid or "dynamics" in mid or "stats" in provides:
        return (tr("category_mechanics"), "⚙️")
    if manifest.contributes.patches:
        return (tr("category_patches"), "⚡")
    if "data" in provides or "storage" in provides:
        return (tr("category_data"), "📦")
    return (tr("category_extension"), "🧩")


class ModsDialog(QDialog):
    """Dialog for viewing, enabling, disabling, and inspecting installed mods."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("mods_manager_title"))
        self.setMinimumSize(850, 580)
        self.resize(920, 640)

        # State
        self._cfg = load_config()
        self._installed_mods: list[tuple[ModManifest, Path]] = []
        self._current_manifest: ModManifest | None = None
        self._current_path: Path | None = None

        self._setup_ui()
        self._load_mods()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header area: Title & Search bar
        header_layout = QHBoxLayout()
        title_label = QLabel(tr("mods_manager_title"))
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(tr("mods_search_placeholder"))
        self._search_input.setClearButtonEnabled(True)
        self._search_input.setFixedWidth(280)
        self._search_input.textChanged.connect(self._apply_filter)
        header_layout.addWidget(self._search_input)

        layout.addLayout(header_layout)

        # Filter buttons bar (All / Enabled / Disabled)
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(8)

        self._btn_filter_all = QPushButton(tr("mods_filter_all", count=0))
        self._btn_filter_all.setCheckable(True)
        self._btn_filter_all.setChecked(True)
        self._btn_filter_all.clicked.connect(lambda: self._set_filter_mode("all"))
        filter_bar.addWidget(self._btn_filter_all)

        self._btn_filter_enabled = QPushButton(tr("mods_filter_enabled", count=0))
        self._btn_filter_enabled.setCheckable(True)
        self._btn_filter_enabled.clicked.connect(lambda: self._set_filter_mode("enabled"))
        filter_bar.addWidget(self._btn_filter_enabled)

        self._btn_filter_disabled = QPushButton(tr("mods_filter_disabled", count=0))
        self._btn_filter_disabled.setCheckable(True)
        self._btn_filter_disabled.clicked.connect(lambda: self._set_filter_mode("disabled"))
        filter_bar.addWidget(self._btn_filter_disabled)

        filter_bar.addStretch()
        layout.addLayout(filter_bar)
        self._filter_mode = "all"

        # Splitter: Left = Mods List, Right = Details Panel
        splitter = QSplitter(Qt.Horizontal)

        # Left: List of mods
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        self._mod_list = QListWidget()
        self._mod_list.setSelectionMode(QListWidget.SingleSelection)
        self._mod_list.currentItemChanged.connect(self._on_mod_selected)
        left_layout.addWidget(self._mod_list)

        splitter.addWidget(left_widget)
        splitter.setStretchFactor(0, 4)

        # Right: Detail scroll area
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QFrame.NoFrame)

        self._detail_container = QWidget()
        self._detail_layout = QVBoxLayout(self._detail_container)
        self._detail_layout.setContentsMargins(12, 4, 12, 12)
        self._detail_layout.setSpacing(14)

        self._setup_detail_view()
        self._scroll_area.setWidget(self._detail_container)

        splitter.addWidget(self._scroll_area)
        splitter.setStretchFactor(1, 6)

        layout.addWidget(splitter, 1)

        # Bottom Bar: Summary, open folder button, close button
        bottom_layout = QHBoxLayout()
        self._summary_label = QLabel()
        self._summary_label.setStyleSheet("color: #888888; font-size: 11px;")
        bottom_layout.addWidget(self._summary_label)

        bottom_layout.addStretch()

        open_folder_btn = QPushButton(f"📁 {tr('mods_open_folder')}")
        open_folder_btn.clicked.connect(self._open_mods_folder)
        bottom_layout.addWidget(open_folder_btn)

        btn_box = QDialogButtonBox(QDialogButtonBox.Close)
        btn_box.rejected.connect(self.accept)
        bottom_layout.addWidget(btn_box)

        layout.addLayout(bottom_layout)

    def _setup_detail_view(self) -> None:
        """Create widgets inside the right-hand detail pane."""
        # Empty placeholder
        self._empty_label = QLabel(tr("mods_select_hint"))
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setStyleSheet("color: #777777; font-size: 13px; padding: 40px;")
        self._detail_layout.addWidget(self._empty_label)

        # Content widget
        self._content_widget = QWidget()
        content_layout = QVBoxLayout(self._content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        # Header: Name + Toggle button
        header_row = QHBoxLayout()
        self._title_lbl = QLabel()
        name_font = QFont()
        name_font.setPointSize(14)
        name_font.setBold(True)
        self._title_lbl.setFont(name_font)
        header_row.addWidget(self._title_lbl, 1)

        self._toggle_btn = QPushButton()
        self._toggle_btn.setFixedWidth(140)
        self._toggle_btn.clicked.connect(self._toggle_current_mod)
        header_row.addWidget(self._toggle_btn)
        content_layout.addLayout(header_row)

        # Badges row (ID, Version, Status, API, Category)
        self._badges_row = QHBoxLayout()
        self._badges_row.setSpacing(8)

        self._badge_id = QLabel()
        self._badge_id.setStyleSheet("background: #2b2b3d; padding: 3px 8px; border-radius: 4px; font-family: monospace;")
        self._badges_row.addWidget(self._badge_id)

        self._badge_version = QLabel()
        self._badge_version.setStyleSheet("background: #2b2b3d; padding: 3px 8px; border-radius: 4px;")
        self._badges_row.addWidget(self._badge_version)

        self._badge_status = QLabel()
        self._badges_row.addWidget(self._badge_status)

        self._badge_category = QLabel()
        self._badge_category.setStyleSheet("background: #3b3b5c; padding: 3px 8px; border-radius: 4px; font-weight: bold;")
        self._badges_row.addWidget(self._badge_category)

        self._badges_row.addStretch()
        content_layout.addLayout(self._badges_row)

        self._notice_lbl = QLabel()
        self._notice_lbl.setWordWrap(True)
        self._notice_lbl.setStyleSheet("background: #45475a; color: #f9e2af; padding: 8px 12px; border-radius: 6px; font-weight: bold;")
        self._notice_lbl.hide()
        content_layout.addWidget(self._notice_lbl)

        # Description box
        desc_box = QFrame()
        desc_box.setFrameShape(QFrame.StyledPanel)
        desc_box.setStyleSheet("background: rgba(255, 255, 255, 0.03); border-radius: 6px; padding: 10px;")
        desc_layout = QVBoxLayout(desc_box)
        desc_title = QLabel("📝 Description")
        desc_title.setStyleSheet("font-weight: bold; color: #a6adc8;")
        desc_layout.addWidget(desc_title)
        self._desc_lbl = QLabel()
        self._desc_lbl.setWordWrap(True)
        desc_layout.addWidget(self._desc_lbl)
        content_layout.addWidget(desc_box)

        # "What This Mod Modifies" (Ce que ce mod modifie)
        changes_box = QFrame()
        changes_box.setFrameShape(QFrame.StyledPanel)
        changes_box.setStyleSheet("background: rgba(255, 255, 255, 0.03); border-radius: 6px; padding: 10px;")
        changes_layout = QVBoxLayout(changes_box)

        changes_title = QLabel(f"⚡ {tr('mods_changes_title')}")
        changes_title.setStyleSheet("font-weight: bold; color: #89b4fa;")
        changes_layout.addWidget(changes_title)

        self._changes_lbl = QLabel()
        self._changes_lbl.setWordWrap(True)
        self._changes_lbl.setTextFormat(Qt.RichText)
        changes_layout.addWidget(self._changes_lbl)
        content_layout.addWidget(changes_box)

        # Location and author metadata box
        meta_box = QFrame()
        meta_box.setFrameShape(QFrame.StyledPanel)
        meta_box.setStyleSheet("background: rgba(255, 255, 255, 0.02); border-radius: 6px; padding: 8px;")
        meta_layout = QVBoxLayout(meta_box)
        self._meta_lbl = QLabel()
        self._meta_lbl.setWordWrap(True)
        self._meta_lbl.setStyleSheet("color: #7f849c; font-size: 11px;")
        meta_layout.addWidget(self._meta_lbl)
        content_layout.addWidget(meta_box)

        content_layout.addStretch()
        self._detail_layout.addWidget(self._content_widget)
        self._content_widget.hide()

    def _load_mods(self) -> None:
        """Scan disk and populate the list widget."""
        self._installed_mods = discover_installed_mods()
        self._apply_filter()

    def _apply_filter(self) -> None:
        """Filter the mod list by search query and enabled/disabled state."""
        query = self._search_input.text().strip().lower()
        selected_id = self._current_manifest.id if self._current_manifest else None

        self._mod_list.clear()

        total = len(self._installed_mods)
        enabled_count = 0
        disabled_count = 0

        item_to_reselect: QListWidgetItem | None = None

        for manifest, path in self._installed_mods:
            enabled = is_mod_enabled(manifest.id, self._cfg)
            if enabled:
                enabled_count += 1
            else:
                disabled_count += 1

            cat_label, cat_icon = categorize_mod(manifest)

            mod_title = manifest.localized_name()
            mod_desc = manifest.localized_description()

            # Match search query
            matches_query = (
                not query
                or query in manifest.id.lower()
                or query in mod_title.lower()
                or query in mod_desc.lower()
                or query in cat_label.lower()
            )
            if not matches_query:
                continue

            # Match filter mode
            if self._filter_mode == "enabled" and not enabled:
                continue
            if self._filter_mode == "disabled" and enabled:
                continue

            status_symbol = "✔" if enabled else "✖"
            item_text = f"{status_symbol} {mod_title} (v{manifest.version})\n   [{cat_icon} {cat_label}] {manifest.id}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, (manifest, path))

            if enabled:
                item.setForeground(Qt.white)
            else:
                item.setForeground(Qt.gray)

            self._mod_list.addItem(item)
            if selected_id and manifest.id == selected_id:
                item_to_reselect = item

        # Update filter button counts
        self._btn_filter_all.setText(tr("mods_filter_all", count=total))
        self._btn_filter_enabled.setText(tr("mods_filter_enabled", count=enabled_count))
        self._btn_filter_disabled.setText(tr("mods_filter_disabled", count=disabled_count))

        self._summary_label.setText(
            f"{total} mod(s) • {enabled_count} {tr('mods_status_enabled').lower()} • "
            f"{disabled_count} {tr('mods_status_disabled').lower()}"
        )

        if item_to_reselect:
            self._mod_list.setCurrentItem(item_to_reselect)
        elif self._mod_list.count() > 0:
            self._mod_list.setCurrentRow(0)
        else:
            self._empty_label.show()
            self._content_widget.hide()

    def _set_filter_mode(self, mode: str) -> None:
        self._filter_mode = mode
        self._btn_filter_all.setChecked(mode == "all")
        self._btn_filter_enabled.setChecked(mode == "enabled")
        self._btn_filter_disabled.setChecked(mode == "disabled")
        self._apply_filter()

    @Slot(QListWidgetItem, QListWidgetItem)
    def _on_mod_selected(self, current: QListWidgetItem | None, previous: QListWidgetItem | None) -> None:
        if not current:
            self._current_manifest = None
            self._current_path = None
            self._empty_label.show()
            self._content_widget.hide()
            return

        manifest, path = current.data(Qt.UserRole)
        self._current_manifest = manifest
        self._current_path = path

        self._empty_label.hide()
        self._content_widget.show()
        self._render_mod_details(manifest, path)

    def _status_for(self, mod_id: str, enabled: bool, active: bool) -> tuple[str, str]:
        """Displayed state and reason: the real status of this process, and for a change
        not applied yet, the plan of the next launch (D13: never "enabled" for a mod
        that will not load)."""
        from axiom.kernel.loader import (
            STATE_ACTIVE,
            STATE_DISABLED,
            STATE_ENABLED,
            STATE_NEXT_LAUNCH,
            get_mod_status,
            plan_modpack,
        )

        current = get_mod_status(mod_id)
        if enabled and active:
            return "active", ""
        if not enabled:
            if active or (current is not None and current.state == STATE_NEXT_LAUNCH):
                return "next_launch_off", ""
            return "disabled", ""
        # Enabled but not running: will it load at next launch, and if not, why?
        if current is not None and current.state not in (STATE_DISABLED, STATE_ENABLED, STATE_ACTIVE):
            return "not_loaded", current.reason
        planned = plan_modpack(config=self._cfg).statuses.get(mod_id)
        if planned is not None and planned.state != STATE_ENABLED:
            return "not_loaded", planned.reason
        return "next_launch_on", ""

    def _render_mod_details(self, manifest: ModManifest, path: Path) -> None:
        enabled = is_mod_enabled(manifest.id, self._cfg)
        active = is_mod_active(manifest.id)
        cat_label, cat_icon = categorize_mod(manifest)
        mod_title = manifest.localized_name()
        mod_desc = manifest.localized_description()

        # Title
        self._title_lbl.setText(f"{cat_icon} {mod_title}")

        # Toggle button
        if enabled:
            self._toggle_btn.setText(tr("mods_btn_disable"))
            self._toggle_btn.setStyleSheet("background: #f38ba8; color: #11111b; font-weight: bold; border-radius: 4px; padding: 6px;")
        else:
            self._toggle_btn.setText(tr("mods_btn_enable"))
            self._toggle_btn.setStyleSheet("background: #a6e3a1; color: #11111b; font-weight: bold; border-radius: 4px; padding: 6px;")

        # Badges
        self._badge_id.setText(f"ID: {manifest.id}")
        self._badge_version.setText(f"v{manifest.version}")
        self._badge_category.setText(f"{cat_icon} {cat_label}")

        state, reason = self._status_for(manifest.id, enabled, active)
        badge_styles = {
            "active": ("#1e3a2f", "#a6e3a1"),
            "next_launch_on": ("#2b3d35", "#a6e3a1"),
            "next_launch_off": ("#453823", "#f9e2af"),
            "not_loaded": ("#45282d", "#f9e2af"),
            "disabled": ("#3b282d", "#f38ba8"),
        }
        if state == "active":
            text, notice = f"● {tr('mods_status_enabled')}", ""
        elif state == "next_launch_on":
            text = f"● {tr('mods_status_enabled')} ({tr('mods_next_launch')})"
            notice = f"ℹ️ {tr('mods_enable_restart_notice')}"
        elif state == "next_launch_off":
            text = f"○ {tr('mods_status_disabled')} ({tr('mods_next_launch')})"
            notice = f"⚠️ {tr('mods_restart_required_notice')}"
        elif state == "not_loaded":
            text = f"✕ {tr('mods_status_not_loaded')}"
            notice = f"⚠️ {tr('mods_not_loaded_notice', reason=reason)}"
        else:
            text, notice = f"○ {tr('mods_status_disabled')}", ""
        bg, fg = badge_styles[state]
        self._badge_status.setText(text)
        self._badge_status.setStyleSheet(
            f"background: {bg}; color: {fg}; padding: 3px 8px; border-radius: 4px; font-weight: bold;"
        )
        self._notice_lbl.setText(notice)
        self._notice_lbl.setVisible(bool(notice))

        # Description
        desc_text = mod_desc.strip() if mod_desc else tr("mods_no_description")
        self._desc_lbl.setText(desc_text)

        # What This Mod Modifies (Detailed breakdown)
        changes_html: list[str] = []

        # 1. Catégorie & Provides
        provides_str = ", ".join(manifest.ordering.provides) if manifest.ordering.provides else "—"
        changes_html.append(f"<b>{tr('mods_meta_category')} :</b> {cat_icon} {cat_label}")
        changes_html.append(f"<b>{tr('mods_meta_provides')} :</b> <code>{provides_str}</code>")

        # 2. Hooks
        if manifest.contributes.hooks:
            hooks_formatted = "<br>&nbsp;&nbsp;• ".join(f"<code>{h}</code>" for h in manifest.contributes.hooks)
            changes_html.append(f"<b>{tr('mods_meta_hooks_subscribed')} :</b><br>&nbsp;&nbsp;• {hooks_formatted}")
        else:
            changes_html.append(f"<b>{tr('mods_meta_hooks')} :</b> <i>{tr('mods_meta_none')}</i>")

        # 3. Slots
        if manifest.contributes.slots:
            slots_formatted = "<br>&nbsp;&nbsp;• ".join(f"<code>{s}</code>" for s in manifest.contributes.slots)
            changes_html.append(f"<b>{tr('mods_meta_slots_contributed')} :</b><br>&nbsp;&nbsp;• {slots_formatted}")
        else:
            changes_html.append(f"<b>{tr('mods_meta_slots')} :</b> <i>{tr('mods_meta_none')}</i>")

        # 4. Patches
        if manifest.contributes.patches:
            patches_formatted = "<br>&nbsp;&nbsp;• ".join(f"<code>{p}</code>" for p in manifest.contributes.patches)
            changes_html.append(f"<b>{tr('mods_meta_patches')} :</b><br>&nbsp;&nbsp;• {patches_formatted}")

        # 5. Slots ouverts créés par ce mod
        if manifest.provides_slots:
            slots_list = "<br>&nbsp;&nbsp;• ".join(f"<code>{s}</code>" for s in manifest.provides_slots.keys())
            changes_html.append(f"<b>{tr('mods_meta_slots_provided')} :</b><br>&nbsp;&nbsp;• {slots_list}")

        # 6. Dépendances
        if manifest.dependencies:
            deps_formatted = ", ".join(f"<code>{d}</code>" for d in manifest.dependencies.keys())
            changes_html.append(f"<b>{tr('mods_meta_dependencies')} :</b> {deps_formatted}")

        if manifest.python_requires:
            py_formatted = ", ".join(f"<code>{p}</code>" for p in manifest.python_requires)
            changes_html.append(f"<b>{tr('mods_meta_python_deps')} :</b> {py_formatted}")

        self._changes_lbl.setText("<br><br>".join(changes_html))

        # Location metadata
        is_archive = path.is_file() and path.suffix == ".axmod"
        type_str = tr("mods_type_archive") if is_archive else tr("mods_type_directory")
        author_str = manifest.author or tr("mods_author_unknown")
        compat_str = f"v{manifest.axiom_api} ({tr('mods_api_compatible')})" if manifest.axiom_api == 1 else f"v{manifest.axiom_api}"
        self._meta_lbl.setText(
            f"<b>{tr('mods_meta_type')} :</b> {type_str}<br>"
            f"<b>{tr('mods_meta_location')} :</b> <code>{path}</code><br>"
            f"<b>{tr('mods_meta_author')} :</b> {author_str}<br>"
            f"<b>{tr('mods_meta_api_compat')} :</b> {compat_str}<br>"
            f"<i>{tr('mods_restart_hint')}</i>"
        )

    @Slot()
    def _toggle_current_mod(self) -> None:
        """Toggle enabled/disabled state of the selected mod."""
        if not self._current_manifest:
            return

        mod_id = self._current_manifest.id
        current_state = is_mod_enabled(mod_id, self._cfg)
        new_state = not current_state

        if mod_id == "axiom.ui.qt" and not new_state:
            reply = QMessageBox.question(
                self,
                tr("mods_disable_active_ui_title"),
                tr(
                    "mods_disable_active_ui_prompt",
                    mod_name=self._current_manifest.name,
                    mod_id=mod_id,
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

            self._cfg.mod_settings.setdefault(mod_id, {})["enabled"] = False
            save_config(self._cfg)
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app is not None:
                app.quit()
            else:
                self.close()
            return

        self._cfg.mod_settings.setdefault(mod_id, {})["enabled"] = new_state
        save_config(self._cfg)

        if not new_state:
            from axiom.kernel.loader import get_load_state
            state = get_load_state()
            dependents = state.dependents_of(mod_id) if state is not None else []
            disable_mod_hot(mod_id)
            if dependents:
                # D13 / §1.4: the mods that depend on it go down with it, and we say so.
                QMessageBox.information(
                    self,
                    tr("mods_manager_title"),
                    tr("mods_dependents_disabled", mod_id=mod_id, dependents=", ".join(dependents)),
                )

        # Notify parent UI if available
        parent = self.parent()
        if parent is not None:
            if hasattr(parent, "_tabletop_view") and hasattr(parent._tabletop_view, "update_mod_visibility"):
                parent._tabletop_view.update_mod_visibility(self._cfg)
            if hasattr(parent, "_hub_view") and hasattr(parent._hub_view, "update_mod_visibility"):
                parent._hub_view.update_mod_visibility(self._cfg)
            if hasattr(parent, "update_mod_visibility"):
                parent.update_mod_visibility(self._cfg)

        # Refresh UI
        self._apply_filter()

    @Slot()
    def _open_mods_folder(self) -> None:
        """Open the mods directory in the system file explorer."""
        from axiom.kernel.loader import get_user_mods_dir
        mods_dir = get_user_mods_dir()
        mods_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(mods_dir)))
