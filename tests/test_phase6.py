"""
tests/test_phase6.py

Unit tests for Phase 6: Bug Fixes & Lore Book Expansion.

Covers:
  - Lore_Book table provisioned by create_universe_db
  - migrate_lore_book_table() is idempotent
  - _format_lore_book_block() grouping and formatting
  - build_narrative_prompt / build_mini_dico_prompt accept lore_book
  - DbWorker.save_full_universe atomicity (single connection, all data saved)
  - ChatDisplayWidget JSON fence filtering (_flush_token_buffer)
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from axiom.schema import create_universe_db, migrate_lore_book_table
from axiom.prompts import (
    _format_lore_book_block,
    build_mini_dico_prompt,
    build_narrative_prompt,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_db(tmp_path: Path) -> str:
    """Return path to a freshly provisioned universe database."""
    db = str(tmp_path / "test.db")
    create_universe_db(db)
    return db


# ---------------------------------------------------------------------------
# 6.3 — Lore_Book schema
# ---------------------------------------------------------------------------

class TestLoreBookSchema:
    def test_lore_book_table_created(self, tmp_db: str) -> None:
        """create_universe_db must provision Lore_Book."""
        with sqlite3.connect(tmp_db) as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='Lore_Book';"
            ).fetchone()
        assert row is not None, "Lore_Book table must exist after create_universe_db"

    def test_lore_book_columns(self, tmp_db: str) -> None:
        """Lore_Book must have entry_id, category, name, content columns."""
        with sqlite3.connect(tmp_db) as conn:
            info = conn.execute("PRAGMA table_info(Lore_Book);").fetchall()
        col_names = {row[1] for row in info}
        assert {"entry_id", "category", "name", "content"} <= col_names

    def test_migrate_lore_book_idempotent(self, tmp_db: str) -> None:
        """migrate_lore_book_table must succeed even if table already exists."""
        migrate_lore_book_table(tmp_db)
        migrate_lore_book_table(tmp_db)  # second call must not raise

    def test_migrate_lore_book_creates_table_on_old_db(self, tmp_path: Path) -> None:
        """migrate_lore_book_table creates the table if it was absent."""
        db = str(tmp_path / "old.db")
        # Provision without Lore_Book (simulate old database)
        with sqlite3.connect(db) as conn:
            conn.execute("CREATE TABLE Universe_Meta (key TEXT PRIMARY KEY, value TEXT);")
        migrate_lore_book_table(db)
        with sqlite3.connect(db) as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='Lore_Book';"
            ).fetchone()
        assert row is not None

    def test_insert_and_read_lore_book_entry(self, tmp_db: str) -> None:
        """Lore_Book accepts valid inserts and returns them."""
        with sqlite3.connect(tmp_db) as conn:
            conn.execute(
                "INSERT INTO Lore_Book (entry_id, category, name, content) "
                "VALUES (?, ?, ?, ?);",
                ("e1", "Faction", "Red Guard", "Elite soldiers of the Empire."),
            )
            conn.commit()
        with sqlite3.connect(tmp_db) as conn:
            row = conn.execute(
                "SELECT category, name, content FROM Lore_Book WHERE entry_id='e1';"
            ).fetchone()
        assert row == ("Faction", "Red Guard", "Elite soldiers of the Empire.")


# ---------------------------------------------------------------------------
# 6.5 — Lore Book prompt formatting
# ---------------------------------------------------------------------------

class TestFormatLoreBookBlock:
    def test_empty_returns_empty_string(self) -> None:
        """An empty lore list formats to an empty string (no header)."""
        assert _format_lore_book_block([]) == ""

    def test_single_entry_formatted(self) -> None:
        """A single entry renders its category, name and content headings."""
        entries = [
            {"entry_id": "e1", "category": "Magic", "name": "Arcane Flame", "content": "Burns eternally."}
        ]
        result = _format_lore_book_block(entries)
        assert "### Category: Magic" in result
        assert "#### Arcane Flame" in result
        assert "Burns eternally." in result

    def test_multiple_entries_grouped_by_category(self) -> None:
        """Entries sharing a category are grouped under a single category heading."""
        entries = [
            {"entry_id": "e1", "category": "Faction", "name": "Red Guard", "content": "Soldiers."},
            {"entry_id": "e2", "category": "Faction", "name": "Blue Fleet", "content": "Sailors."},
            {"entry_id": "e3", "category": "Location", "name": "The Keep", "content": "A fortress."},
        ]
        result = _format_lore_book_block(entries)
        assert result.count("### Category: Faction") == 1
        assert "#### Red Guard" in result
        assert "#### Blue Fleet" in result
        assert "### Category: Location" in result

    def test_missing_category_defaults_to_general(self) -> None:
        """An entry with a blank category is filed under 'General'."""
        entries = [{"entry_id": "e1", "category": "", "name": "Mystery", "content": "Unknown."}]
        result = _format_lore_book_block(entries)
        assert "### Category: General" in result

    def test_lore_book_section_header_present(self) -> None:
        """A non-empty block starts with the '=== LORE BOOK ===' header."""
        entries = [{"entry_id": "e1", "category": "X", "name": "Y", "content": "Z"}]
        result = _format_lore_book_block(entries)
        assert result.startswith("=== LORE BOOK ===")


class TestBuildNarrativePromptLoreBook:
    def test_lore_book_injected_into_system_message(self) -> None:
        """A supplied lore_book is rendered into the narrative system message."""
        entries = [{"entry_id": "e1", "category": "Faction", "name": "Guard", "content": "Soldiers."}]
        msgs = build_narrative_prompt(
            universe_system_prompt="You are narrator.",
            entity_stats_block="(no entities)",
            rag_chunks=[],
            history=[],
            intents={"player": "Hello"},
            lore_book=entries,
        )
        system_content = msgs[0]["content"]
        assert "=== LORE BOOK ===" in system_content
        assert "Faction" in system_content

    def test_empty_lore_book_not_injected(self) -> None:
        """An empty lore_book adds no LORE BOOK section."""
        msgs = build_narrative_prompt(
            universe_system_prompt="Narrator.",
            entity_stats_block="(no entities)",
            rag_chunks=[],
            history=[],
            intents={"player": "Hi"},
            lore_book=[],
        )
        assert "=== LORE BOOK ===" not in msgs[0]["content"]

    def test_none_lore_book_not_injected(self) -> None:
        """A None lore_book adds no LORE BOOK section."""
        msgs = build_narrative_prompt(
            universe_system_prompt="Narrator.",
            entity_stats_block="(no entities)",
            rag_chunks=[],
            history=[],
            intents={"player": "Hi"},
            lore_book=None,
        )
        assert "=== LORE BOOK ===" not in msgs[0]["content"]


class TestBuildMiniDicoPromptLoreBook:
    def test_lore_book_included_in_user_message(self) -> None:
        """A supplied lore_book is rendered into the mini-dico user message."""
        entries = [{"entry_id": "e1", "category": "Magic", "name": "Fireball", "content": "Hot."}]
        msgs = build_mini_dico_prompt("What is Fireball?", [], lore_book=entries)
        user_content = msgs[1]["content"]
        assert "=== LORE BOOK ===" in user_content
        assert "Fireball" in user_content

    def test_no_lore_book_still_works(self) -> None:
        """Omitting lore_book still produces a valid two-message prompt."""
        msgs = build_mini_dico_prompt("What is magic?", ["Magic is power."])
        assert len(msgs) == 2
        assert "Magic is power." in msgs[1]["content"]


# ---------------------------------------------------------------------------
# 6.2 — save_full_universe atomicity
# ---------------------------------------------------------------------------

class TestSaveFullUniverse:
    def test_entities_rules_meta_lore_book_saved_atomically(
        self, tmp_db: str, tmp_path: Path
    ) -> None:
        """save_full_universe must persist all four data groups in one pass."""
        from workers.db_worker import DbWorker

        entities = [
            {"entity_id": "hero", "entity_type": "player", "name": "Aria",
             "stats": {"HP": "100", "Gold": "50"}},
        ]
        rules: list[dict] = []
        meta = {"universe_name": "TestWorld", "global_lore": "Ancient magic rules."}
        lore_book = [
            {"entry_id": "lb1", "category": "Faction", "name": "Empire",
             "content": "The ruling power."},
        ]

        # Provision a Saves row so FK constraints are satisfied if needed
        with sqlite3.connect(tmp_db) as conn:
            conn.execute(
                "INSERT INTO Saves (save_id, player_name, difficulty, last_updated) "
                "VALUES ('s1', 'Aria', 'Normal', '2026-01-01T00:00:00');"
            )

        worker = DbWorker(tmp_db)
        from PySide6.QtCore import QCoreApplication, Qt
        import time
        done = []
        worker.save_complete.connect(lambda: done.append(True), Qt.QueuedConnection)
        worker.save_full_universe(entities, rules, meta, lore_book)
        errors: list[str] = []
        worker.error_occurred.connect(errors.append)

        start = time.time()
        while not done and not errors and time.time() - start < 5:
            QCoreApplication.processEvents()
            time.sleep(0.01)

        assert errors == [], f"save_full_universe emitted error: {errors}"

        with sqlite3.connect(tmp_db) as conn:
            # Entity persisted
            row = conn.execute(
                "SELECT name FROM Entities WHERE entity_id='hero';"
            ).fetchone()
            assert row is not None and row[0] == "Aria"

            # Stats persisted
            hp = conn.execute(
                "SELECT stat_value FROM Entity_Stats WHERE entity_id='hero' AND stat_key='HP';"
            ).fetchone()
            assert hp is not None and hp[0] == "100"

            # Meta persisted
            name = conn.execute(
                "SELECT value FROM Universe_Meta WHERE key='universe_name';"
            ).fetchone()
            assert name is not None and name[0] == "TestWorld"

            # Lore Book persisted
            lb = conn.execute(
                "SELECT name FROM Lore_Book WHERE entry_id='lb1';"
            ).fetchone()
            assert lb is not None and lb[0] == "Empire"


# ---------------------------------------------------------------------------
# 6.6 — JSON fence filtering in ChatDisplayWidget
# ---------------------------------------------------------------------------

class TestJsonFenceFiltering:
    """Tests for the _flush_token_buffer fence-detection logic.

    We instantiate a bare ChatDisplayWidget-like object to avoid needing
    a live QApplication.  Instead we test the pure buffer logic by calling
    _flush_token_buffer directly after setting up _token_buf / _in_json_fence.
    """

    class _FakeFlusher:
        """Minimal stand-in exposing just the fence-filtering logic."""
        _JSON_FENCES = (("~~~json", "~~~"), ("```json", "```"))

        def __init__(self):
            self._token_buf = ""
            self._in_json_fence = False
            self._json_fence_close = "~~~"

        def feed(self, token: str) -> str:
            self._token_buf += token
            from ui.widgets.chat_display import ChatDisplayWidget
            # Borrow the method directly
            return ChatDisplayWidget._flush_token_buffer(self)  # type: ignore[arg-type]

    def _make(self):
        return self._FakeFlusher()

    def test_plain_text_eventually_passes_through(self) -> None:
        """Plain text is visible once enough chars arrive to clear the watch window."""
        f = self._make()
        # Feed enough text so the safe_len guard passes content through.
        # Guard is len("~~~json")-1 = 6 chars held back.
        result = f.feed("Hello world — long enough to flush!")
        assert "Hello" in result

    def test_json_block_fully_suppressed(self) -> None:
        """A complete ~~~json block is fully removed from the streamed output."""
        f = self._make()
        text = "Narrative text.\n~~~json\n{\"foo\":1}\n~~~\nMore text. Extra suffix here."
        result = ""
        for ch in text:
            result += f.feed(ch)
        assert "~~~json" not in result
        assert "foo" not in result
        assert "Narrative text." in result

    def test_text_after_fence_visible(self) -> None:
        """Text after a closed fence becomes visible once the guard window clears."""
        f = self._make()
        # Payload ends with > 6 extra chars so the guard releases "After."
        payload = "Before.\n~~~json\n{}\n~~~\nAfter. And more padding here."
        result = ""
        for ch in payload:
            result += f.feed(ch)
        assert "After." in result
        assert "{}" not in result

    def test_no_fence_text_unchanged(self) -> None:
        """Text with no JSON fence streams through unchanged."""
        f = self._make()
        result = ""
        for ch in "Pure narrative, no JSON here at all!":
            result += f.feed(ch)
        assert "Pure narrative" in result

    def test_partial_open_fence_not_emitted_prematurely(self) -> None:
        """Tilde chars that could be a fence opener must not be emitted early."""
        f = self._make()
        r1 = f.feed("~")
        r2 = f.feed("~")
        r3 = f.feed("~")
        assert "~~~" not in (r1 + r2 + r3)

    def test_unclosed_fence_dropped_on_force_flush(self) -> None:
        """An unclosed JSON fence is suppressed during streaming and discarded on final flush."""
        f = self._make()
        result = ""
        for ch in "Prose.\n~~~json\n{\"key\": \"val":
            result += f.feed(ch)
        # Suppressed so far
        assert "key" not in result
        
        # Now force final flush
        from ui.widgets.chat_display import ChatDisplayWidget
        f._token_buf += "" # nothing new
        final = ChatDisplayWidget._flush_token_buffer(f, force=True)
        assert "key" not in final
        assert "Prose." in result or "Prose." in final

    def test_raw_json_start_dropped_on_force_flush(self) -> None:
        """A raw JSON start (\n{) is suppressed during streaming and discarded on final flush."""
        f = self._make()
        result = ""
        for ch in "Prose.\n{\n  \"state_changes\": []":
            result += f.feed(ch)
        assert "state_changes" not in result
        
        from ui.widgets.chat_display import ChatDisplayWidget
        final = ChatDisplayWidget._flush_token_buffer(f, force=True)
        assert "state_changes" not in final
        assert "Prose." in result or "Prose." in final


# ---------------------------------------------------------------------------
# 6.7 — UI Form Synchronization
# ---------------------------------------------------------------------------

class TestEntityEditorSync:
    """L'éditeur d'entités ne doit pas perdre les éditions en cours (flush UI→données).

    Tests sur de vrais widgets (QApplication via conftest, qtbot via pytest-qt).
    L'API réelle est `_sync_stats_from_ui` (flush) + `_on_row_selected` (lit `currentRow`).
    """

    def _widget(self, qtbot):
        from ui.widgets.entity_editor import EntityEditorWidget
        w = EntityEditorWidget()
        qtbot.addWidget(w)
        return w

    def test_collect_data_flushes_stat_edit(self, qtbot) -> None:
        """Une valeur de stat éditée dans la table est capturée par collect_data()."""
        from PySide6.QtWidgets import QLineEdit

        w = self._widget(qtbot)
        w.populate([{"entity_id": "hero", "entity_type": "player", "name": "Hero",
                     "description": "", "stats": {"HP": "10"}}])
        w._table.setCurrentCell(0, 2)            # sélectionne la ligne 0 → charge ses stats
        val = w._stats_table.cellWidget(0, 1)    # QLineEdit (stat hors définitions)
        assert isinstance(val, QLineEdit)
        val.setText("99")
        assert w.collect_data()[0]["stats"]["HP"] == "99"

    def test_row_switch_preserves_previous_edit(self, qtbot) -> None:
        """Changer de ligne flushe l'édition de la ligne précédente (pas de perte)."""
        w = self._widget(qtbot)
        w.populate([
            {"entity_id": "e0", "entity_type": "npc", "name": "E0", "description": "", "stats": {"HP": "10"}},
            {"entity_id": "e1", "entity_type": "npc", "name": "E1", "description": "", "stats": {}},
        ])
        w._table.setCurrentCell(0, 2)
        w._stats_table.cellWidget(0, 1).setText("77")
        w._table.setCurrentCell(1, 2)            # switch → doit flusher la ligne 0
        assert w.collect_data()[0]["stats"]["HP"] == "77"

    def test_selected_row_advances_after_selection(self, qtbot) -> None:
        """Sélectionner une ligne met à jour `_selected_row`."""
        w = self._widget(qtbot)
        w.populate([
            {"entity_id": "e0", "entity_type": "npc", "name": "A", "description": "", "stats": {}},
            {"entity_id": "e1", "entity_type": "npc", "name": "B", "description": "", "stats": {}},
        ])
        w._table.setCurrentCell(1, 2)
        assert w._selected_row == 1

    def test_change_entity_type(self, qtbot) -> None:
        """Changer le type dans le combobox met à jour les données et émet le signal changed."""
        from PySide6.QtWidgets import QComboBox

        w = self._widget(qtbot)
        w.populate([
            {"entity_id": "e0", "entity_type": "npc", "name": "A", "description": "", "stats": {}},
        ])
        
        # Verify initial type
        combo = w._table.cellWidget(0, 1)
        assert isinstance(combo, QComboBox)
        assert combo.currentData() == "npc"
        
        # Connect changed signal to a spy/counter
        changed_count = 0
        def on_changed():
            nonlocal changed_count
            changed_count += 1
        w.changed.connect(on_changed)
        
        # Change type to player
        idx = combo.findData("player")
        assert idx >= 0
        combo.setCurrentIndex(idx)
        
        # Verify value updated in entities data and signal emitted
        assert w._entities_data[0]["entity_type"] == "player"
        assert w.collect_data()[0]["entity_type"] == "player"
        assert changed_count == 1


class TestRuleEditorSync:
    """L'éditeur de règles : round-trip, navigation, et flush depuis la table.

    Tests sur de vrais widgets. API réelle : `_sync_subtables_from_ui` (flush) +
    `_on_row_selected` (lit `currentRow`), table principale col 0/1/2 = id/priority/target.
    """

    def _widget(self, qtbot):
        from ui.widgets.rule_editor import RuleEditorWidget
        w = RuleEditorWidget()
        qtbot.addWidget(w)
        return w

    @staticmethod
    def _rules():
        return [
            {"rule_id": "r0", "priority": 0, "target_entity": "*",
             "conditions": {"operator": "AND", "clauses": []}, "actions": []},
            {"rule_id": "r1", "priority": 1, "target_entity": "*",
             "conditions": {"operator": "AND", "clauses": []}, "actions": []},
        ]

    def test_collect_data_roundtrips_rules(self, qtbot) -> None:
        """collect_data() restitue les règles peuplées (ids + priorités)."""
        w = self._widget(qtbot)
        w.populate(self._rules())
        out = w.collect_data()
        assert [r["rule_id"] for r in out] == ["r0", "r1"]
        assert [r["priority"] for r in out] == [0, 1]

    def test_selected_row_advances_after_selection(self, qtbot) -> None:
        """Sélectionner une règle met à jour `_selected_row`."""
        w = self._widget(qtbot)
        w.populate(self._rules())
        w._table.setCurrentCell(1, 0)
        assert w._selected_row == 1

    def test_collect_data_flushes_main_table_edit(self, qtbot) -> None:
        """Une édition de la table principale (target_entity) est capturée par collect_data()."""
        from PySide6.QtWidgets import QTableWidgetItem

        w = self._widget(qtbot)
        w.populate(self._rules())
        w._table.setItem(0, 2, QTableWidgetItem("player_1"))
        assert w.collect_data()[0]["target_entity"] == "player_1"
