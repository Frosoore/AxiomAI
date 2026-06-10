"""tests/test_source_preview.py

TICKET-030 — Populate × Universe-as-Code, hors LLM :
- `axiom.library.diff_source_trees` / `apply_staged_source` (moteur) ;
- sandbox `_stage_source_change` + `ApplyStagedSourceTask` (workers) ;
- insertion canon idempotente + résolution de l'univers depuis une save.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from axiom import paths
from axiom.compile import compile_universe
from axiom.library import apply_staged_source, diff_source_trees


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path: Path):
    paths.configure(data_dir=tmp_path / "data")
    yield
    paths.reset()


@pytest.fixture
def source_tree(tmp_path: Path) -> Path:
    root = tmp_path / "demo_src"
    _write(root / "universe.toml", '[meta]\nname = "Demo"\n\n[narrative]\nsystem_prompt = "GM."\n')
    _write(root / "entities" / "alice.toml",
           'entity_id = "alice"\nname = "Alice"\n\n[stats]\nHealth = "80"\n')
    return root


# ---------------------------------------------------------------------------
# diff_source_trees
# ---------------------------------------------------------------------------

def test_diff_trees_added_modified_removed(tmp_path: Path, source_tree: Path):
    import shutil

    after = tmp_path / "after"
    shutil.copytree(source_tree, after)
    (after / "entities" / "bob.toml").write_text('entity_id = "bob"\n', encoding="utf-8")
    (after / "entities" / "alice.toml").write_text('entity_id = "alice"\nname = "Alicia"\n',
                                                   encoding="utf-8")
    (after / "universe.toml").unlink()

    diffs = {d["path"]: d for d in diff_source_trees(source_tree, after)}
    assert diffs["entities/bob.toml"]["status"] == "added"
    assert diffs["entities/alice.toml"]["status"] == "modified"
    assert diffs["universe.toml"]["status"] == "removed"
    assert "+name = \"Alicia\"" in diffs["entities/alice.toml"]["diff"]


def test_diff_trees_ignore_zones_protegees(tmp_path: Path, source_tree: Path):
    import shutil

    after = tmp_path / "after"
    shutil.copytree(source_tree, after)
    _write(after / ".axiom-cache" / "source.hash", "xxx")
    _write(after / ".git" / "config", "yyy")
    assert diff_source_trees(source_tree, after) == []


# ---------------------------------------------------------------------------
# apply_staged_source
# ---------------------------------------------------------------------------

def test_apply_staged_source(tmp_path: Path, source_tree: Path):
    import shutil

    db = compile_universe(source_tree)
    staged = tmp_path / "staged"
    shutil.copytree(source_tree, staged, ignore=shutil.ignore_patterns(".axiom-cache"))
    (staged / "entities" / "bob.toml").write_text(
        'entity_id = "bob"\nname = "Bob"\n', encoding="utf-8")

    apply_staged_source(staged, source_tree, db)

    assert (source_tree / "entities" / "bob.toml").exists()
    with sqlite3.connect(str(db)) as conn:
        ids = {r[0] for r in conn.execute("SELECT entity_id FROM Entities;")}
    assert {"alice", "bob"} <= ids


# ---------------------------------------------------------------------------
# Sandbox workers (_stage_source_change / ApplyStagedSourceTask)
# ---------------------------------------------------------------------------

def test_stage_source_change_ne_touche_pas_le_reel(source_tree: Path):
    from workers.db_tasks import _stage_source_change, discard_staged_source

    db = compile_universe(source_tree)
    before = (source_tree / "entities" / "alice.toml").read_text(encoding="utf-8")

    def mutate(tmp_db: str) -> int:
        with sqlite3.connect(tmp_db) as conn:
            conn.execute(
                "INSERT INTO Entities (entity_id, name, entity_type, is_active) "
                "VALUES ('bob', 'Bob', 'npc', 1);")
            conn.commit()
        return 1

    info = _stage_source_change(str(db), mutate)
    assert info["result"] == 1
    assert [d["path"] for d in info["diffs"]] == ["entities/bob.toml"]
    assert info["diffs"][0]["status"] == "added"
    # Le réel est intact tant qu'on n'applique pas.
    assert (source_tree / "entities" / "alice.toml").read_text(encoding="utf-8") == before
    assert not (source_tree / "entities" / "bob.toml").exists()
    with sqlite3.connect(str(db)) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM Entities WHERE entity_id='bob';").fetchone()[0] == 0

    discard_staged_source(info["staged_dir"])
    assert not Path(info["staged_dir"]).exists()


def test_stage_puis_apply(source_tree: Path):
    from workers.db_tasks import ApplyStagedSourceTask, _stage_source_change

    db = compile_universe(source_tree)

    def mutate(tmp_db: str) -> None:
        with sqlite3.connect(tmp_db) as conn:
            conn.execute(
                "INSERT INTO Lore_Book (entry_id, category, name, keywords, content) "
                "VALUES ('l1', 'Faction', 'La Guilde', '', 'Une guilde secrète.');")
            conn.commit()

    info = _stage_source_change(str(db), mutate)
    assert info["diffs"]

    ApplyStagedSourceTask(str(db), info["staged_dir"], info["src_dir"]).execute()
    assert not Path(info["staged_dir"]).exists()  # sandbox nettoyée
    with sqlite3.connect(str(db)) as conn:
        names = {r[0] for r in conn.execute("SELECT name FROM Lore_Book;")}
    assert "La Guilde" in names
    # La source texte porte aussi le nouveau lore.
    lore_files = list((source_tree / "lore").rglob("*.md")) if (source_tree / "lore").is_dir() else []
    assert any("guilde" in f.read_text(encoding="utf-8").lower() for f in lore_files)


def test_stage_refuse_db_plat(tmp_path: Path, source_tree: Path):
    from workers.db_tasks import _stage_source_change

    flat = compile_universe(source_tree, tmp_path / "flat.db")
    with pytest.raises(ValueError):
        _stage_source_change(str(flat), lambda _db: None)


def test_stage_sans_changement(source_tree: Path):
    from workers.db_tasks import _stage_source_change

    db = compile_universe(source_tree)
    info = _stage_source_change(str(db), lambda _db: "noop")
    assert info["diffs"] == [] and info["staged_dir"] == ""


# ---------------------------------------------------------------------------
# Canonisation (hors LLM)
# ---------------------------------------------------------------------------

def test_insert_canon_idempotent(source_tree: Path):
    from workers.db_tasks import _insert_canon

    db = str(compile_universe(source_tree))
    entities = [
        {"name": "Alice", "entity_type": "npc", "description": "déjà connue"},
        {"name": "Le Forgeron", "entity_type": "npc", "description": "rencontré au chapitre 2"},
        {"name": "", "entity_type": "npc"},  # ignorée
    ]
    lore = [{"category": "Location", "name": "La Taverne", "content": "Établie en jeu."}]

    counts = _insert_canon(db, entities, lore)
    assert counts == {"entities": 1, "lore": 1}
    # Rejouer la même extraction n'ajoute rien.
    assert _insert_canon(db, entities, lore) == {"entities": 0, "lore": 0}


def test_canonize_resout_l_univers_depuis_la_save(source_tree: Path):
    from axiom.savestore import create_save
    from workers.db_tasks import CanonizeStoryTask

    db = compile_universe(source_tree)
    info = create_save(db, "Hero", "Normal")

    task = CanonizeStoryTask(info["db_path"], "transcript")
    assert task._resolve_universe_db() == str(db)


def test_canonize_refuse_sans_univers_dossier(tmp_path: Path, source_tree: Path):
    from axiom.db_helpers import create_new_save
    from workers.db_tasks import CanonizeStoryTask

    flat = compile_universe(source_tree, tmp_path / "flat.db")
    create_new_save(str(flat), "Hero", "Normal")
    task = CanonizeStoryTask(str(flat), "transcript")
    with pytest.raises(ValueError):
        task._resolve_universe_db()
