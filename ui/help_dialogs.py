"""
ui/help_dialogs.py

TICKET-057 — integrated in-app documentation: the user-facing dialogs.

Everything here renders content from the ui/help_system registry:
  - ExplainPageDialog : "explain this page" (one page, all its elements)
  - DocDirectoryDialog: searchable directory of the whole app
  - QuickTourDialog   : paged first-launch tour (replayable from Help)
  - make_help_button(): the small "?" button placed in each page header
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from core.localization import tr
from ui import help_system


def _entry_html(ref: str) -> str:
    title_key, body_key = help_system.entry_keys(ref)
    html = f"<p><b>{tr(title_key)}</b><br/>{tr(body_key)}</p>"
    # Long-form details (examples, how-to, effect, why) are shown only here and
    # in the directory — never in the hover tooltip, which keeps the short body.
    if help_system.has_details(ref):
        html += f"<div style='margin:-6px 0 14px 0;'>{tr(help_system.details_key(ref))}</div>"
    return html


def _page_html(page: str) -> str:
    """Full HTML of one page: intro then every element."""
    title_key, intro_key = help_system.page_keys(page)
    parts = [f"<h2>{tr(title_key)}</h2>", f"<p>{tr(intro_key)}</p><hr/>"]
    for element in help_system.PAGES[page]:
        parts.append(_entry_html(f"{page}.{element}"))
    return "\n".join(parts)


class ExplainPageDialog(QDialog):
    """Brique 2 : the 'explain this page' dialog for a single page."""

    def __init__(self, page: str, parent=None) -> None:
        super().__init__(parent)
        title_key, _ = help_system.page_keys(page)
        self.setWindowTitle(tr(title_key))
        self.setMinimumSize(560, 520)

        layout = QVBoxLayout(self)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(_page_html(page))
        layout.addWidget(browser)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


class DocDirectoryDialog(QDialog):
    """Brique 4 : searchable directory of every documented element."""

    def __init__(self, parent=None, current_page: str | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("doc_directory_title"))
        self.setMinimumSize(760, 540)

        layout = QVBoxLayout(self)

        self._search = QLineEdit()
        self._search.setPlaceholderText(tr("doc_search_placeholder"))
        self._search.textChanged.connect(self._apply_filter)
        layout.addWidget(self._search)

        splitter = QSplitter(Qt.Horizontal)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._build_tree()
        self._tree.currentItemChanged.connect(self._on_selection)
        splitter.addWidget(self._tree)

        self._detail = QTextBrowser()
        self._detail.setOpenExternalLinks(True)
        splitter.addWidget(self._detail)
        splitter.setSizes([280, 480])
        layout.addWidget(splitter, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

        if current_page and current_page in help_system.PAGES:
            self._select_page(current_page)
        else:
            self._tree.setCurrentItem(self._tree.topLevelItem(0))

    # -- tree -----------------------------------------------------------

    def _build_tree(self) -> None:
        for page, elements in help_system.PAGES.items():
            page_title_key, _ = help_system.page_keys(page)
            page_item = QTreeWidgetItem([tr(page_title_key)])
            page_item.setData(0, Qt.UserRole, ("page", page))
            self._tree.addTopLevelItem(page_item)
            for element in elements:
                ref = f"{page}.{element}"
                title_key, _ = help_system.entry_keys(ref)
                child = QTreeWidgetItem([tr(title_key)])
                child.setData(0, Qt.UserRole, ("entry", ref))
                page_item.addChild(child)
        self._tree.expandAll()

    def _select_page(self, page: str) -> None:
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            if item.data(0, Qt.UserRole) == ("page", page):
                self._tree.setCurrentItem(item)
                return

    def _on_selection(self, current, _previous=None) -> None:
        if current is None:
            self._detail.clear()
            return
        kind, value = current.data(0, Qt.UserRole)
        if kind == "page":
            self._detail.setHtml(_page_html(value))
        else:
            page = value.split(".", 1)[0]
            page_title_key, _ = help_system.page_keys(page)
            self._detail.setHtml(
                f"<p style='color: gray;'>{tr(page_title_key)}</p>" + _entry_html(value)
            )

    # -- search ---------------------------------------------------------

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        for i in range(self._tree.topLevelItemCount()):
            page_item = self._tree.topLevelItem(i)
            _, page = page_item.data(0, Qt.UserRole)
            # A page matches on its own title/intro — and always when the search
            # is empty, so pages with no documented elements (e.g. an editor tab
            # whose internals aren't individually listed) still show.
            page_title_key, page_intro_key = help_system.page_keys(page)
            page_visible = (not needle) or (
                needle in f"{tr(page_title_key)} {tr(page_intro_key)}".lower())
            for j in range(page_item.childCount()):
                child = page_item.child(j)
                _, ref = child.data(0, Qt.UserRole)
                title_key, body_key = help_system.entry_keys(ref)
                haystack = f"{tr(title_key)} {tr(body_key)}".lower()
                match = not needle or needle in haystack
                child.setHidden(not match)
                page_visible = page_visible or match
            page_item.setHidden(not page_visible)


class QuickTourDialog(QDialog):
    """Brique 3 : paged welcome tour (first launch + Help menu replay)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("tour_title"))
        self.setMinimumSize(520, 360)
        self._index = 0

        layout = QVBoxLayout(self)

        self._step_label = QLabel()
        self._step_label.setStyleSheet("color: gray;")
        layout.addWidget(self._step_label)

        self._body = QTextBrowser()
        self._body.setOpenExternalLinks(True)
        layout.addWidget(self._body, 1)

        nav = QHBoxLayout()
        self._skip_btn = QPushButton(tr("tour_skip"))
        self._skip_btn.clicked.connect(self.reject)
        nav.addWidget(self._skip_btn)
        nav.addStretch()
        self._back_btn = QPushButton(tr("tour_back"))
        self._back_btn.clicked.connect(self._go_back)
        nav.addWidget(self._back_btn)
        self._next_btn = QPushButton(tr("tour_next"))
        self._next_btn.setDefault(True)
        self._next_btn.clicked.connect(self._go_next)
        nav.addWidget(self._next_btn)
        layout.addLayout(nav)

        self._show_step()

    def _show_step(self) -> None:
        steps = help_system.TOUR_STEPS
        step = steps[self._index]
        title_key, body_key = help_system.tour_keys(step)
        self._step_label.setText(
            tr("tour_step_fmt", current=self._index + 1, total=len(steps))
        )
        self._body.setHtml(f"<h2>{tr(title_key)}</h2><p>{tr(body_key)}</p>")
        self._back_btn.setEnabled(self._index > 0)
        last = self._index == len(steps) - 1
        self._next_btn.setText(tr("tour_finish") if last else tr("tour_next"))
        self._skip_btn.setVisible(not last)

    def _go_back(self) -> None:
        if self._index > 0:
            self._index -= 1
            self._show_step()

    def _go_next(self) -> None:
        if self._index == len(help_system.TOUR_STEPS) - 1:
            self.accept()
            return
        self._index += 1
        self._show_step()


def make_help_button(page, parent=None) -> QPushButton:
    """The 'Information' button placed in each page header (brique 2).

    `page` may be a page id (str) or a zero-arg callable returning one, resolved
    at click time — the Creator Studio passes a callable so the dialog always
    matches the active tab.
    """
    button = QPushButton(tr("information"), parent)
    button.setStyleSheet(
        "QPushButton { border-radius: 8px; font-weight: bold; padding: 4px 12px; }"
    )
    button.setToolTip(tr("explain_page_btn"))

    def _open() -> None:
        resolved = page() if callable(page) else page
        ExplainPageDialog(resolved, parent).exec()

    button.clicked.connect(_open)
    return button
