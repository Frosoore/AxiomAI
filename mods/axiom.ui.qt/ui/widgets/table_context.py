"""
ui/widgets/table_context.py

Shared helpers for the Creator Studio editors:
- selected_rows(): which rows a "Delete" should hit (selection, else current row).
- set_cell_widget(): setCellWidget + make a click on the widget select its row
  (otherwise the current row stays stale and Delete removes the wrong one).

Context-menu protocol (read by CreatorStudioView.contextMenuEvent), all optional
on an editor widget:
    context_targets() -> list[(view, delete_selection_callable)]
    context_add(under: QWidget | None) -> None
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint
from PySide6.QtWidgets import QAbstractItemView, QTableWidget, QWidget


def selected_rows(table: QTableWidget) -> list[int]:
    """Rows to act on, ascending: rows of selected cells, else the current row."""
    rows = {i.row() for i in table.selectionModel().selectedIndexes()}
    if not rows and table.currentRow() >= 0:
        rows = {table.currentRow()}
    return sorted(r for r in rows if 0 <= r < table.rowCount())


class _RowSelectFilter(QObject):
    def __init__(self, table: QTableWidget) -> None:
        super().__init__(table)
        self._table = table

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.MouseButtonPress and isinstance(obj, QWidget):
            table = self._table
            idx = table.indexAt(obj.mapTo(table.viewport(), QPoint(0, 0)))
            if idx.isValid():
                table.setCurrentCell(idx.row(), idx.column())
        return False


def set_cell_widget(table: QTableWidget, row: int, col: int, widget: QWidget) -> None:
    table.setCellWidget(row, col, widget)
    flt = _RowSelectFilter(table)
    widget.installEventFilter(flt)
    for child in widget.findChildren(QWidget):
        child.installEventFilter(flt)


def select_row_at(view: QAbstractItemView, global_pos) -> bool:
    """Select the row under global_pos (keeps a multi-selection that contains it).

    Returns True if the position is over an item or table header.
    """
    header = getattr(view, "horizontalHeader", lambda: None)()
    if header is not None:
        pos_in_h = header.mapFromGlobal(global_pos)
        if header.rect().contains(pos_in_h):
            col = header.logicalIndexAt(pos_in_h)
            if col >= 0:
                rows_in_col = {i.row() for i in view.selectionModel().selectedIndexes() if i.column() == col}
                num_rows = getattr(view, "rowCount", lambda: 0)()
                if len(rows_in_col) < num_rows or not view.selectionModel().hasSelection():
                    if isinstance(view, QTableWidget):
                        view.selectColumn(col)
                return True
            return False

    v_header = getattr(view, "verticalHeader", lambda: None)()
    if v_header is not None:
        pos_in_v = v_header.mapFromGlobal(global_pos)
        if v_header.rect().contains(pos_in_v):
            row = v_header.logicalIndexAt(pos_in_v)
            if row >= 0:
                cols_in_row = {i.column() for i in view.selectionModel().selectedIndexes() if i.row() == row}
                num_cols = getattr(view, "columnCount", lambda: 0)()
                if len(cols_in_row) < num_cols or not view.selectionModel().hasSelection():
                    if isinstance(view, QTableWidget):
                        view.selectRow(row)
                return True
            return False

    idx = view.indexAt(view.viewport().mapFromGlobal(global_pos))
    if not idx.isValid():
        return False
    if isinstance(view, QTableWidget):
        if idx.row() not in {i.row() for i in view.selectionModel().selectedIndexes()}:
            view.setCurrentCell(idx.row(), idx.column())
    else:
        view.setCurrentIndex(idx)
    return True

