"""tests/test_universe_as_code.py

Tests du Pilier 2 (Universe-as-Code) : compiler (`axiom.compile`), decompiler
(`axiom.decompile`) et leurs sous-commandes CLI.

Aucun LLM, aucun Qt : pur moteur. La garantie centrale est le **round-trip** —
arbo → .db → arbo → .db doit préserver tout le contenu de définition.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from axiom.compile import CompileError, compile_universe, hash_directory
from axiom.decompile import decompile_universe, read_definition
from axiom.schema import create_universe_db
from axiom.time_system import CalendarConfig


# ---------------------------------------------------------------------------
# Fixtures : une arborescence source riche
# ---------------------------------------------------------------------------

def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def source_tree(tmp_path: Path) -> Path:
    """Construit une arborescence source d'univers couvrant toutes les tables."""
    root = tmp_path / "drakthar_src"
    _write(root / "universe.toml", """
[meta]
name = "Drakthar"

[narrative]
system_prompt = "You are the narrator of Drakthar, a grim world."
global_lore_file = "lore/history.md"
first_message_file = "lore/intro.md"
world_tension_level = "0.4"

[calendar]
minutes_per_hour = 60
hours_per_day = 24
month_names = ["Forge", "Smelt", "Anvil", "Ember", "Cinder", "Ash", "Frost", "Bone", "Hollow", "Veil", "Dusk", "Pyre"]
days_per_month = [30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30]
start_day = 1
start_hour = 8
start_minute = 0

[companion]
enabled = true
hero_id = "player_hero"

[extra]
author = "Garen"
license = "CC-BY-SA-4.0"
""")
    _write(root / "lore" / "history.md", "# History\n\nLong ago, the forges burned bright.\n")
    _write(root / "lore" / "intro.md", "You wake in a cold smithy.")

    _write(root / "stats" / "definitions.toml", """
[[definitions]]
stat_id = "Health"
name = "Health"
description = "Hit points."
value_type = "numeric"
parameters = { min = 0, max = 100 }

[[definitions]]
stat_id = "Status"
name = "Status"
description = "Life state."
value_type = "categorical"
""")

    _write(root / "entities" / "player_hero.toml", """
entity_id = "player_hero"
entity_type = "player"
name = "The Hero"
description = "A nameless wanderer."

[stats]
Health = "100"
Status = "Alive"
""")
    _write(root / "entities" / "bob_blacksmith.toml", """
entity_id = "bob_blacksmith"
entity_type = "npc"
name = "Bob the Blacksmith"
description = "A gruff but kind smith."

[stats]
Health = "80"
Location = "drakthar_capital_smithy"
""")
    # _index.toml doit être ignoré.
    _write(root / "entities" / "_index.toml", 'note = "manifest, ignore me"')

    _write(root / "rules" / "death.toml", """
rule_id = "death_below_zero"
priority = 0
target_entity = "*"

[conditions]
operator = "AND"
[[conditions.clauses]]
stat = "Health"
comparator = "<="
value = 0

[[actions]]
type = "stat_set"
stat = "Status"
value = "Dead"
""")

    _write(root / "locations" / "map.toml", """
[[locations]]
location_id = "drakthar"
name = "Drakthar"
scale = "country"
description = "A grim kingdom."
x = 500
y = 500

[[locations]]
location_id = "drakthar_capital_smithy"
name = "The Iron Smithy"
parent_id = "drakthar"
scale = "building"
description = "Bob's workshop."

[[connections]]
source_id = "drakthar"
target_id = "drakthar_capital_smithy"
distance_km = 12
""")

    _write(root / "lore" / "magic.md", """+++
entry_id = "magic_system"
category = "Systems"
name = "The Weave"
keywords = "magic, mana"
+++

Magic is dangerous and costs blood.
""")

    _write(root / "events" / "festival.toml", """
event_id = "festival_of_lights"
trigger_minute = 1440
title = "Festival of Lights"
description = "Lanterns fill the sky."
""")

    _write(root / "setup" / "questions.toml", """
[[questions]]
setup_id = "origin"
question = "Where do you come from?"
type = "single_choice"
options = ["The mountains", "The sea"]
max_selections = 1
priority = 1
""")

    _write(root / "items" / "sword.toml", """
item_id = "sword_excalibur"
name = "Excalibur"
description = "A legendary blade."
category = "weapon"
weight = 3.5
rarity = "legendary"
""")

    return root


# ---------------------------------------------------------------------------
# Comparaison sémantique
# ---------------------------------------------------------------------------

def _norm_nl(obj):
    """Normalise récursivement les fins de ligne (LF) dans toute structure."""
    if isinstance(obj, str):
        return obj.replace("\r\n", "\n").replace("\r", "\n")
    if isinstance(obj, dict):
        return {k: _norm_nl(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_norm_nl(v) for v in obj]
    return obj


def _normalize_meta(meta: dict) -> dict:
    """Normalise calendar_config (JSON non canonique) + fins de ligne."""
    out = _norm_nl(dict(meta))
    if "calendar_config" in out:
        out["calendar_config"] = CalendarConfig.from_json(out["calendar_config"]).to_json()
    return out


def assert_definitions_equal(a: dict, b: dict) -> None:
    assert _normalize_meta(a["meta"]) == _normalize_meta(b["meta"])
    for key in ("entities", "rules", "stat_definitions", "locations",
                "connections", "lore", "events", "setup", "items"):
        assert _norm_nl(a[key]) == _norm_nl(b[key]), f"divergence sur {key}"


# ---------------------------------------------------------------------------
# Compilation
# ---------------------------------------------------------------------------

def test_compile_creates_cache_db(source_tree: Path):
    out = compile_universe(source_tree)
    assert out.exists()
    assert out.name == "universe.db"
    assert (source_tree / ".axiom-cache" / "cache_hash.txt").exists()


def test_compile_populates_all_tables(source_tree: Path):
    db = compile_universe(source_tree)
    data = read_definition(db)

    assert data["meta"]["universe_name"] == "Drakthar"
    assert data["meta"]["system_prompt"].startswith("You are the narrator")
    assert "forges burned bright" in data["meta"]["global_lore"]
    assert data["meta"]["first_message"] == "You wake in a cold smithy."
    assert data["meta"]["world_tension_level"] == "0.4"
    assert data["meta"]["companion_mode_enabled"] == "1"
    assert data["meta"]["companion_hero_id"] == "player_hero"
    assert data["meta"]["author"] == "Garen"  # passthrough [extra]

    cal = CalendarConfig.from_json(data["meta"]["calendar_config"])
    assert cal.month_names[0] == "Forge"
    assert cal.start_hour == 8

    ids = {e["entity_id"] for e in data["entities"]}
    assert ids == {"player_hero", "bob_blacksmith"}  # _index.toml ignoré
    hero = next(e for e in data["entities"] if e["entity_id"] == "player_hero")
    assert hero["entity_type"] == "player"
    assert hero["description"] == "A nameless wanderer."
    assert hero["stats"]["Health"] == "100"

    assert data["rules"][0]["rule_id"] == "death_below_zero"
    assert data["rules"][0]["conditions"]["operator"] == "AND"
    assert data["rules"][0]["actions"][0]["type"] == "stat_set"

    assert {s["stat_id"] for s in data["stat_definitions"]} == {"Health", "Status"}
    assert {l["location_id"] for l in data["locations"]} == {"drakthar", "drakthar_capital_smithy"}
    assert data["connections"][0]["distance_km"] == 12
    assert data["lore"][0]["entry_id"] == "magic_system"
    assert "blood" in data["lore"][0]["content"]
    assert data["events"][0]["event_id"] == "festival_of_lights"
    assert data["setup"][0]["options"] == ["The mountains", "The sea"]
    assert data["items"][0]["rarity"] == "legendary"


def test_compile_missing_universe_toml(tmp_path: Path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(CompileError):
        compile_universe(tmp_path / "empty")


def test_compile_invalid_toml(tmp_path: Path):
    root = tmp_path / "bad"
    _write(root / "universe.toml", "this is = = not valid")
    with pytest.raises(CompileError):
        compile_universe(root)


def test_compile_missing_required_field(tmp_path: Path):
    root = tmp_path / "norule"
    _write(root / "universe.toml", '[meta]\nname = "X"\n')
    _write(root / "rules" / "broken.toml", 'priority = 1\n')  # pas de rule_id
    with pytest.raises(CompileError):
        compile_universe(root)


# ---------------------------------------------------------------------------
# Cache (hash)
# ---------------------------------------------------------------------------

def test_compile_skips_when_unchanged(source_tree: Path):
    db = compile_universe(source_tree)
    # Marqueur dans le cache : il doit survivre à une 2e compilation sans force.
    with sqlite3.connect(str(db)) as conn:
        conn.execute("INSERT INTO Universe_Meta (key, value) VALUES ('_marker', 'kept');")
        conn.commit()

    compile_universe(source_tree)  # hash inchangé → skip
    data = read_definition(db)
    assert data["meta"].get("_marker") == "kept"


def test_compile_force_rebuilds(source_tree: Path):
    db = compile_universe(source_tree)
    # closing() : sous Windows la connexion ouverte verrouille le .db et le
    # recompile (replace atomique) échouerait (WinError 32).
    with closing(sqlite3.connect(str(db))) as conn:
        conn.execute("INSERT INTO Universe_Meta (key, value) VALUES ('_marker', 'kept');")
        conn.commit()

    compile_universe(source_tree, force=True)
    data = read_definition(db)
    assert "_marker" not in data["meta"]


def test_compile_rebuilds_on_source_change(source_tree: Path):
    db = compile_universe(source_tree)
    with closing(sqlite3.connect(str(db))) as conn:
        conn.execute("INSERT INTO Universe_Meta (key, value) VALUES ('_marker', 'kept');")
        conn.commit()

    _write(source_tree / "entities" / "newbie.toml",
           'entity_id = "newbie"\nentity_type = "npc"\nname = "Newbie"\n')
    compile_universe(source_tree)  # hash changé → recompile
    data = read_definition(db)
    assert "_marker" not in data["meta"]
    assert any(e["entity_id"] == "newbie" for e in data["entities"])


def test_hash_directory_ignores_cache(source_tree: Path):
    h1 = hash_directory(source_tree)
    (source_tree / ".axiom-cache").mkdir(exist_ok=True)
    (source_tree / ".axiom-cache" / "junk.txt").write_text("noise")
    assert hash_directory(source_tree) == h1


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------

def test_roundtrip_source_to_source(source_tree: Path, tmp_path: Path):
    """arbo → .db → arbo → .db : le contenu de définition est préservé."""
    db1 = compile_universe(source_tree, tmp_path / "db1.db")
    out_dir = tmp_path / "regen"
    decompile_universe(db1, out_dir)
    db2 = compile_universe(out_dir, tmp_path / "db2.db")
    assert_definitions_equal(read_definition(db1), read_definition(db2))


def test_roundtrip_real_db(tmp_path: Path):
    """.db construit à la main → decompile → compile : ids/calendrier préservés."""
    db = tmp_path / "manual.db"
    create_universe_db(str(db))
    with sqlite3.connect(str(db)) as conn:
        conn.executemany(
            "INSERT INTO Universe_Meta (key, value) VALUES (?, ?);",
            [
                ("universe_name", "Handmade"),
                ("system_prompt", "Be terse."),
                ("calendar_config", CalendarConfig(start_hour=6).to_json()),
                ("companion_mode_enabled", "0"),
                ("custom_flag", "xyz"),
            ],
        )
        conn.execute(
            "INSERT INTO Entities (entity_id, entity_type, name, description, is_active) "
            "VALUES ('npc_1', 'npc', 'Guard', 'Stands watch.', 1);"
        )
        conn.execute(
            "INSERT INTO Entity_Stats (entity_id, stat_key, stat_value) "
            "VALUES ('npc_1', 'Health', '50');"
        )
        conn.execute(
            "INSERT INTO Lore_Book (entry_id, category, name, keywords, content) "
            "VALUES ('e1', 'Geo', 'The Wastes', 'cold,north', 'Frozen and empty.');"
        )
        conn.commit()

    out_dir = tmp_path / "decompiled"
    decompile_universe(db, out_dir)
    db2 = compile_universe(out_dir, tmp_path / "recompiled.db")
    assert_definitions_equal(read_definition(db), read_definition(db2))


def test_decompile_writes_gitignore(source_tree: Path, tmp_path: Path):
    db = compile_universe(source_tree, tmp_path / "x.db")
    out = decompile_universe(db, tmp_path / "regen")
    assert (out / ".gitignore").read_text().strip() == ".axiom-cache/"


def test_decompile_missing_db(tmp_path: Path):
    from axiom.decompile import DecompileError
    with pytest.raises(DecompileError):
        decompile_universe(tmp_path / "nope.db", tmp_path / "out")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def test_cli_compile_and_decompile(source_tree: Path, tmp_path: Path):
    from axiom.cli.main import build_parser

    parser = build_parser()

    db_out = tmp_path / "cli.db"
    args = parser.parse_args(["compile", str(source_tree), "-o", str(db_out)])
    assert args.func(args) == 0
    assert db_out.exists()

    out_dir = tmp_path / "cli_src"
    args = parser.parse_args(["decompile", str(db_out), str(out_dir)])
    assert args.func(args) == 0
    assert (out_dir / "universe.toml").exists()


def test_cli_compile_bad_source(tmp_path: Path):
    from axiom.cli.main import build_parser

    parser = build_parser()
    args = parser.parse_args(["compile", str(tmp_path / "missing")])
    assert args.func(args) == 1


# ---------------------------------------------------------------------------
# Packaging .axiom v2 + compat v1
# ---------------------------------------------------------------------------

def test_pack_unpack_v2_roundtrip(source_tree: Path, tmp_path: Path):
    from axiom.package import pack_universe, unpack_universe

    archive = pack_universe(source_tree, tmp_path / "drakthar.axiom")
    assert archive.exists()

    dest = unpack_universe(archive, tmp_path / "imported")
    assert (dest / "universe.toml").exists()
    db = dest / ".axiom-cache" / "universe.db"
    assert db.exists()

    src_db = compile_universe(source_tree, tmp_path / "src.db")
    assert_definitions_equal(read_definition(src_db), read_definition(db))


def test_pack_definition_seule(source_tree: Path, tmp_path: Path):
    """TICKET-039 : l'archive .axiom ne publie que la définition — pas les
    saves embarquées du cache (vie privée), pas `.git/`, pas les sidecars WAL."""
    import zipfile

    from axiom.db_helpers import create_new_save
    from axiom.package import pack_universe

    cache = compile_universe(source_tree)
    sid = create_new_save(str(cache), "Privé", "Normal")
    (source_tree / ".git").mkdir()
    (source_tree / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")

    archive = pack_universe(source_tree, tmp_path / "u.axiom")

    with zipfile.ZipFile(str(archive)) as zf:
        names = zf.namelist()
        assert not any(n.startswith(".git/") for n in names)
        assert not any(n.endswith(("-wal", "-shm")) for n in names)
        extracted = tmp_path / "x"
        zf.extractall(extracted)
    with sqlite3.connect(str(extracted / ".axiom-cache" / "universe.db")) as conn:
        assert conn.execute("SELECT COUNT(*) FROM Saves;").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM Event_Log;").fetchone()[0] == 0
        # La définition, elle, voyage bien.
        assert conn.execute("SELECT COUNT(*) FROM Entities;").fetchone()[0] > 0

    # L'original n'a pas été touché : la save embarquée est toujours là.
    with sqlite3.connect(str(cache)) as conn:
        saves = [r[0] for r in conn.execute("SELECT save_id FROM Saves;")]
    assert saves == [sid]


def test_pack_embeds_valid_cache(source_tree: Path, tmp_path: Path):
    """L'archive embarque un cache dont le hash correspond à la source (réutilisable tel quel)."""
    from axiom.package import pack_universe, unpack_universe

    archive = pack_universe(source_tree, tmp_path / "u.axiom")
    dest = unpack_universe(archive, tmp_path / "imp")

    cache_hash = (dest / ".axiom-cache" / "cache_hash.txt").read_text(encoding="utf-8").strip()
    assert cache_hash == hash_directory(dest)  # cache embarqué considéré valide


def test_unpack_v2_recompiles_on_stale_cache(source_tree: Path, tmp_path: Path):
    """Un cache embarqué périmé (hash invalide) est recompilé à l'import."""
    from axiom.package import pack_universe, unpack_universe
    import zipfile

    archive = pack_universe(source_tree, tmp_path / "u.axiom")

    # Réécrit l'archive avec un cache_hash périmé et un marqueur dans le .db embarqué.
    extract = tmp_path / "edit"
    with zipfile.ZipFile(str(archive)) as zf:
        zf.extractall(extract)
    (extract / ".axiom-cache" / "cache_hash.txt").write_text("stale", encoding="utf-8")
    with sqlite3.connect(str(extract / ".axiom-cache" / "universe.db")) as conn:
        conn.execute("INSERT INTO Universe_Meta (key, value) VALUES ('_marker', 'x');")
        conn.commit()
    stale_archive = tmp_path / "stale.axiom"
    with zipfile.ZipFile(str(stale_archive), "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(extract.rglob("*")):
            if p.is_file():
                zf.write(p, p.relative_to(extract).as_posix())

    dest = unpack_universe(stale_archive, tmp_path / "imp")
    data = read_definition(dest / ".axiom-cache" / "universe.db")
    assert "_marker" not in data["meta"]  # recompilé → marqueur perdu
    assert data["meta"]["universe_name"] == "Drakthar"


def _make_v1_axiom(path: Path) -> None:
    """Crée un `.axiom` v1 (zip de JSON) minimal."""
    import zipfile
    meta = {
        "universe_name": "Legacy World",
        "system_prompt": "Old narrator.",
        "global_lore": "Ancient times.",
        "first_message": "Welcome back.",
    }
    entities = [{
        "entity_id": "old_npc",
        "entity_type": "npc",
        "name": "Old NPC",
        "stats": {"Health": "42"},
    }]
    rules = [{
        "rule_id": "old_rule",
        "priority": 1,
        "conditions": {"operator": "AND", "clauses": []},
        "actions": [{"type": "stat_set", "stat": "Status", "value": "Done"}],
        "target_entity": "*",
    }]
    lore = [{
        "entry_id": "l1", "category": "Hist", "name": "Old Lore",
        "keywords": "old", "content": "Long ago.",
    }]
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(str(path), "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("universe_meta.json", json.dumps(meta))
        zf.writestr("entities.json", json.dumps(entities))
        zf.writestr("rules.json", json.dumps(rules))
        zf.writestr("lore_book.json", json.dumps(lore))
        zf.writestr("format_version.json", json.dumps({"version": "1.0"}))


def test_detect_format(source_tree: Path, tmp_path: Path):
    from axiom.package import detect_format, pack_universe, PackageError

    v2 = pack_universe(source_tree, tmp_path / "v2.axiom")
    assert detect_format(v2) == "v2"

    v1 = tmp_path / "v1.axiom"
    _make_v1_axiom(v1)
    assert detect_format(v1) == "v1"

    bad = tmp_path / "bad.axiom"
    import zipfile
    with zipfile.ZipFile(str(bad), "w") as zf:
        zf.writestr("random.txt", "nope")
    with pytest.raises(PackageError):
        detect_format(bad)


def test_import_v1_converts_to_v2(tmp_path: Path):
    from axiom.package import unpack_universe

    v1 = tmp_path / "legacy.axiom"
    _make_v1_axiom(v1)

    dest = unpack_universe(v1, tmp_path / "out")
    assert dest.name == "Legacy_World"  # nom de l'univers, pas « legacy.axiom »
    assert (dest / "universe.toml").exists()
    db = dest / ".axiom-cache" / "universe.db"
    data = read_definition(db)
    assert data["meta"]["universe_name"] == "Legacy World"
    assert data["meta"]["global_lore"] == "Ancient times."
    assert data["entities"][0]["entity_id"] == "old_npc"
    assert data["entities"][0]["stats"]["Health"] == "42"
    assert data["rules"][0]["rule_id"] == "old_rule"
    assert data["lore"][0]["content"] == "Long ago."


def test_cli_pack_and_import(source_tree: Path, tmp_path: Path):
    from axiom.cli.main import build_parser

    parser = build_parser()
    archive = tmp_path / "cli.axiom"
    args = parser.parse_args(["pack", str(source_tree), str(archive)])
    assert args.func(args) == 0
    assert archive.exists()

    args = parser.parse_args(["import", str(archive), str(tmp_path / "cli_imp")])
    assert args.func(args) == 0
    # Le dossier d'import porte le NOM de l'univers (pas le nom du fichier .axiom).
    assert (tmp_path / "cli_imp" / "Drakthar" / "universe.toml").exists()


# ---------------------------------------------------------------------------
# `axiom play` sur un univers compilé / source / .axiom
# ---------------------------------------------------------------------------

def test_play_resolves_db(source_tree: Path, tmp_path: Path):
    from axiom.cli.play import _resolve_playable_db

    db = compile_universe(source_tree, tmp_path / "x.db")
    assert _resolve_playable_db(str(db)) == str(db)


def test_play_resolves_source_dir(source_tree: Path):
    """Un dossier source est compilé à la volée et devient jouable."""
    from axiom.cli.play import _resolve_playable_db
    from axiom.universe import Universe

    db = _resolve_playable_db(str(source_tree))
    assert db is not None and Path(db).exists()
    Universe.load(db)  # chargeable sans erreur


def test_play_resolves_axiom_v2(source_tree: Path, tmp_path: Path, monkeypatch):
    from axiom import paths
    from axiom.package import pack_universe
    from axiom.cli.play import _resolve_playable_db

    monkeypatch.setattr(paths, "UNIVERSES_DIR", tmp_path / "universes")
    (tmp_path / "universes").mkdir()
    archive = pack_universe(source_tree, tmp_path / "w.axiom")

    db = _resolve_playable_db(str(archive))
    assert db is not None and Path(db).exists()
    assert read_definition(db)["meta"]["universe_name"] == "Drakthar"


def test_play_resolve_missing(tmp_path: Path):
    from axiom.cli.play import _resolve_playable_db

    assert _resolve_playable_db(str(tmp_path / "nope.db")) is None


def test_play_loop_on_compiled_universe(source_tree: Path):
    """Bout-en-bout : `Session` réelle sur un .db compilé, commandes /stats puis /quit."""
    import io
    from axiom.cli.play import play_loop, _read_first_message, _resolve_player_id
    from axiom.db_helpers import create_new_save
    from axiom.session import Session

    db = str(compile_universe(source_tree))
    save_id = create_new_save(db, "Hero", "Normal")

    class FakeLLM:
        def is_available(self):
            return True

    session = Session(db, save_id, llm=FakeLLM(), mode="Normal")
    out, err = io.StringIO(), io.StringIO()
    lines = iter(["/stats", "/quit"])
    play_loop(
        session,
        player_id=_resolve_player_id(db),
        first_message=_read_first_message(db),
        read=lambda _prompt: next(lines),
        out=out, err=err,
    )
    assert "You wake in a cold smithy." in out.getvalue()  # first_message affiché
    assert _resolve_player_id(db) == "player_hero"
