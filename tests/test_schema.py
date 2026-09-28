"""
tests/test_schema.py

Unit tests for database/schema.py — verifies that create_universe_db()
provisions a file with the exact set of required tables and expected columns.
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from axiom.schema import create_universe_db, EXPECTED_TABLES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _table_names(conn: sqlite3.Connection) -> set[str]:
    """Return the set of user-defined table names in the connected database."""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
    ).fetchall()
    return {row[0] for row in rows}


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    """Return the set of column names for the given table."""
    rows = conn.execute(f"PRAGMA table_info({table});").fetchall()
    return {row[1] for row in rows}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path: Path) -> str:
    """Provide a path inside a temporary directory for a fresh universe db."""
    return str(tmp_path / "test_universe.db")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCreateUniverseDb:
    def test_creates_file(self, tmp_db: str) -> None:
        """create_universe_db writes the db file to disk."""
        create_universe_db(tmp_db)
        assert Path(tmp_db).exists(), "Database file was not created"

    def test_idempotent(self, tmp_db: str) -> None:
        """Calling create_universe_db twice must not raise."""
        create_universe_db(tmp_db)
        create_universe_db(tmp_db)  # should not raise

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        """create_universe_db creates any missing parent directories in the path."""
        nested = str(tmp_path / "a" / "b" / "c" / "universe.db")
        create_universe_db(nested)
        assert Path(nested).exists()

    def test_all_tables_present(self, tmp_db: str) -> None:
        """The created schema contains exactly EXPECTED_TABLES — no missing or
        extra tables."""
        create_universe_db(tmp_db)
        with sqlite3.connect(tmp_db) as conn:
            tables = _table_names(conn)
        assert tables == EXPECTED_TABLES, (
            f"Missing tables: {EXPECTED_TABLES - tables} | "
            f"Unexpected tables: {tables - EXPECTED_TABLES}"
        )

    # --- Per-table column checks ---

    def test_universe_meta_columns(self, tmp_db: str) -> None:
        """Universe_Meta exposes the key/value columns."""
        create_universe_db(tmp_db)
        with sqlite3.connect(tmp_db) as conn:
            cols = _column_names(conn, "Universe_Meta")
        assert {"key", "value"}.issubset(cols)

    def test_entities_columns(self, tmp_db: str) -> None:
        """Entities exposes the entity_id/entity_type/name/is_active columns."""
        create_universe_db(tmp_db)
        with sqlite3.connect(tmp_db) as conn:
            cols = _column_names(conn, "Entities")
        assert {"entity_id", "entity_type", "name", "is_active"}.issubset(cols)

    def test_entity_stats_columns(self, tmp_db: str) -> None:
        """Entity_Stats exposes the entity_id/stat_key/stat_value columns."""
        create_universe_db(tmp_db)
        with sqlite3.connect(tmp_db) as conn:
            cols = _column_names(conn, "Entity_Stats")
        assert {"entity_id", "stat_key", "stat_value"}.issubset(cols)

    def test_rules_columns(self, tmp_db: str) -> None:
        """Rules exposes the rule_id/priority/conditions/actions/target_entity columns."""
        create_universe_db(tmp_db)
        with sqlite3.connect(tmp_db) as conn:
            cols = _column_names(conn, "Rules")
        assert {"rule_id", "priority", "conditions", "actions", "target_entity"}.issubset(cols)

    def test_active_modifiers_columns(self, tmp_db: str) -> None:
        """Active_Modifiers exposes the modifier_id/entity_id/stat_key/delta/
        minutes_remaining columns."""
        create_universe_db(tmp_db)
        with sqlite3.connect(tmp_db) as conn:
            cols = _column_names(conn, "Active_Modifiers")
        assert {"modifier_id", "entity_id", "stat_key", "delta", "minutes_remaining"}.issubset(cols)

    def test_saves_columns(self, tmp_db: str) -> None:
        """Saves exposes the save_id/player_name/difficulty/last_updated columns."""
        create_universe_db(tmp_db)
        with sqlite3.connect(tmp_db) as conn:
            cols = _column_names(conn, "Saves")
        assert {"save_id", "player_name", "difficulty", "last_updated"}.issubset(cols)

    def test_event_log_columns(self, tmp_db: str) -> None:
        """Event_Log exposes the event_id/save_id/turn_id/event_type/
        target_entity/payload columns."""
        create_universe_db(tmp_db)
        with sqlite3.connect(tmp_db) as conn:
            cols = _column_names(conn, "Event_Log")
        assert {"event_id", "save_id", "turn_id", "event_type", "target_entity", "payload"}.issubset(cols)

    def test_state_cache_columns(self, tmp_db: str) -> None:
        """State_Cache exposes the save_id/entity_id/stat_key/stat_value columns."""
        create_universe_db(tmp_db)
        with sqlite3.connect(tmp_db) as conn:
            cols = _column_names(conn, "State_Cache")
        assert {"save_id", "entity_id", "stat_key", "stat_value"}.issubset(cols)

    def test_entity_type_constraint(self, tmp_db: str) -> None:
        """Entities.entity_type must reference Entity_Types (unknown ids rejected)."""
        create_universe_db(tmp_db)
        with sqlite3.connect(tmp_db) as conn:
            conn.execute("PRAGMA foreign_keys=ON;")
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO Entities (entity_id, entity_type, name) VALUES (?, ?, ?);",
                    ("e1", "monster", "Goblin"),
                )

    def test_saves_difficulty_accepts_custom_modes(self, tmp_db: str) -> None:
        """Saves.difficulty is unconstrained to support custom game modes/mods (Phase 0e)."""
        create_universe_db(tmp_db)
        with sqlite3.connect(tmp_db) as conn:
            conn.execute(
                "INSERT INTO Saves (save_id, player_name, difficulty, last_updated) VALUES (?, ?, ?, ?);",
                ("s1", "Hero", "CustomModDifficulty", "2026-01-01T00:00:00"),
            )
            row = conn.execute("SELECT difficulty FROM Saves WHERE save_id = 's1';").fetchone()
            assert row[0] == "CustomModDifficulty"

    def test_foreign_keys_enforced(self, tmp_db: str) -> None:
        """Entity_Stats must reject inserts referencing non-existent entity_id."""
        create_universe_db(tmp_db)
        with sqlite3.connect(tmp_db) as conn:
            conn.execute("PRAGMA foreign_keys=ON;")
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO Entity_Stats VALUES (?, ?, ?);",
                    ("ghost_entity", "HP", "100"),
                )


class TestModMigrations:
    """Test suite for Mod_Schema_Versions and apply_mod_migrations (Phase 0e)."""

    def test_apply_mod_migrations_sequential(self, tmp_db: str) -> None:
        from axiom.schema import apply_mod_migrations

        create_universe_db(tmp_db)

        def m0_to_1(conn: sqlite3.Connection) -> None:
            conn.execute("CREATE TABLE Test_Hunger (entity_id TEXT PRIMARY KEY, hunger_level REAL);")

        def m1_to_2(conn: sqlite3.Connection) -> None:
            conn.execute("ALTER TABLE Test_Hunger ADD COLUMN max_hunger REAL DEFAULT 100.0;")

        migrations = {0: m0_to_1, 1: m1_to_2}
        apply_mod_migrations(tmp_db, "comm.hunger", 2, migrations)

        with sqlite3.connect(tmp_db) as conn:
            row = conn.execute("SELECT schema_version, installed_at FROM Mod_Schema_Versions WHERE mod_id = 'comm.hunger';").fetchone()
            assert row is not None
            assert row[0] == 2
            assert "T" in row[1]  # ISO timestamp

            cols = {c[1] for c in conn.execute("PRAGMA table_info(Test_Hunger);").fetchall()}
            assert cols == {"entity_id", "hunger_level", "max_hunger"}

        # Running again with same target_version is a no-op
        apply_mod_migrations(tmp_db, "comm.hunger", 2, migrations)

    def test_apply_mod_migrations_missing_step_raises(self, tmp_db: str) -> None:
        from axiom.schema import apply_mod_migrations

        create_universe_db(tmp_db)
        with pytest.raises(ValueError, match="Missing migration step 0 -> 1"):
            apply_mod_migrations(tmp_db, "comm.broken", 2, {})
