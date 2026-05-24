"""
tests/test_universe_meta.py

Unit tests for the Universe_Meta key/value store — verifies that per-universe
LLM parameters (temperature, top_p) survive a write/read round-trip.

Migrated (TICKET-001) from debug/test_db_logic.py into proper pytest coverage
using tmp_path isolation instead of a hard-coded debug_test.db file.
"""

from pathlib import Path

import pytest

from axiom.schema import create_universe_db, get_connection


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    """Provision a fresh universe db inside a temp directory."""
    path = str(tmp_path / "universe.db")
    create_universe_db(path)
    return path


def test_llm_params_survive_write_then_read(db_path: str) -> None:
    """llm_temperature/llm_top_p written to Universe_Meta read back unchanged."""
    temperature = 0.85
    top_p = 0.95

    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO Universe_Meta (key, value) VALUES (?, ?);",
            ("llm_temperature", str(temperature)),
        )
        conn.execute(
            "INSERT OR REPLACE INTO Universe_Meta (key, value) VALUES (?, ?);",
            ("llm_top_p", str(top_p)),
        )
        conn.commit()

    with get_connection(db_path) as conn:
        row_temp = conn.execute(
            "SELECT value FROM Universe_Meta WHERE key = 'llm_temperature';"
        ).fetchone()
        row_top_p = conn.execute(
            "SELECT value FROM Universe_Meta WHERE key = 'llm_top_p';"
        ).fetchone()

    assert float(row_temp[0]) == temperature
    assert float(row_top_p[0]) == top_p


def test_insert_or_replace_overwrites_existing_key(db_path: str) -> None:
    """A second INSERT OR REPLACE for the same key overwrites the prior value."""
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO Universe_Meta (key, value) VALUES ('llm_temperature', '0.5');"
        )
        conn.execute(
            "INSERT OR REPLACE INTO Universe_Meta (key, value) VALUES ('llm_temperature', '0.9');"
        )
        conn.commit()
        row = conn.execute(
            "SELECT value FROM Universe_Meta WHERE key = 'llm_temperature';"
        ).fetchone()

    assert row[0] == "0.9"
