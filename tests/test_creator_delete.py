"""Creator Studio: suppression de lignes (clic sur un cell widget, stats préservées)."""

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest


def _widget(qtbot, n=4):
    from mods.axiom.ui.qt.ui.widgets.entity_editor import EntityEditorWidget
    w = EntityEditorWidget()
    qtbot.addWidget(w)
    w.show()
    w.populate([
        {"entity_id": f"e{i}", "entity_type": "npc", "name": f"n{i}",
         "description": "", "stats": {"hp": str(i)}}
        for i in range(n)
    ])
    return w


def test_click_on_type_combo_selects_row_then_delete(qtbot) -> None:
    w = _widget(qtbot)
    QTest.mouseClick(w._table.cellWidget(2, 1), Qt.LeftButton)
    assert w._table.currentRow() == 2
    w._del_btn.click()
    assert [e["entity_id"] for e in w._entities_data] == ["e0", "e1", "e3"]


def test_delete_keeps_stats_of_remaining_entities(qtbot) -> None:
    w = _widget(qtbot)
    w._table.setCurrentCell(1, 0)
    w._del_btn.click()
    data = w.collect_data()
    assert [(e["entity_id"], e["stats"]) for e in data] == [
        ("e0", {"hp": "0"}), ("e2", {"hp": "2"}), ("e3", {"hp": "3"}),
    ]


def test_context_protocol(qtbot) -> None:
    w = _widget(qtbot)
    (view, fn), _stats = w.context_targets()
    assert view is w._table
    w._table.setCurrentCell(0, 2)
    fn()
    assert w._table.rowCount() == 3
    w.context_add(None)
    assert w._table.rowCount() == 4


def test_select_column_and_press_delete_key_deletes_rows(qtbot) -> None:
    w = _widget(qtbot)
    w._table.selectColumn(2)  # Select 'Name' column
    # Ensure all 4 rows are selected via this column
    assert len(w._table.selectionModel().selectedIndexes()) == 4
    # Press Key_Delete
    QTest.keyClick(w, Qt.Key_Delete)
    assert w._table.rowCount() == 0
    assert len(w._entities_data) == 0


def test_select_column_and_click_delete_button_deletes_rows(qtbot) -> None:
    w = _widget(qtbot)
    w._table.selectColumn(0)  # Select 'id' column
    w._del_btn.click()
    assert w._table.rowCount() == 0
    assert len(w._entities_data) == 0


def test_right_click_on_horizontal_header_selects_and_deletes(qtbot) -> None:
    from mods.axiom.ui.qt.ui.widgets.table_context import select_row_at
    from PySide6.QtCore import QPoint

    w = _widget(qtbot)
    header = w._table.horizontalHeader()
    # Global pos on section 2 ("Name") of the horizontal header
    rect = header.sectionViewportPosition(2)
    gp = header.viewport().mapToGlobal(QPoint(rect + 5, 5))

    assert select_row_at(w._table, gp) is True
    # Column 2 is selected -> all rows
    (view, fn), _stats = w.context_targets()
    fn()
    assert w._table.rowCount() == 0
    assert len(w._entities_data) == 0


def test_select_partial_column_cells_deletes_selected_rows(qtbot) -> None:
    w = _widget(qtbot)
    # Select cells (1, 2) and (2, 2)
    w._table.clearSelection()
    item1 = w._table.item(1, 2)
    item2 = w._table.item(2, 2)
    item1.setSelected(True)
    item2.setSelected(True)
    w._del_btn.click()
    assert [e["entity_id"] for e in w._entities_data] == ["e0", "e3"]
    assert w._table.rowCount() == 2


def test_delete_key_in_input_field_does_not_delete_entities(qtbot) -> None:
    w = _widget(qtbot)
    w._in_name.setText("hello")
    w._in_name.setCursorPosition(0)
    QTest.keyClick(w._in_name, Qt.Key_Delete)
    assert w._in_name.text() == "ello"
    assert w._table.rowCount() == 4
    assert len(w._entities_data) == 4


