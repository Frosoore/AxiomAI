"""Tests for StatDefinitionEditorWidget in Creator Studio."""

import pytest
from PySide6.QtWidgets import QComboBox

from mods.axiom.ui.qt.ui.widgets.stat_definition_editor import StatDefinitionEditorWidget


@pytest.fixture
def stat_widget(qtbot):
    w = StatDefinitionEditorWidget()
    qtbot.addWidget(w)
    return w


def test_populate_and_collect_data(stat_widget):
    initial_stats = [
        {
            "stat_id": "hp",
            "name": "Health",
            "value_type": "numeric",
            "description": "Physical vitality",
            "parameters": {"min": 0.0, "max": 100.0},
        },
        {
            "stat_id": "stance",
            "name": "Stance",
            "value_type": "categorical",
            "description": "Combat posture",
            "parameters": {"options": ["Aggressive", "Defensive"]},
        },
    ]

    stat_widget.populate(initial_stats)

    # Check cell widgets
    combo_0 = stat_widget._table.cellWidget(0, 2)
    assert isinstance(combo_0, QComboBox)
    assert combo_0.currentData() == "numeric"

    combo_1 = stat_widget._table.cellWidget(1, 2)
    assert isinstance(combo_1, QComboBox)
    assert combo_1.currentData() == "categorical"

    collected = stat_widget.collect_data()
    assert len(collected) == 2
    assert collected[0]["stat_id"] == "hp"
    assert collected[0]["value_type"] == "numeric"
    assert collected[0]["parameters"]["min"] == 0.0
    assert collected[0]["parameters"]["max"] == 100.0

    assert collected[1]["stat_id"] == "stance"
    assert collected[1]["value_type"] == "categorical"
    assert collected[1]["parameters"]["options"] == ["Aggressive", "Defensive"]


def test_change_stat_type_in_table(stat_widget):
    initial_stats = [
        {
            "stat_id": "karma",
            "name": "Karma",
            "value_type": "numeric",
            "description": "Good vs bad deeds",
            "parameters": {"min": -100.0, "max": 100.0},
        }
    ]
    stat_widget.populate(initial_stats)

    combo = stat_widget._table.cellWidget(0, 2)
    assert isinstance(combo, QComboBox)
    assert combo.currentData() == "numeric"

    changed_called = []
    stat_widget.changed.connect(lambda: changed_called.append(True))

    # Change to categorical
    idx_cat = combo.findData("categorical")
    assert idx_cat >= 0
    combo.setCurrentIndex(idx_cat)

    assert len(changed_called) == 1
    data = stat_widget.collect_data()
    assert data[0]["value_type"] == "categorical"

    # Change back to numeric
    idx_num = combo.findData("numeric")
    assert idx_num >= 0
    combo.setCurrentIndex(idx_num)

    assert len(changed_called) == 2
    data_back = stat_widget.collect_data()
    assert data_back[0]["value_type"] == "numeric"
    assert data_back[0]["parameters"]["min"] == 0.0
    assert data_back[0]["parameters"]["max"] == 100.0


def test_add_stat_from_input_row(stat_widget):
    stat_widget._id_input.setText("rank")
    stat_widget._name_input.setText("Military Rank")

    # Set input combo to categorical
    cat_idx = stat_widget._type_combo.findData("categorical")
    assert cat_idx >= 0
    stat_widget._type_combo.setCurrentIndex(cat_idx)

    stat_widget._on_add_clicked()

    assert stat_widget._table.rowCount() == 1
    combo = stat_widget._table.cellWidget(0, 2)
    assert isinstance(combo, QComboBox)
    assert combo.currentData() == "categorical"

    collected = stat_widget.collect_data()
    assert len(collected) == 1
    assert collected[0]["stat_id"] == "rank"
    assert collected[0]["value_type"] == "categorical"


def test_retranslate_ui_preserves_combos(stat_widget):
    initial_stats = [
        {
            "stat_id": "hp",
            "name": "Health",
            "value_type": "numeric",
            "description": "",
            "parameters": {"min": 0.0, "max": 100.0},
        },
        {
            "stat_id": "class",
            "name": "Class",
            "value_type": "categorical",
            "description": "",
            "parameters": {"options": ["Mage", "Warrior"]},
        },
    ]
    stat_widget.populate(initial_stats)

    stat_widget.retranslate_ui()

    combo_0 = stat_widget._table.cellWidget(0, 2)
    assert isinstance(combo_0, QComboBox)
    assert combo_0.currentData() == "numeric"

    combo_1 = stat_widget._table.cellWidget(1, 2)
    assert isinstance(combo_1, QComboBox)
    assert combo_1.currentData() == "categorical"
