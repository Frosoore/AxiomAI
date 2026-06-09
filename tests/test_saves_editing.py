"""tests/test_saves_editing.py

Tests de l'éditeur de saves (Pilier 2, Phase 6, `axiom.saves`) : matérialisation à
un point (tour/minute), export/import TOML, fork (journal tronqué). Pur moteur, sans LLM.

Garantie centrale : une save importée ou forkée reste **jouable** (State_Cache cohérent).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from axiom.compile import compile_universe
from axiom.db_helpers import create_new_save
from axiom.events import EventSourcer
from axiom.saves import (
    SaveError,
    export_save_state,
    fork_save,
    import_save_state,
    materialize_state,
    resolve_point,
)
from axiom.schema import get_connection


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def universe_db(tmp_path: Path) -> str:
    """Un univers compilé minimal (joueur + un item défini)."""
    root = tmp_path / "src"
    _write(root / "universe.toml", '[meta]\nname = "T"\n[narrative]\nsystem_prompt = "GM."\n')
    _write(root / "entities" / "player_1.toml",
           'entity_id = "player_1"\nentity_type = "player"\nname = "Hero"\n'
           '[stats]\nHealth = "100"\nStatus = "Alive"\n')
    _write(root / "items" / "sword.toml",
           'item_id = "sword"\nname = "Sword"\ncategory = "weapon"\n')
    return str(compile_universe(root, tmp_path / "u.db"))


@pytest.fixture
def played_save(universe_db: str) -> tuple[str, str]:
    """Une save avec 3 tours d'historique + Timeline (15/30/45 min)."""
    save_id = create_new_save(universe_db, "Hero", "Normal")
    es = EventSourcer(universe_db)
    es.append_events_batch([
        (save_id, 1, "stat_set", "player_1", {"entity_id": "player_1", "stat_key": "Health", "value": "90"}),
        (save_id, 2, "stat_set", "player_1", {"entity_id": "player_1", "stat_key": "Health", "value": "80"}),
        (save_id, 3, "stat_set", "player_1", {"entity_id": "player_1", "stat_key": "Health", "value": "70"}),
    ])
    with get_connection(universe_db) as conn:
        conn.executemany(
            "INSERT INTO Timeline (save_id, turn_id, in_game_time, description) VALUES (?, ?, ?, ?);",
            [(save_id, 1, 15, "t1"), (save_id, 2, 30, "t2"), (save_id, 3, 45, "t3")],
        )
        conn.commit()
    es.rebuild_state_cache(save_id)
    return universe_db, save_id


# ---------------------------------------------------------------------------
# Résolution de point + matérialisation
# ---------------------------------------------------------------------------

def test_resolve_point_turn_and_minute(played_save):
    db, save_id = played_save
    assert resolve_point(db, save_id) == 3                       # défaut = dernier tour
    assert resolve_point(db, save_id, at_turn=2) == 2
    assert resolve_point(db, save_id, at_minute=30) == 2         # tour à 30 min
    assert resolve_point(db, save_id, at_minute=20) == 1         # max tour <= 20 min
    assert resolve_point(db, save_id, at_minute=5) == 0          # rien avant 15 min


def test_resolve_point_rejects_both(played_save):
    db, save_id = played_save
    with pytest.raises(SaveError):
        resolve_point(db, save_id, at_turn=1, at_minute=1)


def test_materialize_current(played_save):
    db, save_id = played_save
    state = materialize_state(db, save_id)
    assert state["entities"]["player_1"]["Health"] == "70"      # dernier état
    assert state["entities"]["player_1"]["Status"] == "Alive"   # base d'univers conservée
    assert state["point"] == {"turn_id": 3, "in_game_minutes": 45}


def test_materialize_at_turn(played_save):
    db, save_id = played_save
    assert materialize_state(db, save_id, at_turn=2)["entities"]["player_1"]["Health"] == "80"
    assert materialize_state(db, save_id, at_turn=1)["entities"]["player_1"]["Health"] == "90"


def test_materialize_at_minute(played_save):
    db, save_id = played_save
    s = materialize_state(db, save_id, at_minute=30)
    assert s["entities"]["player_1"]["Health"] == "80"
    assert s["point"]["turn_id"] == 2


# ---------------------------------------------------------------------------
# Export / import
# ---------------------------------------------------------------------------

def test_export_import_roundtrip(played_save, tmp_path: Path):
    db, save_id = played_save
    out = export_save_state(db, save_id, tmp_path / "s.toml")
    assert out.exists()

    new_id = import_save_state(db, out)
    assert new_id != save_id
    imported = materialize_state(db, new_id)
    assert imported["entities"]["player_1"]["Health"] == "70"
    assert imported["entities"]["player_1"]["Status"] == "Alive"
    assert imported["save"]["player_name"] == "Hero"


def test_import_hand_written(universe_db: str, tmp_path: Path):
    """Un save_state.toml écrit à la main (humain/LLM) crée une save jouable."""
    toml = tmp_path / "custom.toml"
    toml.write_text(
        '[save]\nplayer_name = "Garen"\ndifficulty = "Hardcore"\nplayer_persona = "Vétéran."\n'
        '[point]\nin_game_minutes = 600\n'
        '[state.player_1]\nHealth = "42"\nStatus = "Wounded"\n'
        '[[inventory]]\nentity_id = "player_1"\nitem_id = "sword"\nquantity = 1\n',
        encoding="utf-8",
    )
    save_id = import_save_state(universe_db, toml)
    state = materialize_state(universe_db, save_id)
    assert state["save"]["player_name"] == "Garen"
    assert state["save"]["difficulty"] == "Hardcore"
    assert state["entities"]["player_1"]["Health"] == "42"
    assert state["point"]["in_game_minutes"] == 600
    assert state["inventory"] == [{"entity_id": "player_1", "item_id": "sword", "quantity": 1}]


def test_modifiers_roundtrip(universe_db: str, tmp_path: Path):
    """Les modifiers (par-save depuis TICKET-024) survivent à export→import."""
    from axiom.modifiers import ModifierProcessor

    save_id = create_new_save(universe_db, "Hero", "Normal")
    ModifierProcessor(universe_db).add_modifier(save_id, "player_1", "Health", 5.0, 30)

    out = export_save_state(universe_db, save_id, tmp_path / "m.toml")
    assert 'modifiers' in out.read_text(encoding="utf-8")

    new_id = import_save_state(universe_db, out)
    state = materialize_state(universe_db, new_id)
    assert state["modifiers"] == [
        {"entity_id": "player_1", "stat_key": "Health", "delta": 5.0, "minutes_remaining": 30}
    ]


def test_import_name_override(universe_db: str, tmp_path: Path):
    toml = tmp_path / "s.toml"
    toml.write_text('[save]\nplayer_name = "X"\ndifficulty = "Normal"\n'
                    '[state.player_1]\nHealth = "1"\n', encoding="utf-8")
    save_id = import_save_state(universe_db, toml, player_name="Override")
    assert materialize_state(universe_db, save_id)["save"]["player_name"] == "Override"


def test_imported_save_is_playable(universe_db: str, tmp_path: Path):
    """La save importée est jouable : Session se construit et lit l'état."""
    toml = tmp_path / "s.toml"
    toml.write_text('[save]\nplayer_name = "P"\ndifficulty = "Normal"\n'
                    '[state.player_1]\nHealth = "55"\n', encoding="utf-8")
    save_id = import_save_state(universe_db, toml)

    from axiom.session import Session

    class FakeLLM:
        def is_available(self):
            return True

    session = Session(universe_db, save_id, llm=FakeLLM(), mode="Normal")
    stats = session.current_stats()
    assert stats["player_1"]["Health"] == "55"


def test_import_invalid_item_fk(universe_db: str, tmp_path: Path):
    """Un item inconnu (FK) doit échouer proprement en SaveError."""
    toml = tmp_path / "s.toml"
    toml.write_text('[save]\nplayer_name = "P"\ndifficulty = "Normal"\n'
                    '[state.player_1]\nHealth = "1"\n'
                    '[[inventory]]\nentity_id = "player_1"\nitem_id = "ghost_item"\nquantity = 1\n',
                    encoding="utf-8")
    with pytest.raises(SaveError):
        import_save_state(universe_db, toml)


# ---------------------------------------------------------------------------
# Fork
# ---------------------------------------------------------------------------

def test_fork_truncates_journal(played_save):
    db, save_id = played_save
    new_id = fork_save(db, save_id, at_turn=2)

    # Le fork a l'état du tour 2 et un journal tronqué.
    assert materialize_state(db, new_id)["entities"]["player_1"]["Health"] == "80"
    with get_connection(db) as conn:
        max_turn = conn.execute(
            "SELECT MAX(turn_id) FROM Event_Log WHERE save_id = ?;", (new_id,)
        ).fetchone()[0]
    assert max_turn == 2
    # La save source est intacte.
    assert materialize_state(db, save_id)["entities"]["player_1"]["Health"] == "70"


def test_fork_by_minute(played_save):
    db, save_id = played_save
    new_id = fork_save(db, save_id, at_minute=15)
    assert materialize_state(db, new_id)["entities"]["player_1"]["Health"] == "90"


def test_fork_rewind_still_works(played_save):
    """Après fork, le rewind fonctionne toujours sur la nouvelle save."""
    db, save_id = played_save
    new_id = fork_save(db, save_id, at_turn=3)
    from axiom.checkpoint import CheckpointManager

    cm = CheckpointManager(db)
    assert cm.list_checkpoints(new_id) == [1, 2, 3]
    cm.rewind(new_id, 1)
    assert materialize_state(db, new_id)["entities"]["player_1"]["Health"] == "90"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def test_cli_save_export_import_fork(played_save, tmp_path: Path):
    from axiom.cli.main import build_parser

    db, save_id = played_save
    parser = build_parser()

    # save-show
    args = parser.parse_args(["save-show", db, save_id])
    assert args.func(args) == 0

    # save-export
    out = tmp_path / "s.toml"
    args = parser.parse_args(["save-export", db, save_id, str(out), "--turn", "2"])
    assert args.func(args) == 0
    assert out.exists()

    # save-import
    args = parser.parse_args(["save-import", db, str(out), "--name", "Clone"])
    assert args.func(args) == 0

    # save-fork
    args = parser.parse_args(["save-fork", db, save_id, "--minute", "30"])
    assert args.func(args) == 0
