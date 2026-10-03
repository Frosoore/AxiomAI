"""tests/test_modpack_persistence.py

Tests for K10:
- Active modpack persistence in save databases (Save_Meta).
- Modpack compatibility checks (missing, mismatched, extra mods).
- .axiomsave packaging embedding modpack.json and unpack_save restoring it.
- Session warning and modpack_compatibility attribute.
"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import zipfile

import pytest

from axiom.compile import compile_universe
from axiom.savestore import (
    check_save_modpack_compatibility,
    create_save,
    get_save_modpack,
    pack_save,
    unpack_save,
)
from axiom.schema import create_universe_db, get_connection


def test_modpack_recorded_and_checked(tmp_path: Path):
    db_file = tmp_path / "game.db"
    create_universe_db(str(db_file))

    # Manually seed a save with active_modpack in Save_Meta
    expected_mp = [
        {"id": "axiom.turn", "version": "1.0.0", "name": "Axiom Turn"},
        {"id": "axiom.world", "version": "1.0.0", "name": "Axiom World"},
        {"id": "community.alchemy", "version": "0.2.0", "name": "Alchemy"},
    ]
    with get_connection(str(db_file)) as conn:
        conn.execute(
            "INSERT INTO Saves (save_id, player_name, difficulty, last_updated) "
            "VALUES ('s1', 'Hero', 'Normal', '2026-10-03T12:00:00Z');",
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS Save_Meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);"
        )
        conn.execute(
            "INSERT OR REPLACE INTO Save_Meta (key, value) VALUES ('active_modpack', ?);",
            (json.dumps(expected_mp),),
        )

    # 1. get_save_modpack
    loaded_mp = get_save_modpack(str(db_file))
    assert loaded_mp == expected_mp

    # 2. Check compatibility: perfectly matching
    curr_matching = [
        {"id": "axiom.turn", "version": "1.0.0"},
        {"id": "axiom.world", "version": "1.0.0"},
        {"id": "community.alchemy", "version": "0.2.0"},
    ]
    res = check_save_modpack_compatibility(str(db_file), curr_matching)
    assert res["compatible"] is True
    assert res["missing_mods"] == []
    assert res["version_mismatches"] == []

    # 3. Check compatibility: missing mod
    curr_missing = [
        {"id": "axiom.turn", "version": "1.0.0"},
        {"id": "axiom.world", "version": "1.0.0"},
    ]
    res_missing = check_save_modpack_compatibility(str(db_file), curr_missing)
    assert res_missing["compatible"] is False
    assert "community.alchemy" in res_missing["missing_mods"]

    # 4. Check compatibility: version mismatch
    curr_mismatch = [
        {"id": "axiom.turn", "version": "1.0.0"},
        {"id": "axiom.world", "version": "1.0.0"},
        {"id": "community.alchemy", "version": "0.3.0"},
    ]
    res_mismatch = check_save_modpack_compatibility(str(db_file), curr_mismatch)
    assert res_mismatch["compatible"] is False
    assert len(res_mismatch["version_mismatches"]) == 1
    assert res_mismatch["version_mismatches"][0]["id"] == "community.alchemy"


def test_pack_and_unpack_preserves_modpack_json(tmp_path: Path):
    myria_src = Path(__file__).resolve().parent.parent / "universes" / "Myria"
    uni_db = compile_universe(myria_src, tmp_path / "myria.db", force=True)

    save_info = create_save(uni_db, "Hero", "Normal")
    save_id = save_info["save_id"]
    save_db = save_info["db_path"]

    # Store custom modpack
    expected_mp = [{"id": "community.quest", "version": "1.5.0", "name": "Quest Mod"}]
    with sqlite3.connect(save_db) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO Save_Meta (key, value) VALUES ('active_modpack', ?);",
            (json.dumps(expected_mp),),
        )
        conn.commit()

    # Pack save
    archive = tmp_path / "save_export.axiomsave"
    pack_save(uni_db, save_id, archive)

    # Verify modpack.json inside zip
    with zipfile.ZipFile(str(archive), "r") as zf:
        assert "modpack.json" in zf.namelist()
        archived_mp = json.loads(zf.read("modpack.json").decode("utf-8"))
        assert archived_mp == expected_mp

    # Unpack into new universe
    uni_db2 = compile_universe(myria_src, tmp_path / "myria2.db", force=True)
    imported = unpack_save(archive, uni_db2, force=True)
    restored_mp = get_save_modpack(imported["db_path"])
    assert restored_mp == expected_mp


def test_hash_extra_mods_and_description(tmp_path: Path):
    """DOC §10.3: ids + versions + hash; warn on a missing, changed or ADDED mod."""
    from axiom.savestore import describe_modpack_differences, record_save_modpack

    save_db = tmp_path / "save.db"
    record_save_modpack(save_db, [
        {"id": "a.mod", "version": "1.0.0", "hash": "h1"},
        {"id": "b.mod", "version": "1.0.0", "hash": "h2"},
    ])
    same = [{"id": "a.mod", "version": "1.0.0", "hash": "h1"}, {"id": "b.mod", "version": "1.0.0", "hash": "h2"}]
    assert check_save_modpack_compatibility(save_db, same)["compatible"] is True

    changed = [{"id": "a.mod", "version": "1.0.0", "hash": "OTHER"}, {"id": "b.mod", "version": "1.0.0", "hash": "h2"},
               {"id": "c.mod", "version": "2.0.0", "hash": "h3"}]
    res = check_save_modpack_compatibility(save_db, changed)
    assert res["compatible"] is False
    assert res["changed_mods"] == ["a.mod"] and res["extra_mods"] == ["c.mod"]
    text = describe_modpack_differences(res)
    assert "a.mod: same version, modified content" in text and "added: c.mod" in text


def test_real_modpack_is_recorded_with_hashes_and_checked_by_session(tmp_path: Path):
    """create_save records the loaded modpack (with content hashes); a Session opened
    with another modpack exposes the warning the interfaces display."""
    from axiom.config import AppConfig
    from axiom.kernel.loader import bootstrap_all_mods, get_active_modpack, mod_content_hash
    from axiom.kernel.registry import KernelRegistry
    from axiom.savestore import record_save_modpack
    from axiom.session import Session

    reg = bootstrap_all_mods(KernelRegistry(), AppConfig())
    myria_src = Path(__file__).resolve().parent.parent / "universes" / "Myria"
    uni_db = compile_universe(myria_src, tmp_path / "myria.db", force=True)
    info = create_save(uni_db, "Hero", "Normal")

    recorded = get_save_modpack(info["db_path"])
    assert [m["id"] for m in recorded] == [m["id"] for m in get_active_modpack(reg)]
    turn = next(m for m in recorded if m["id"] == "axiom.turn")
    assert turn["hash"] == mod_content_hash(Path(__file__).resolve().parent.parent / "mods" / "axiom.turn")

    sess = Session(info["db_path"], info["save_id"], llm=object(), time_llm=object(), kernel_registry=reg)
    assert sess.modpack_compatibility["compatible"] is True and sess.modpack_warning == ""

    record_save_modpack(info["db_path"], recorded + [{"id": "community.gone", "version": "1.0.0", "hash": "x"}])
    sess2 = Session(info["db_path"], info["save_id"], llm=object(), time_llm=object(), kernel_registry=reg)
    assert "missing: community.gone" in sess2.modpack_warning
