"""tests/test_dev_hotreload.py

Tests de la finition du Pilier 2 (Phase 7) :
- hot reload `axiom dev` (`axiom.dev`) — refresh **in-place** de la définition
  qui préserve les tables runtime (saves, journal, inventaire, modifiers) ;
- export `.db` → `.axiom` v2 (`axiom.package.export_db_to_axiom`) ;
- découverte de bibliothèque (`axiom.library.discover_universes`).

Aucun LLM, aucun Qt : pur moteur.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from axiom.compile import CACHE_DB_NAME, CACHE_DIRNAME, CompileError, compile_universe
from axiom.db_helpers import create_new_save
from axiom.decompile import read_definition
from axiom.dev import ensure_compiled, poll_once, refresh_definition, watch_universe
from axiom.library import discover_universes, universe_root_for
from axiom.package import export_db_to_axiom, unpack_universe


# ---------------------------------------------------------------------------
# Fixture : petite arborescence source + une partie en cours dans le cache
# ---------------------------------------------------------------------------

def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def source_tree(tmp_path: Path) -> Path:
    """Arborescence source minimale : 2 entités, 2 items, 1 event programmé."""
    root = tmp_path / "hotreload_src"
    _write(root / "universe.toml", """
[meta]
name = "Hotreload"

[narrative]
system_prompt = "You are the narrator."
""")
    _write(root / "entities" / "alice.toml", """
entity_id = "alice"
entity_type = "npc"
name = "Alice"

[stats]
Health = "80"
""")
    _write(root / "entities" / "bob.toml", """
entity_id = "bob"
entity_type = "npc"
name = "Bob"
""")
    _write(root / "items" / "sword.toml", """
item_id = "sword"
name = "Sword"
""")
    _write(root / "items" / "shield.toml", """
item_id = "shield"
name = "Shield"
""")
    _write(root / "events" / "festival.toml", """
event_id = "festival"
trigger_minute = 600
title = "Festival"
""")
    return root


@pytest.fixture
def db_with_save(source_tree: Path) -> tuple[Path, str]:
    """Compile l'univers puis y joue : une save, des events, inventaire, modifier."""
    db = compile_universe(source_tree)
    save_id = create_new_save(str(db), "Player", "Normal")
    with sqlite3.connect(str(db)) as conn:
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute(
            "INSERT INTO Event_Log (save_id, turn_id, event_type, target_entity, payload) "
            "VALUES (?, 1, 'stat_change', 'alice', '{\"stat_key\": \"Health\", \"delta\": -10}');",
            (save_id,),
        )
        conn.execute(
            "INSERT INTO Items_Inventory (save_id, entity_id, item_id, quantity) "
            "VALUES (?, 'alice', 'sword', 1);",
            (save_id,),
        )
        conn.execute(
            "INSERT INTO Active_Modifiers (modifier_id, save_id, entity_id, stat_key, delta, minutes_remaining) "
            "VALUES ('mod1', ?, 'alice', 'Health', -5.0, 30);",
            (save_id,),
        )
        conn.execute(
            "INSERT INTO Fired_Scheduled_Events (save_id, event_id) VALUES (?, 'festival');",
            (save_id,),
        )
        conn.commit()
    return db, save_id


def _rows(db: Path, query: str) -> list:
    with sqlite3.connect(str(db)) as conn:
        return conn.execute(query).fetchall()


# ---------------------------------------------------------------------------
# refresh_definition
# ---------------------------------------------------------------------------

class TestRefreshDefinition:
    def test_premier_appel_sans_db_compile_a_neuf(self, source_tree: Path):
        db = refresh_definition(source_tree)
        assert db.exists()
        names = {r[0] for r in _rows(db, "SELECT entity_id FROM Entities;")}
        assert names == {"alice", "bob"}

    def test_refresh_met_a_jour_la_definition(self, db_with_save):
        db, _ = db_with_save
        alice = db.parent.parent / "entities" / "alice.toml"
        alice.write_text(alice.read_text().replace('name = "Alice"', 'name = "Alicia"'),
                         encoding="utf-8")
        refresh_definition(db.parent.parent, db)
        assert _rows(db, "SELECT name FROM Entities WHERE entity_id='alice';")[0][0] == "Alicia"

    def test_refresh_preserve_les_tables_runtime(self, db_with_save):
        db, save_id = db_with_save
        src = db.parent.parent
        # Modifs source : Alice renommée, Bob supprimé, Carol ajoutée, shield supprimé.
        (src / "entities" / "bob.toml").unlink()
        (src / "items" / "shield.toml").unlink()
        _write(src / "entities" / "carol.toml", 'entity_id = "carol"\nname = "Carol"\n')

        refresh_definition(src, db)

        # Définition à jour.
        names = {r[0] for r in _rows(db, "SELECT entity_id FROM Entities;")}
        assert names == {"alice", "carol"}
        items = {r[0] for r in _rows(db, "SELECT item_id FROM Item_Definitions;")}
        assert items == {"sword"}

        # Runtime intact : save, journal, inventaire/modifier d'Alice, event tiré.
        assert _rows(db, f"SELECT save_id FROM Saves WHERE save_id='{save_id}';")
        assert len(_rows(db, "SELECT * FROM Event_Log;")) >= 1
        assert _rows(db, "SELECT quantity FROM Items_Inventory WHERE entity_id='alice';") == [(1,)]
        assert _rows(db, "SELECT modifier_id FROM Active_Modifiers;") == [("mod1",)]
        assert _rows(db, "SELECT event_id FROM Fired_Scheduled_Events;") == [("festival",)]

    def test_entite_retiree_emporte_ses_enfants_runtime(self, db_with_save):
        db, save_id = db_with_save
        src = db.parent.parent
        with sqlite3.connect(str(db)) as conn:
            conn.execute("PRAGMA foreign_keys=ON;")
            conn.execute(
                "INSERT INTO Items_Inventory (save_id, entity_id, item_id, quantity) "
                "VALUES (?, 'bob', 'sword', 2);",
                (save_id,),
            )
            conn.commit()
        (src / "entities" / "bob.toml").unlink()

        refresh_definition(src, db)

        # L'inventaire de Bob disparaît (cascade voulue), celui d'Alice survit.
        owners = {r[0] for r in _rows(db, "SELECT entity_id FROM Items_Inventory;")}
        assert owners == {"alice"}

    def test_entite_runtime_survit_au_refresh(self, db_with_save):
        """Le joueur (et tout PNJ découvert en jeu) ne vient pas de la source :
        le hot reload ne doit jamais le supprimer ni toucher ses stats."""
        db, _ = db_with_save
        src = db.parent.parent
        with sqlite3.connect(str(db)) as conn:
            conn.execute(
                "INSERT INTO Entities (entity_id, entity_type, name, origin) "
                "VALUES ('garen', 'player', 'Garen', 'runtime');"
            )
            conn.execute(
                "INSERT INTO Entity_Stats (entity_id, stat_key, stat_value) "
                "VALUES ('garen', 'Health', '42');"
            )
            conn.commit()
        # Une modif source quelconque déclenche un vrai resync.
        _write(src / "entities" / "carol.toml", 'entity_id = "carol"\nname = "Carol"\n')

        refresh_definition(src, db)

        names = {r[0] for r in _rows(db, "SELECT entity_id FROM Entities;")}
        assert {"garen", "carol"} <= names
        assert _rows(db, "SELECT stat_value FROM Entity_Stats WHERE entity_id='garen';") == [("42",)]

    def test_amnistie_db_d_avant_la_colonne_origin(self, db_with_save):
        """DB legacy (sans colonne origin) : les entités hors-source sont
        requalifiées runtime au premier refresh, pas supprimées."""
        db, _ = db_with_save
        src = db.parent.parent
        with sqlite3.connect(str(db)) as conn:
            conn.execute("ALTER TABLE Entities DROP COLUMN origin;")  # simule l'ancien schéma
            conn.execute(
                "INSERT INTO Entities (entity_id, entity_type, name) "
                "VALUES ('old_player', 'player', 'Old Player');"
            )
            conn.commit()
        _write(src / "entities" / "carol.toml", 'entity_id = "carol"\nname = "Carol"\n')

        refresh_definition(src, db)

        rows = dict(_rows(db, "SELECT entity_id, origin FROM Entities;"))
        assert rows["old_player"] == "runtime"   # amnistié, pas supprimé
        assert rows["alice"] == "definition"     # toujours gérée par la source

    def test_source_malformee_ne_touche_pas_la_db(self, db_with_save):
        db, _ = db_with_save
        src = db.parent.parent
        _write(src / "entities" / "broken.toml", "ceci n'est pas = = du toml [[[")
        with pytest.raises(CompileError):
            refresh_definition(src, db)
        # Définition d'origine intacte.
        names = {r[0] for r in _rows(db, "SELECT entity_id FROM Entities;")}
        assert names == {"alice", "bob"}


# ---------------------------------------------------------------------------
# ensure_compiled — le chemin « rendre jouable » (Hub, axiom play) ne doit
# jamais détruire les saves embarquées dans le cache
# ---------------------------------------------------------------------------

class TestEnsureCompiled:
    def test_cache_a_jour_no_op(self, source_tree: Path):
        db = compile_universe(source_tree)
        mtime = db.stat().st_mtime_ns
        assert ensure_compiled(source_tree) == db
        assert db.stat().st_mtime_ns == mtime  # pas réécrit

    def test_source_modifiee_preserve_les_saves(self, db_with_save):
        db, save_id = db_with_save
        src = db.parent.parent
        _write(src / "entities" / "carol.toml", 'entity_id = "carol"\nname = "Carol"\n')

        out = ensure_compiled(src)

        assert out == db
        names = {r[0] for r in _rows(db, "SELECT entity_id FROM Entities;")}
        assert "carol" in names  # définition rechargée…
        assert _rows(db, f"SELECT save_id FROM Saves WHERE save_id='{save_id}';")  # …saves intactes

    def test_play_sur_dossier_modifie_preserve_les_saves(self, db_with_save):
        from axiom.cli.play import _resolve_playable_db

        db, save_id = db_with_save
        src = db.parent.parent
        _write(src / "entities" / "carol.toml", 'entity_id = "carol"\nname = "Carol"\n')

        resolved = _resolve_playable_db(str(src))

        assert resolved == str(db)
        assert _rows(db, f"SELECT save_id FROM Saves WHERE save_id='{save_id}';")

    def test_discovery_sur_source_modifiee_preserve_les_saves(self, db_with_save, tmp_path):
        db, save_id = db_with_save
        src = db.parent.parent
        _write(src / "entities" / "carol.toml", 'entity_id = "carol"\nname = "Carol"\n')

        entries = discover_universes(src.parent)

        assert [e["name"] for e in entries] == ["Hotreload"]
        assert _rows(db, f"SELECT save_id FROM Saves WHERE save_id='{save_id}';")


# ---------------------------------------------------------------------------
# Ré-import : jamais d'écrasement d'un univers installé
# ---------------------------------------------------------------------------

class TestReimportSansEcrasement:
    def test_unpack_uniquifie_la_destination(self, source_tree: Path, tmp_path: Path):
        from axiom.package import pack_universe

        archive = tmp_path / "demo.axiom"
        pack_universe(source_tree, archive)
        lib = tmp_path / "lib"

        first = unpack_universe(archive, lib)
        second = unpack_universe(archive, lib)

        # Dossier = nom de l'univers ([meta].name = "Hotreload"), pas "demo.axiom".
        assert first == lib / "Hotreload"
        assert second == lib / "Hotreload_1"
        assert (first / "universe.toml").exists()
        assert (second / "universe.toml").exists()


# ---------------------------------------------------------------------------
# poll_once / watch_universe
# ---------------------------------------------------------------------------

class TestWatch:
    def test_poll_once_sans_changement_ne_recompile_pas(self, source_tree: Path):
        h1, refreshed = poll_once(source_tree, None, None)
        assert refreshed
        h2, refreshed = poll_once(source_tree, None, h1)
        assert h2 == h1 and not refreshed

    def test_poll_once_detecte_un_changement(self, source_tree: Path):
        h1, _ = poll_once(source_tree, None, None)
        _write(source_tree / "entities" / "carol.toml", 'entity_id = "carol"\nname = "Carol"\n')
        h2, refreshed = poll_once(source_tree, None, h1)
        assert h2 != h1 and refreshed
        db = source_tree / CACHE_DIRNAME / CACHE_DB_NAME
        names = {r[0] for r in _rows(db, "SELECT entity_id FROM Entities;")}
        assert "carol" in names

    def test_poll_once_erreur_porte_le_hash(self, source_tree: Path):
        _write(source_tree / "entities" / "broken.toml", "pas du toml [[[")
        with pytest.raises(CompileError) as excinfo:
            poll_once(source_tree, None, None)
        assert isinstance(getattr(excinfo.value, "src_hash", None), str)

    def test_watch_universe_s_arrete_et_compile(self, source_tree: Path):
        polls = {"n": 0}

        def should_stop() -> bool:
            polls["n"] += 1
            return polls["n"] > 2

        events: list[str] = []
        watch_universe(source_tree, interval=0.01, on_event=events.append,
                       should_stop=should_stop)
        assert (source_tree / CACHE_DIRNAME / CACHE_DB_NAME).exists()
        assert any("compiled" in e or "reloaded" in e for e in events)

    def test_cli_dev_refuse_un_dossier_sans_universe_toml(self, tmp_path: Path, capsys):
        from axiom.cli.main import main
        assert main(["dev", str(tmp_path)]) == 1
        assert "universe.toml" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# export .db → .axiom v2
# ---------------------------------------------------------------------------

class TestExportDbToAxiom:
    def test_round_trip_definition(self, db_with_save, tmp_path: Path):
        db, _ = db_with_save
        archive = tmp_path / "out" / "hotreload.axiom"
        out = export_db_to_axiom(db, archive)
        assert out.exists()

        unpacked = unpack_universe(archive, tmp_path / "lib")
        new_db = unpacked / CACHE_DIRNAME / CACHE_DB_NAME
        original, exported = read_definition(db), read_definition(new_db)
        assert exported["meta"]["universe_name"] == original["meta"]["universe_name"]
        assert {e["entity_id"] for e in exported["entities"]} == \
               {e["entity_id"] for e in original["entities"]}
        # Les saves ne voyagent pas dans l'archive (définition seule).
        assert _rows(new_db, "SELECT * FROM Saves;") == []

    def test_cli_pack_accepte_un_db(self, db_with_save, tmp_path: Path, capsys):
        from axiom.cli.main import main
        db, _ = db_with_save
        archive = tmp_path / "cli.axiom"
        assert main(["pack", str(db), str(archive)]) == 0
        assert archive.exists()


# ---------------------------------------------------------------------------
# TICKET-027 — sync .db → source après édition Creator Studio
# ---------------------------------------------------------------------------

class TestStudioSyncSource:
    def test_sync_reecrit_la_source(self, source_tree: Path):
        from axiom.library import sync_source_if_any

        db = compile_universe(source_tree)
        # Simule une session Creator Studio : renomme Alice, supprime Bob,
        # ajoute une entité et une entrée de lore directement dans le .db.
        with sqlite3.connect(str(db)) as conn:
            conn.execute("UPDATE Entities SET name = 'Alicia' WHERE entity_id = 'alice';")
            conn.execute("DELETE FROM Entities WHERE entity_id = 'bob';")
            conn.execute(
                "INSERT INTO Entities (entity_id, entity_type, name) VALUES ('carol', 'npc', 'Carol');"
            )
            conn.execute(
                "INSERT INTO Lore_Book (entry_id, category, name, keywords, content) "
                "VALUES ('studio_entry', 'General', 'Studio', '', 'Écrit au Studio.');"
            )
            conn.commit()

        assert sync_source_if_any(db) is True

        assert "Alicia" in (source_tree / "entities" / "alice.toml").read_text(encoding="utf-8")
        assert not (source_tree / "entities" / "bob.toml").exists()
        assert (source_tree / "entities" / "carol.toml").exists()
        lore_files = list((source_tree / "lore").rglob("*.md")) if (source_tree / "lore").is_dir() else []
        assert any("Écrit au Studio." in f.read_text(encoding="utf-8") for f in lore_files)

    def test_cache_considere_frais_apres_sync(self, source_tree: Path):
        """Après sync, la source réécrite correspond au .db : pas de recompil inutile
        (et surtout pas de refresh qui écraserait l'édition Studio)."""
        from axiom.dev import ensure_compiled
        from axiom.library import sync_source_if_any

        db = compile_universe(source_tree)
        with sqlite3.connect(str(db)) as conn:
            conn.execute("UPDATE Entities SET name = 'Alicia' WHERE entity_id = 'alice';")
            conn.commit()
        sync_source_if_any(db)

        mtime = db.stat().st_mtime_ns
        assert ensure_compiled(source_tree) == db
        assert db.stat().st_mtime_ns == mtime  # à jour : non touché
        # Et la définition Studio est toujours là.
        assert _rows(db, "SELECT name FROM Entities WHERE entity_id='alice';") == [("Alicia",)]

    def test_entites_runtime_non_exportees(self, source_tree: Path):
        from axiom.library import sync_source_if_any

        db = compile_universe(source_tree)
        with sqlite3.connect(str(db)) as conn:
            conn.execute(
                "INSERT INTO Entities (entity_id, entity_type, name, origin) "
                "VALUES ('garen', 'player', 'Garen', 'runtime');"
            )
            conn.commit()
        sync_source_if_any(db)
        assert not (source_tree / "entities" / "garen.toml").exists()
        # …mais l'entité reste dans le .db (elle appartient au runtime).
        assert _rows(db, "SELECT entity_id FROM Entities WHERE entity_id='garen';")

    def test_round_trip_apres_sync(self, source_tree: Path, tmp_path: Path):
        """compile(source resynchronisée) == définition du .db Studio."""
        from axiom.library import sync_source_if_any

        db = compile_universe(source_tree)
        with sqlite3.connect(str(db)) as conn:
            conn.execute("UPDATE Entities SET description = 'Forgeronne.' WHERE entity_id = 'alice';")
            conn.commit()
        sync_source_if_any(db)

        recompiled = compile_universe(source_tree, tmp_path / "recheck.db", force=True)
        a, b = read_definition(db), read_definition(recompiled)
        assert {e["entity_id"]: e["description"] for e in a["entities"]} == \
               {e["entity_id"]: e["description"] for e in b["entities"]}

    def test_db_plat_no_op(self, tmp_path: Path):
        from axiom.library import sync_source_if_any
        from axiom.schema import create_universe_db

        flat = tmp_path / "flat.db"
        create_universe_db(str(flat))
        assert sync_source_if_any(flat) is False

    def test_worker_qt_save_full_universe_resync_la_source(self, source_tree: Path):
        """Bout-en-bout réel : le worker Qt du Creator Studio sauvegarde →
        l'arbo texte est réécrite (hook TICKET-027 dans la coquille)."""
        import time

        from PySide6.QtCore import QCoreApplication
        from workers.db_worker import DbWorker

        db = compile_universe(source_tree)
        worker = DbWorker(str(db))
        done: list[bool] = []
        worker.save_complete.connect(lambda: done.append(True))
        worker.save_full_universe(
            entities=[{"entity_id": "alice", "entity_type": "npc", "name": "Alicia",
                       "description": "", "stats": {"Health": "80"}}],
            rules=[],
            meta={"universe_name": "Hotreload"},
            lore_book=[],
        )
        start = time.time()
        while not done and time.time() - start < 5:
            QCoreApplication.processEvents()
            time.sleep(0.01)

        assert done, "save_full_universe n'a pas abouti"
        assert "Alicia" in (source_tree / "entities" / "alice.toml").read_text(encoding="utf-8")
        assert not (source_tree / "entities" / "bob.toml").exists()  # retiré au Studio → retiré du texte


# ---------------------------------------------------------------------------
# Découverte de bibliothèque
# ---------------------------------------------------------------------------

class TestLibraryDiscovery:
    def test_universe_root_for(self, source_tree: Path):
        db = compile_universe(source_tree)
        assert universe_root_for(db) == source_tree
        assert universe_root_for(source_tree / "universe.toml") is None
        assert universe_root_for("/tmp/flat.db") is None

    def test_discover_mixte_db_plat_et_dossier_source(self, tmp_path: Path, source_tree: Path):
        from axiom.schema import create_universe_db

        lib = tmp_path / "library"
        lib.mkdir()
        # 1. Un .db plat legacy.
        flat = lib / "legacy.db"
        create_universe_db(str(flat))
        with sqlite3.connect(str(flat)) as conn:
            conn.execute("INSERT INTO Universe_Meta (key, value) VALUES ('universe_name', 'Legacy');")
            conn.commit()
        # 2. Un univers-dossier (déplacé dans la bibliothèque).
        import shutil
        shutil.copytree(source_tree, lib / "hotreload")
        # 3. Un dossier cassé (universe.toml invalide) et un dossier étranger.
        _write(lib / "broken" / "universe.toml", "pas du toml [[[")
        (lib / "unrelated").mkdir()

        entries = discover_universes(lib)

        assert [e["name"] for e in entries] == ["Legacy", "Hotreload"]
        flat_entry, dir_entry = entries
        assert flat_entry["source_dir"] is None
        assert dir_entry["source_dir"] == str(lib / "hotreload")
        assert Path(dir_entry["db_path"]).exists()  # compilé à la demande

    def test_discover_dossier_absent(self, tmp_path: Path):
        assert discover_universes(tmp_path / "nope") == []
