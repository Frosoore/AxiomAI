"""
ui/widgets/universe_files_tab.py

TICKET-029 — Onglet « Fichiers » du Creator Studio : voir et éditer directement
l'arborescence texte d'un univers-dossier (universe.toml, entities/*.toml,
lore/**/*.md, …). À l'enregistrement, le Studio recompile la définition
in-place (`refresh_definition`) et recharge ses vues.

Pour un `.db` plat (legacy, sans source texte), l'onglet propose la conversion
en univers-dossier (`axiom.library.convert_flat_db_to_folder`).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.localization import tr

# Fichiers texte éditables de l'arbo source. Le cache compilé et .git sont
# exclus de l'affichage (zones protégées, cf. axiom.library).
_EDITABLE_SUFFIXES = {".toml", ".md", ".txt", ".json"}
_HIDDEN_TOP_LEVEL = {".axiom-cache", ".git"}


class UniverseFilesTabWidget(QWidget):
    """Arbo + éditeur des fichiers source d'un univers."""

    file_saved = Signal(str)    # chemin absolu du fichier écrit
    convert_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._src_dir: Path | None = None
        self._current_rel: str | None = None
        self._loaded_text: str = ""
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        # Page 0 : univers-dossier (arbo + éditeur).
        source_page = QWidget()
        src_layout = QVBoxLayout(source_page)
        src_layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Horizontal)
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.currentItemChanged.connect(self._on_tree_selection)
        splitter.addWidget(self._tree)

        editor_panel = QWidget()
        ed_layout = QVBoxLayout(editor_panel)
        ed_layout.setContentsMargins(0, 0, 0, 0)
        self._path_label = QLabel("")
        self._path_label.setStyleSheet("color: #888;")
        ed_layout.addWidget(self._path_label)
        self._editor = QPlainTextEdit()
        self._editor.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self._editor.textChanged.connect(self._on_text_changed)
        ed_layout.addWidget(self._editor)
        self._save_file_btn = QPushButton(tr("files_save_file"))
        self._save_file_btn.clicked.connect(self._on_save_file_clicked)
        ed_layout.addWidget(self._save_file_btn, 0, Qt.AlignRight)
        splitter.addWidget(editor_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        src_layout.addWidget(splitter)
        self._stack.addWidget(source_page)

        # Page 1 : .db plat → proposition de conversion.
        flat_page = QWidget()
        flat_layout = QVBoxLayout(flat_page)
        flat_layout.addStretch()
        self._flat_label = QLabel(tr("files_flat_db_msg"))
        self._flat_label.setWordWrap(True)
        self._flat_label.setAlignment(Qt.AlignCenter)
        flat_layout.addWidget(self._flat_label)
        self._convert_btn = QPushButton(tr("files_convert_btn"))
        self._convert_btn.setFixedHeight(40)
        self._convert_btn.clicked.connect(self._on_convert_clicked)
        flat_layout.addWidget(self._convert_btn, 0, Qt.AlignCenter)
        flat_layout.addStretch()
        self._stack.addWidget(flat_page)

        self._show_editor(False)

    def retranslate_ui(self) -> None:
        self._save_file_btn.setText(tr("files_save_file"))
        self._flat_label.setText(tr("files_flat_db_msg"))
        self._convert_btn.setText(tr("files_convert_btn"))

    # ------------------------------------------------------------------
    # API publique (pilotée par CreatorStudioView)
    # ------------------------------------------------------------------

    def set_universe(self, db_path: str | None) -> None:
        """Pointe l'onglet sur un univers : arbo si dossier source, sinon conversion."""
        from axiom.library import universe_root_for

        self._src_dir = universe_root_for(db_path) if db_path else None
        self._current_rel = None
        self._loaded_text = ""
        if self._src_dir is None:
            self._stack.setCurrentIndex(1)
        else:
            self._stack.setCurrentIndex(0)
            self.refresh()

    def refresh(self) -> None:
        """Relit l'arbo et le fichier courant depuis le disque.

        Appelé à chaque activation de l'onglet : le Studio réécrit la source à
        chaque sauvegarde (TICKET-027), le contenu affiché doit suivre.
        """
        if self._src_dir is None:
            return
        if not self._confirm_discard():
            return
        selected = self._current_rel
        self._populate_tree()
        if selected and (self._src_dir / selected).is_file():
            self._select_rel(selected)
        else:
            self._show_editor(False)

    def has_unsaved_changes(self) -> bool:
        return (
            self._current_rel is not None
            and self._editor.toPlainText() != self._loaded_text
        )

    # ------------------------------------------------------------------
    # Internes
    # ------------------------------------------------------------------

    def _populate_tree(self) -> None:
        self._tree.blockSignals(True)
        self._tree.clear()
        nodes: dict[str, QTreeWidgetItem] = {}

        def node_for(rel_dir: Path) -> QTreeWidgetItem | None:
            if not rel_dir.parts:
                return None
            key = str(rel_dir)
            if key in nodes:
                return nodes[key]
            parent = node_for(rel_dir.parent)
            item = QTreeWidgetItem([rel_dir.name])
            (parent or self._tree.invisibleRootItem()).addChild(item)
            nodes[key] = item
            return item

        files = sorted(
            p for p in self._src_dir.rglob("*")
            if p.is_file()
            and p.suffix.lower() in _EDITABLE_SUFFIXES
            and p.relative_to(self._src_dir).parts[0] not in _HIDDEN_TOP_LEVEL
        )
        for f in files:
            rel = f.relative_to(self._src_dir)
            item = QTreeWidgetItem([rel.name])
            item.setData(0, Qt.UserRole, str(rel))
            (node_for(rel.parent) or self._tree.invisibleRootItem()).addChild(item)
        self._tree.expandAll()
        self._tree.blockSignals(False)

    def _select_rel(self, rel: str) -> None:
        for item in self._tree.findItems(Path(rel).name, Qt.MatchExactly | Qt.MatchRecursive):
            if item.data(0, Qt.UserRole) == rel:
                self._tree.setCurrentItem(item)
                return

    def _show_editor(self, on: bool) -> None:
        self._editor.setEnabled(on)
        self._save_file_btn.setEnabled(False)
        if not on:
            self._current_rel = None
            self._loaded_text = ""
            self._editor.blockSignals(True)
            self._editor.setPlainText("")
            self._editor.blockSignals(False)
            self._path_label.setText("")

    def _confirm_discard(self) -> bool:
        """True si on peut quitter le fichier courant (modifs sauvées ou jetées)."""
        if not self.has_unsaved_changes():
            return True
        reply = QMessageBox.question(
            self, tr("tab_files"), tr("files_unsaved_q", name=self._current_rel)
        )
        if reply == QMessageBox.Yes:
            self._write_current()
        return True  # Yes = sauvé, No = jeté : dans les deux cas on continue

    @Slot()
    def _on_tree_selection(self, current: QTreeWidgetItem | None, _previous=None) -> None:
        rel = current.data(0, Qt.UserRole) if current else None
        if rel is None or rel == self._current_rel:
            return
        if not self._confirm_discard():
            return
        path = self._src_dir / rel
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, tr("error"), str(exc))
            return
        self._current_rel = rel
        self._loaded_text = text
        self._editor.blockSignals(True)
        self._editor.setPlainText(text)
        self._editor.blockSignals(False)
        self._editor.setEnabled(True)
        self._path_label.setText(rel)
        self._save_file_btn.setEnabled(False)

    @Slot()
    def _on_text_changed(self) -> None:
        self._save_file_btn.setEnabled(self.has_unsaved_changes())

    @Slot()
    def _on_save_file_clicked(self) -> None:
        if self.has_unsaved_changes():
            self._write_current()

    def _write_current(self) -> None:
        path = self._src_dir / self._current_rel
        try:
            path.write_text(self._editor.toPlainText(), encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, tr("error"), str(exc))
            return
        self._loaded_text = self._editor.toPlainText()
        self._save_file_btn.setEnabled(False)
        self.file_saved.emit(str(path))

    @Slot()
    def _on_convert_clicked(self) -> None:
        reply = QMessageBox.question(
            self, tr("files_convert_btn"), tr("files_convert_confirm")
        )
        if reply == QMessageBox.Yes:
            self.convert_requested.emit()
