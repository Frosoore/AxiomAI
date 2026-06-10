"""tests/test_populate_engine.py

B3 — l'authoring LLM d'univers vit dans le moteur (`axiom.populate`, zéro Qt).
LLM factice injecté : on teste le câblage contexte → insertion idempotente,
pas la génération. La reprise par chunk des entités est couverte par
`tests/test_populate_resume.py`.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from axiom import populate as pop
from axiom.schema import create_universe_db


class _FakeLLM:
    """Renvoie la même réponse JSON à chaque appel."""

    def __init__(self, payload):
        self._payload = payload
        self.calls = 0

    def complete(self, *_a, **_k):
        self.calls += 1
        return SimpleNamespace(tool_call=self._payload)


@pytest.fixture
def db(tmp_path: Path) -> str:
    path = tmp_path / "u.db"
    create_universe_db(str(path))
    with sqlite3.connect(str(path)) as conn:
        conn.execute(
            "INSERT INTO Universe_Meta (key, value) VALUES ('global_lore', 'Un monde.');")
        conn.commit()
    return str(path)


def _rows(db_path: str, query: str) -> list:
    with sqlite3.connect(db_path) as conn:
        return conn.execute(query).fetchall()


def test_populate_meta_ecrit_les_cles(db):
    llm = _FakeLLM({"universe_name": "Aether", "global_lore": "Nouveau lore."})
    assert pop.populate_meta(db, llm=llm) is True
    meta = dict(_rows(db, "SELECT key, value FROM Universe_Meta;"))
    assert meta["universe_name"] == "Aether"
    assert meta["global_lore"] == "Nouveau lore."


def test_populate_meta_reponse_vide(db):
    assert pop.populate_meta(db, llm=_FakeLLM({})) is False


def test_populate_stats_idempotent(db):
    llm = _FakeLLM({"stats": [
        {"name": "Santé", "value_type": "numeric", "parameters": {"min": 0, "max": 100}},
    ]})
    assert pop.populate_stats(db, llm=llm) == 1
    assert pop.populate_stats(db, llm=llm) == 0  # déjà connue
    rows = _rows(db, "SELECT stat_id, name, parameters FROM Stat_Definitions;")
    assert len(rows) == 1
    assert rows[0][0] == "sant"  # id ascii-safe
    assert json.loads(rows[0][2]) == {"min": 0, "max": 100}


def test_populate_rules_idempotent(db):
    llm = _FakeLLM({"rules": [
        {"rule_id": "r1", "priority": 5, "conditions": {"a": 1}, "actions": [{"x": 2}]},
    ]})
    assert pop.populate_rules(db, llm=llm) == 1
    assert pop.populate_rules(db, llm=llm) == 0
    assert len(_rows(db, "SELECT rule_id FROM Rules;")) == 1


def test_populate_events_insere(db):
    llm = _FakeLLM({"events": [
        {"title": "L'éclipse", "description": "…", "trigger_minute": 1440},
    ]})
    assert pop.populate_events(db, llm=llm) == 1
    rows = _rows(db, "SELECT event_id, trigger_minute FROM Scheduled_Events;")
    assert rows == [("l_clipse", 1440)]


def test_populate_events_collision_id_sautee(db):
    """TICKET-035 : un titre reproposé (même event_id dérivé) ne crashe plus en
    IntegrityError — la ligne est sautée (idempotence)."""
    llm = _FakeLLM({"events": [
        {"title": "L'éclipse", "description": "…", "trigger_minute": 1440},
    ]})
    assert pop.populate_events(db, llm=llm) == 1
    assert pop.populate_events(db, llm=llm) == 0  # relance : rien à insérer
    assert len(_rows(db, "SELECT event_id FROM Scheduled_Events;")) == 1


def test_populate_stats_collision_id_desambiguisee(db):
    """TICKET-035 : deux noms différents → même _safe_id (PK) : la 2e stat est
    insérée sous un id désambiguïsé au lieu de crasher."""
    assert pop.populate_stats(db, llm=_FakeLLM({"stats": [{"name": "Force!"}]})) == 1
    assert pop.populate_stats(db, llm=_FakeLLM({"stats": [{"name": "Force?"}]})) == 1
    rows = _rows(db, "SELECT stat_id, name FROM Stat_Definitions;")
    assert len(rows) == 2
    assert {r[1] for r in rows} == {"Force!", "Force?"}


def test_populate_entities_nom_non_latin(db):
    """TICKET-041 : un nom 100 % non-latin reçoit un id déterministe au lieu
    d'être silencieusement sauté ; la relance reste idempotente."""
    llm = _FakeLLM({"entities": [
        {"name": "山田", "entity_type": "npc", "description": "Forgeron."},
    ]})
    assert pop.populate_entities(db, mode="custom", custom_text="x", llm=llm) == 1
    rows = _rows(db, "SELECT entity_id, name FROM Entities;")
    assert rows[0][1] == "山田"
    assert rows[0][0].startswith("ent_")
    # Relance : même id dérivé → entité connue, rien d'inséré.
    assert pop.populate_entities(db, mode="custom", custom_text="x", llm=llm) == 0


def test_populate_lore_idempotent(db):
    llm = _FakeLLM({"lore_entries": [
        {"category": "Faction", "name": "La Guilde", "content": "Secrète."},
    ]})
    assert pop.populate_lore(db, llm=llm) == 1
    assert pop.populate_lore(db, llm=llm) == 0
    assert _rows(db, "SELECT name FROM Lore_Book;") == [("La Guilde",)]


def test_populate_map_parents_et_connexions(db):
    llm = _FakeLLM({
        "locations": [
            {"location_id": "monde", "name": "Monde", "scale": "world", "parent_id": "none"},
            {"location_id": "ville", "name": "Ville", "scale": "city", "parent_id": "monde"},
        ],
        "connections": [
            {"source_id": "monde", "target_id": "ville", "distance_km": 12},
            {"source_id": "ville", "target_id": "fantome"},  # nœud inconnu → sautée
        ],
    })
    out = pop.populate_map(db, llm=llm)
    assert out == {"added_locs": 2, "added_conns": 1}
    locs = dict(_rows(db, "SELECT location_id, parent_id FROM Locations;"))
    assert locs == {"monde": None, "ville": "monde"}  # 'none' → NULL
    conns = set(_rows(db, "SELECT source_id, target_id FROM Location_Connections;"))
    assert conns == {("monde", "ville"), ("ville", "monde")}  # bidirectionnel


def test_populate_entities_via_consigne(db):
    llm = _FakeLLM({"entities": [
        {"name": "Le Forgeron", "entity_type": "npc", "description": "Bourru.",
         "stats": {"inconnue": "9"}},  # stat non définie → filtrée
    ]})
    assert pop.populate_entities(db, mode="custom", custom_text="3 marchands", llm=llm) == 1
    assert llm.calls == 1  # mode custom = un seul chunk
    assert _rows(db, "SELECT entity_id FROM Entities;") == [("le_forgeron",)]
    assert _rows(db, "SELECT * FROM Entity_Stats;") == []


def test_populate_sync_la_source(tmp_path: Path):
    """Univers-dossier : le contenu généré atterrit aussi dans l'arbo texte (TICKET-027)."""
    from axiom.compile import compile_universe

    root = tmp_path / "src"
    root.mkdir()
    (root / "universe.toml").write_text(
        '[meta]\nname = "T"\n[narrative]\nsystem_prompt = "GM."\n', encoding="utf-8")
    cache = str(compile_universe(root))

    llm = _FakeLLM({"lore_entries": [{"category": "Faction", "name": "La Guilde",
                                      "content": "Secrète."}]})
    assert pop.populate_lore(cache, llm=llm) == 1
    lore_files = list((root / "lore").rglob("*.md"))
    assert any("guilde" in f.read_text(encoding="utf-8").lower() for f in lore_files)


def test_cli_populate(db, monkeypatch, capsys):
    import axiom.config as config_mod
    from axiom.cli.main import main

    llm = _FakeLLM({"lore_entries": [{"category": "General", "name": "X", "content": "y"}]})
    monkeypatch.setattr(config_mod, "build_llm_from_config", lambda *a, **k: llm)

    assert main(["populate", db, "-t", "lore"]) == 0
    assert "lore : 1" in capsys.readouterr().out
    assert _rows(db, "SELECT name FROM Lore_Book;") == [("X",)]


def test_cli_populate_univers_introuvable(tmp_path: Path, capsys):
    from axiom.cli.main import main

    assert main(["populate", str(tmp_path / "nope.db"), "-t", "lore"]) == 2
