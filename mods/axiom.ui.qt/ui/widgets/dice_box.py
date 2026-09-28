"""ui/widgets/dice_box.py

Desktop Qt widget for interactive tabletop dice rolls (D4, D6, D8, D10, D12, D20, D100).
"""

from __future__ import annotations

import random
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from core.localization import tr


class DiceBoxWidget(QWidget):
    """Widget allowing the player or GM to roll standard RPG dice."""

    dice_rolled = Signal(str, int, int)  # die_type, count, total

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        box = QGroupBox(tr("dice_box_title") if tr("dice_box_title") != "dice_box_title" else "Dice Box")
        box_layout = QVBoxLayout(box)

        # Quantity / Modifier row
        ctrl_layout = QHBoxLayout()
        ctrl_layout.addWidget(QLabel("Count:"))
        self._count_spin = QSpinBox()
        self._count_spin.setRange(1, 20)
        self._count_spin.setValue(1)
        ctrl_layout.addWidget(self._count_spin)

        ctrl_layout.addWidget(QLabel("+ Mod:"))
        self._mod_spin = QSpinBox()
        self._mod_spin.setRange(-50, 50)
        self._mod_spin.setValue(0)
        ctrl_layout.addWidget(self._mod_spin)
        box_layout.addLayout(ctrl_layout)

        # Dice buttons
        grid = QGridLayout()
        dice_types = [
            ("D4", 4),
            ("D6", 6),
            ("D8", 8),
            ("D10", 10),
            ("D12", 12),
            ("D20", 20),
            ("D100", 100),
        ]
        for i, (name, sides) in enumerate(dice_types):
            btn = QPushButton(name)
            btn.clicked.connect(lambda checked=False, s=sides, n=name: self._roll_die(n, s))
            grid.addWidget(btn, i // 4, i % 4)
        box_layout.addLayout(grid)

        # Result display
        self._result_label = QLabel("Roll: -")
        self._result_label.setAlignment(Qt.AlignCenter)
        self._result_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #4CAF50;")
        box_layout.addWidget(self._result_label)

        layout.addWidget(box)

    def _roll_die(self, name: str, sides: int) -> None:
        count = self._count_spin.value()
        mod = self._mod_spin.value()
        rolls = [random.randint(1, sides) for _ in range(count)]
        total = sum(rolls) + mod
        if count == 1 and mod == 0:
            self._result_label.setText(f"{name}: {total}")
        else:
            mod_str = f" + {mod}" if mod > 0 else (f" - {abs(mod)}" if mod < 0 else "")
            self._result_label.setText(f"{count}{name}{mod_str}: {total} ({rolls})")
        self.dice_rolled.emit(name, count, total)
