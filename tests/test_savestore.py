"""tests/test_savestore.py

Tests du §7.6 (Pilier 2) : saves séparées de l'univers (`axiom.savestore`).

Garanties centrales :
- une nouvelle partie = un fichier `saves/<univers>/save_<uuid>.db` autonome
  (définition copiée), jouable par `Session` sans rien changer au moteur ;
- les saves legacy embarquées dans le `.db` univers restent listées/jouables ;
- patcher la source de l'univers resynchronise la définition de la save à
  l'ouverture, sans toucher au journal ni aux entités runtime.

Aucun LLM, aucun Qt : pur moteur.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from axiom import paths
from axiom.compile import compile_universe
from axiom.db_helpers import create_new_save
from axiom.savestore import (
    create_save,
    delete_save,
    delete_universe_saves,
    is_separated_save_db,
    list_saves,
    prepare_save_for_play,
    resolve_save_db,
    saves_dir_for,
    universe_key,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path: Path):
    """Toutes les saves vont sous tmp (jamais dans ~/AxiomAI)."""
    paths.configure(data_dir=tmp_path / "data")
    yield
    paths.reset()


@pytest.fixture
def source_tree(tmp_path: Path) -> Path:
    root = tmp_path / "demo_src"
    _write(root / "universe.toml", '[meta]\nname = "Demo"\n\n[narrative]\nsystem_prompt = "GM."\n')
    _write(root / "entities" / "alice.toml",
           'entity_id = "alice"\nname = "Alice"\n\n[stats]\nHealth = "80"\n')
    _write(root / "items" / "sword.toml", 'item_id = "sword"\nname = "Sword"\n')
    return root


@pytest.fixture
def universe_db(source_tree: Path) -> Path:
    return compile_universe(source_tree)


class TestCreateSave:
    def test_cree_un_fichier_autonome_avec_definition(self, universe_db: Path):
        info = create_save(universe_db, "Hero", "Normal", "Persona.")
        save_db = Path(info["db_path"])

        assert save_db.exists()
        assert save_db.parent == saves_dir_for(universe_db)
        assert save_db.name == f"save_{info['save_id']}.db"
        assert is_separated_save_db(save_db)

        with sqlite3.connect(str(save_db)) as conn:
            entities = {r[0] for r in conn.execute("SELECT entity_id FROM Entities;")}
            items = {r[0] for r in conn.execute("SELECT item_id FROM Item_Definitions;")}
            meta = dict(conn.execute("SELECT key, value FROM Save_Meta;").fetchall())
            saves = conn.execute("SELECT save_id, player_name FROM Saves;").fetchall()
        assert entities == {"alice"}
        assert items == {"sword"}
        assert meta["universe_source"] == str(universe_db.parent.parent)
        assert saves == [(info["save_id"], "Hero")]

    def test_universe_db_plat_sans_source(self, tmp_path: Path):
        from axiom.schema import create_universe_db

        flat = tmp_path / "flat.db"
        create_universe_db(str(flat))
        info = create_save(flat, "Hero", "Normal")
        save_db = Path(info["db_path"])
        with sqlite3.connect(str(save_db)) as conn:
            meta = dict(conn.execute("SELECT key, value FROM Save_Meta;").fetchall())
        assert meta["universe_source"] == ""
        assert universe_key(flat) == "flat"

    def test_session_joue_sur_la_save_separee(self, universe_db: Path):
        from axiom.session import Session

        info = create_save(universe_db, "Hero", "Normal")

        class FakeLLM:
            def is_available(self):
                return True

        session = Session(info["db_path"], info["save_id"], llm=FakeLLM(), mode="Normal")
        assert session.current_stats() == {}  # save fraîche : rien de matérialisé (normal)

        # La définition copiée est bien celle que le moteur lit en jeu.
        from axiom.db_helpers import load_active_entities

        entities = {e["entity_id"]: e for e in load_active_entities(info["db_path"])}
        assert entities["alice"]["stats"]["Health"] == "80"

    def test_l_univers_n_est_pas_touche(self, universe_db: Path):
        create_save(universe_db, "Hero", "Normal")
        with sqlite3.connect(str(universe_db)) as conn:
            assert conn.execute("SELECT COUNT(*) FROM Saves;").fetchone()[0] == 0


class TestListResolve:
    def test_fusion_separees_et_embarquees(self, universe_db: Path):
        legacy_id = create_new_save(str(universe_db), "Old", "Normal")
        sep = create_save(universe_db, "New", "Hardcore")

        rows = list_saves(universe_db)
        by_id = {r["save_id"]: r for r in rows}
        assert by_id[legacy_id]["storage"] == "embedded"
        assert by_id[legacy_id]["db_path"] == str(universe_db)
        assert by_id[sep["save_id"]]["storage"] == "separated"
        assert by_id[sep["save_id"]]["db_path"] == sep["db_path"]

    def test_resolve_save_db(self, universe_db: Path):
        sep = create_save(universe_db, "New", "Normal")
        legacy_id = create_new_save(str(universe_db), "Old", "Normal")
        assert resolve_save_db(universe_db, sep["save_id"]) == sep["db_path"]
        assert resolve_save_db(universe_db, legacy_id) == str(universe_db)
        assert resolve_save_db(universe_db, "inconnu") is None


class TestRefreshOnOpen:
    def test_patch_univers_repercute_sans_toucher_au_runtime(
        self, universe_db: Path, source_tree: Path
    ):
        info = create_save(universe_db, "Hero", "Normal")
        save_db = info["db_path"]
        # La partie vit : entité runtime + un event.
        with sqlite3.connect(save_db) as conn:
            conn.execute(
                "INSERT INTO Entities (entity_id, entity_type, name, origin) "
                "VALUES ('garen', 'player', 'Garen', 'runtime');"
            )
            conn.execute(
                "INSERT INTO Event_Log (save_id, turn_id, event_type, target_entity, payload) "
                "VALUES (?, 1, 'stat_change', 'garen', '{\"stat_key\": \"Health\", \"delta\": -3}');",
                (info["save_id"],),
            )
            conn.commit()
        # L'auteur patche son univers.
        _write(source_tree / "entities" / "bob.toml", 'entity_id = "bob"\nname = "Bob"\n')

        resolved = prepare_save_for_play(universe_db, info["save_id"])

        assert resolved == save_db
        with sqlite3.connect(save_db) as conn:
            entities = {r[0] for r in conn.execute("SELECT entity_id FROM Entities;")}
            events = conn.execute("SELECT COUNT(*) FROM Event_Log;").fetchone()[0]
        assert {"alice", "bob", "garen"} <= entities  # patch appliqué, joueur intact
        assert events == 1

    def test_no_op_si_source_inchangee(self, universe_db: Path):
        from axiom.savestore import refresh_save_definition

        info = create_save(universe_db, "Hero", "Normal")
        assert refresh_save_definition(info["db_path"]) is False

    def test_source_disparue_non_bloquante(self, universe_db: Path, source_tree: Path):
        import shutil

        info = create_save(universe_db, "Hero", "Normal")
        shutil.rmtree(source_tree)
        # La save reste résoluble et jouable (définition embarquée).
        assert prepare_save_for_play(universe_db, info["save_id"]) == info["db_path"]


class TestCliOnSeparatedSaves:
    def test_save_cmds_resolvent_la_save_separee(
        self, universe_db: Path, source_tree: Path, tmp_path: Path
    ):
        """save-edit / save-show / save-export / save-import / save-fork via le
        dossier source, sur une save qui vit dans son propre fichier."""
        from axiom.cli.main import build_parser
        from axiom.saves import materialize_state

        info = create_save(universe_db, "Hero", "Normal")
        save_id, save_db = info["save_id"], info["db_path"]
        parser = build_parser()

        # save-edit (correction en place) sur la save séparée.
        patch = tmp_path / "patch.toml"
        patch.write_text('[state.alice]\nHealth = "55"\n', encoding="utf-8")
        args = parser.parse_args(["save-edit", str(source_tree), save_id, str(patch)])
        assert args.func(args) == 0
        assert materialize_state(save_db, save_id)["entities"]["alice"]["Health"] == "55"

        # save-show.
        args = parser.parse_args(["save-show", str(source_tree), save_id])
        assert args.func(args) == 0

        # save-export → save-import : la nouvelle save naît séparée elle aussi.
        out = tmp_path / "state.toml"
        args = parser.parse_args(["save-export", str(source_tree), save_id, str(out)])
        assert args.func(args) == 0
        before = {r["save_id"] for r in list_saves(universe_db)}
        args = parser.parse_args(["save-import", str(source_tree), str(out), "--name", "Clone"])
        assert args.func(args) == 0
        after = list_saves(universe_db)
        new = [r for r in after if r["save_id"] not in before]
        assert len(new) == 1
        assert new[0]["storage"] == "separated"
        assert new[0]["player_name"] == "Clone"

        # save-fork (reste dans le fichier de la save source).
        args = parser.parse_args(["save-fork", str(source_tree), save_id, "--name", "Forked"])
        assert args.func(args) == 0
        forked = [r for r in list_saves(universe_db) if r["player_name"] == "Forked"]
        assert forked and forked[0]["db_path"] == save_db

    def test_save_inconnue_message_clair(self, source_tree: Path, universe_db: Path, capsys):
        from axiom.cli.main import build_parser

        parser = build_parser()
        args = parser.parse_args(["save-show", str(source_tree), "ghost"])
        assert args.func(args) == 2
        assert "introuvable" in capsys.readouterr().err


class TestPackUnpack:
    def _played_separated_save(self, universe_db: Path) -> dict:
        info = create_save(universe_db, "Hero", "Normal")
        with sqlite3.connect(info["db_path"]) as conn:
            conn.execute(
                "INSERT INTO Event_Log (save_id, turn_id, event_type, target_entity, payload) "
                "VALUES (?, 1, 'stat_change', 'alice', '{\"stat_key\": \"Health\", \"delta\": -7}');",
                (info["save_id"],),
            )
            conn.commit()
        return info

    def test_round_trip_save_separee(self, universe_db: Path, tmp_path: Path):
        from axiom.savestore import pack_save, unpack_save

        info = self._played_separated_save(universe_db)
        archive = tmp_path / "hero.axiomsave"
        pack_save(universe_db, info["save_id"], archive)
        assert archive.exists()

        # Ré-import dans le même univers : le save_id existe → ré-identifiée.
        out = unpack_save(archive, universe_db)
        assert out["save_id"] != info["save_id"]
        with sqlite3.connect(out["db_path"]) as conn:
            events = conn.execute(
                "SELECT save_id, event_type FROM Event_Log;"
            ).fetchall()
        assert events == [(out["save_id"], "stat_change")]  # journal re-scopé
        ids = {r["save_id"] for r in list_saves(universe_db)}
        assert {info["save_id"], out["save_id"]} <= ids

    def test_pack_save_embarquee_legacy(self, universe_db: Path, tmp_path: Path):
        from axiom.savestore import pack_save, unpack_save

        legacy_id = create_new_save(str(universe_db), "Old", "Normal")
        archive = tmp_path / "old.axiomsave"
        pack_save(universe_db, legacy_id, archive)

        # L'original embarqué est intact, et aucune copie séparée ne traîne.
        with sqlite3.connect(str(universe_db)) as conn:
            assert conn.execute("SELECT COUNT(*) FROM Saves;").fetchone()[0] == 1
        assert [r["storage"] for r in list_saves(universe_db)] == ["embedded"]

        out = unpack_save(archive, universe_db)
        assert out["save_id"] != legacy_id  # collision → ré-identifiée
        assert Path(out["db_path"]).exists()

    def test_unpack_relie_la_save_a_l_univers_local(self, universe_db: Path,
                                                    source_tree: Path, tmp_path: Path):
        """TICKET-036 : l'archive porte les chemins de l'exportateur — l'import
        doit re-lier Save_Meta à l'univers de destination, sinon la save ne se
        resynchronise jamais avec la source locale."""
        from axiom.savestore import pack_save, refresh_save_definition, unpack_save

        info = self._played_separated_save(universe_db)
        archive = tmp_path / "hero.axiomsave"
        pack_save(universe_db, info["save_id"], archive)

        # Simule une archive venant d'une autre machine : chemins exotiques.
        with sqlite3.connect(info["db_path"]) as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO Save_Meta (key, value) VALUES (?, ?);",
                [("universe_db", "/machine/exportateur/u.db"),
                 ("universe_source", "/machine/exportateur/src"),
                 ("definition_hash", "stale")],
            )
            conn.commit()
        pack_save(universe_db, info["save_id"], archive)

        out = unpack_save(archive, universe_db)
        with sqlite3.connect(out["db_path"]) as conn:
            meta = dict(conn.execute("SELECT key, value FROM Save_Meta;").fetchall())
        assert meta["universe_db"] == str(universe_db)
        assert meta["universe_source"] == str(source_tree)
        assert meta["universe_key"] == "demo_src"
        assert meta["definition_hash"] == ""  # → resync au premier lancement

        # La resync depuis la source LOCALE fonctionne désormais.
        _write(source_tree / "entities" / "bob.toml",
               'entity_id = "bob"\nname = "Bob"\n')
        assert refresh_save_definition(out["db_path"]) is True
        with sqlite3.connect(out["db_path"]) as conn:
            ids = {r[0] for r in conn.execute("SELECT entity_id FROM Entities;")}
        assert "bob" in ids

    def test_unpack_refuse_autre_univers(self, universe_db: Path, tmp_path: Path):
        from axiom.savestore import SaveStoreError, pack_save, unpack_save
        from axiom.schema import create_universe_db

        info = self._played_separated_save(universe_db)
        archive = tmp_path / "hero.axiomsave"
        pack_save(universe_db, info["save_id"], archive)

        other = tmp_path / "other.db"
        create_universe_db(str(other))
        with pytest.raises(SaveStoreError):
            unpack_save(archive, other)
        # --force passe outre.
        out = unpack_save(archive, other, force=True)
        assert Path(out["db_path"]).exists()

    def test_cli_save_pack_unpack(self, universe_db: Path, source_tree: Path, tmp_path: Path):
        from axiom.cli.main import main

        info = self._played_separated_save(universe_db)
        archive = tmp_path / "cli.axiomsave"
        assert main(["save-pack", str(source_tree), info["save_id"], str(archive)]) == 0
        assert main(["save-unpack", str(source_tree), str(archive)]) == 0
        assert len(list_saves(universe_db)) == 2


class TestDuplicate:
    """TICKET-028 : « Dupliquer » = save manuelle (point de branche au présent)."""

    def _played_separated_save(self, universe_db: Path) -> dict:
        info = create_save(universe_db, "Hero", "Normal")
        with sqlite3.connect(info["db_path"]) as conn:
            conn.execute(
                "INSERT INTO Event_Log (save_id, turn_id, event_type, target_entity, payload) "
                "VALUES (?, 1, 'stat_change', 'alice', '{\"stat_key\": \"Health\", \"delta\": -7}');",
                (info["save_id"],),
            )
            conn.commit()
        return info

    def test_separee_copie_dans_un_nouveau_fichier(self, universe_db: Path):
        from axiom.savestore import duplicate_save

        info = self._played_separated_save(universe_db)
        out = duplicate_save(universe_db, info["save_id"], player_name="Hero (fork)")

        assert out["save_id"] != info["save_id"]
        assert out["db_path"] != info["db_path"]
        assert Path(out["db_path"]).exists()
        assert Path(info["db_path"]).exists()  # l'original est intact

        with sqlite3.connect(out["db_path"]) as conn:
            saves = conn.execute("SELECT save_id, player_name FROM Saves;").fetchall()
            events = conn.execute("SELECT save_id, event_type FROM Event_Log;").fetchall()
        # Un seul Saves par fichier (modèle 1 save = 1 fichier), journal re-scopé.
        assert saves == [(out["save_id"], "Hero (fork)")]
        assert events == [(out["save_id"], "stat_change")]

        ids = {r["save_id"] for r in list_saves(universe_db)}
        assert {info["save_id"], out["save_id"]} <= ids

    def test_separee_garde_le_nom_par_defaut(self, universe_db: Path):
        from axiom.savestore import duplicate_save

        info = create_save(universe_db, "Hero", "Normal")
        out = duplicate_save(universe_db, info["save_id"])
        with sqlite3.connect(out["db_path"]) as conn:
            name = conn.execute("SELECT player_name FROM Saves;").fetchone()[0]
        assert name == "Hero"

    def test_embarquee_fork_dans_la_meme_base(self, universe_db: Path):
        from axiom.savestore import duplicate_save

        legacy_id = create_new_save(str(universe_db), "Old", "Normal")
        out = duplicate_save(universe_db, legacy_id, player_name="Old (fork)")

        assert out["save_id"] != legacy_id
        assert Path(out["db_path"]) == universe_db  # reste embarquée (legacy)
        with sqlite3.connect(str(universe_db)) as conn:
            assert conn.execute("SELECT COUNT(*) FROM Saves;").fetchone()[0] == 2

    def test_save_inconnue(self, universe_db: Path):
        from axiom.savestore import SaveStoreError, duplicate_save

        with pytest.raises(SaveStoreError):
            duplicate_save(universe_db, "nope")


class TestConvertFlatDb:
    """TICKET-029 : conversion d'un `.db` plat en univers-dossier."""

    def _flat_universe(self, tmp_path: Path) -> Path:
        seed = tmp_path / "seed"
        _write(seed / "universe.toml",
               '[meta]\nname = "Mon Univers"\n\n[narrative]\nsystem_prompt = "GM."\n')
        _write(seed / "entities" / "alice.toml",
               'entity_id = "alice"\nname = "Alice"\n\n[stats]\nHealth = "80"\n')
        lib = tmp_path / "lib"
        lib.mkdir()
        return compile_universe(seed, lib / "MonUnivers.db")

    def test_conversion_complete(self, tmp_path: Path):
        from axiom.library import convert_flat_db_to_folder

        flat = self._flat_universe(tmp_path)
        sid = create_new_save(str(flat), "Hero", "Normal")

        out = convert_flat_db_to_folder(flat)
        root = Path(out["source_dir"])
        cache = Path(out["db_path"])

        # Dossier source + cache compilé, même clé d'univers que le .db plat.
        assert root == flat.parent / "MonUnivers"
        assert (root / "universe.toml").exists()
        assert (root / "entities" / "alice.toml").exists()
        assert cache.is_file()
        assert universe_key(cache) == universe_key(flat) == "MonUnivers"

        # La save embarquée est devenue séparée, reliée à la nouvelle source.
        rows = list_saves(cache)
        assert [(r["save_id"], r["storage"]) for r in rows] == [(sid, "separated")]
        with sqlite3.connect(rows[0]["db_path"]) as conn:
            meta = dict(conn.execute("SELECT key, value FROM Save_Meta;").fetchall())
        assert meta["universe_source"] == str(root)
        assert meta["universe_db"] == str(cache)

        # L'original sort de la bibliothèque mais reste récupérable.
        assert not flat.exists()
        assert flat.with_name("MonUnivers.db.bak").exists()

    def test_conversion_n_exporte_pas_le_joueur(self, tmp_path: Path):
        """TICKET-037 : l'entité joueur (créée au lobby) ne doit pas devenir
        une entité de DÉFINITION de l'univers converti — mais elle reste dans
        la save extraite, et la resync ne la supprime pas."""
        from axiom.db_helpers import create_player_entity
        from axiom.library import convert_flat_db_to_folder
        from axiom.savestore import refresh_save_definition

        flat = self._flat_universe(tmp_path)
        sid = create_new_save(str(flat), "Hero", "Normal")
        player_id = create_player_entity(str(flat), "Hero")
        # Simule un joueur d'avant la colonne `origin` (défaut de migration =
        # 'definition') : c'est le cas legacy que la conversion doit rattraper.
        with sqlite3.connect(str(flat)) as conn:
            conn.execute(
                "UPDATE Entities SET origin = 'definition' WHERE entity_id = ?;",
                (player_id,),
            )
            conn.commit()

        out = convert_flat_db_to_folder(flat)
        root = Path(out["source_dir"])
        cache = Path(out["db_path"])

        # Le joueur n'est ni dans la source texte, ni dans le cache compilé.
        ent_ids = set()
        for f in (root / "entities").glob("*.toml"):
            import tomllib
            ent_ids.add(tomllib.loads(f.read_text(encoding="utf-8"))["entity_id"])
        assert ent_ids == {"alice"}
        with sqlite3.connect(str(cache)) as conn:
            cache_ids = {r[0] for r in conn.execute("SELECT entity_id FROM Entities;")}
        assert player_id not in cache_ids

        # La save extraite garde son joueur, marqué runtime, et il survit
        # à une resynchronisation depuis la nouvelle source.
        save_db = list_saves(cache)[0]["db_path"]
        _write(root / "entities" / "bob.toml", 'entity_id = "bob"\nname = "Bob"\n')
        assert refresh_save_definition(save_db) is True
        with sqlite3.connect(save_db) as conn:
            rows = dict(conn.execute("SELECT entity_id, origin FROM Entities;").fetchall())
        assert rows.get(player_id) == "runtime"
        assert "bob" in rows
        assert sid in {r["save_id"] for r in list_saves(cache)}

    def test_refuse_un_cache_d_univers_dossier(self, universe_db: Path):
        from axiom.library import LibraryError, convert_flat_db_to_folder

        with pytest.raises(LibraryError):
            convert_flat_db_to_folder(universe_db)

    def test_refuse_si_le_dossier_existe(self, tmp_path: Path):
        from axiom.library import LibraryError, convert_flat_db_to_folder

        flat = self._flat_universe(tmp_path)
        (flat.parent / "MonUnivers").mkdir()
        with pytest.raises(LibraryError):
            convert_flat_db_to_folder(flat)


class TestDelete:
    def test_delete_save_separee_efface_le_fichier(self, universe_db: Path):
        info = create_save(universe_db, "Hero", "Normal")
        assert delete_save(universe_db, info["save_id"]) is True
        assert not Path(info["db_path"]).exists()
        assert list_saves(universe_db) == []

    def test_delete_save_embarquee_garde_l_univers(self, universe_db: Path):
        legacy_id = create_new_save(str(universe_db), "Old", "Normal")
        assert delete_save(universe_db, legacy_id) is True
        assert universe_db.exists()

    def test_delete_universe_saves(self, universe_db: Path):
        create_save(universe_db, "A", "Normal")
        create_save(universe_db, "B", "Normal")
        assert saves_dir_for(universe_db).is_dir()
        delete_universe_saves(universe_db)
        assert not saves_dir_for(universe_db).exists()
