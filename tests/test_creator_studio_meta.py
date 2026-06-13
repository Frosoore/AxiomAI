"""
tests/test_creator_studio_meta.py

Studio meta parsing must survive malformed user-editable values
(crash report 2026-06-12: world_tension_level held free text).
"""

import tomllib
from pathlib import Path

from ui.creator_studio_view import _meta_float


def test_meta_float_parses_valid_values() -> None:
    assert _meta_float({"k": "0.6"}, "k", 0.3) == 0.6
    assert _meta_float({"k": 0.6}, "k", 0.3) == 0.6
    assert _meta_float({"k": 1}, "k", 0.3) == 1.0


def test_meta_float_falls_back_on_malformed_values() -> None:
    assert _meta_float({"k": "cold war on many fronts"}, "k", 0.3) == 0.3
    assert _meta_float({"k": None}, "k", 0.7) == 0.7
    assert _meta_float({"k": ""}, "k", 1.0) == 1.0


def test_meta_float_falls_back_on_missing_key() -> None:
    assert _meta_float({}, "k", 0.3) == 0.3


def test_bundled_myria_tension_is_numeric() -> None:
    """Regression: the bundled universe shipped free text in a numeric field."""
    toml_path = Path(__file__).parent.parent / "universes" / "Myria" / "universe.toml"
    data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    tension = data["narrative"]["world_tension_level"]
    assert isinstance(tension, (int, float))
    assert 0.0 <= float(tension) <= 1.0
