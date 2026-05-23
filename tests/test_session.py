"""Tests de l'API publique headless du moteur : axiom.Session / axiom.Universe.

Ces tests valident le câblage de la façade (construction, turn_id, checkpoints,
stats, reconstruction d'historique) contre une vraie base SQLite, SANS Qt et
SANS LLM réel. La correction de `process_turn` lui-même est couverte par
tests/test_arbitrator.py.
"""

import pytest

from axiom.schema import create_universe_db
from axiom.db_helpers import create_new_save
from axiom.events import EventSourcer
from axiom.universe import Universe
from axiom.session import Session


class _DummyLLM:
    """Backend factice : Session ne l'utilise pas hors take_turn()."""


class _DummyVectorMemory:
    """Mémoire vectorielle factice (évite de charger chromadb)."""


@pytest.fixture
def universe_db(tmp_path):
    """Crée un univers SQLite vierge avec une sauvegarde et renvoie (path, save_id)."""
    db = str(tmp_path / "world.axiom")
    create_universe_db(db)
    save_id = create_new_save(db, player_name="Hero", difficulty="Normal")
    return db, save_id


def test_universe_load_exposes_name_and_saves(universe_db):
    db, save_id = universe_db
    universe = Universe.load(db)
    assert universe.path == db
    assert universe.name  # non vide (nom ou stem du fichier)
    saves = universe.list_saves()
    assert any(s.get("save_id") == save_id for s in saves)


def test_session_constructs_against_real_db(universe_db):
    # NB : l'absence de Qt est prouvée hors-pytest (conftest charge QApplication
    # pour toute la suite). Ici on valide juste le câblage de la façade.
    db, save_id = universe_db
    sess = Session(db, save_id, llm=_DummyLLM(), vector_memory=_DummyVectorMemory())
    assert sess.universe.path == db


def test_new_save_starts_at_turn_zero_with_no_checkpoints(universe_db):
    db, save_id = universe_db
    sess = Session(db, save_id, llm=_DummyLLM(), vector_memory=_DummyVectorMemory())
    assert sess.turn_id == 0
    assert sess.list_checkpoints() == []
    assert sess.current_stats() == {}
    assert sess._load_history() == []


def test_load_history_maps_events_to_roles(universe_db):
    db, save_id = universe_db
    # Injecte un échange (user_input -> user, narrative_text -> assistant).
    events = EventSourcer(db)
    events.append_event(save_id, 1, "user_input", "player", {"text": "bonjour"})
    events.append_event(save_id, 1, "narrative_text", "narrator", {"text": "Le monde s'éveille."})

    sess = Session(db, save_id, llm=_DummyLLM(), vector_memory=_DummyVectorMemory())
    history = sess._load_history()
    assert history == [
        {"role": "user", "content": "bonjour"},
        {"role": "assistant", "content": "Le monde s'éveille."},
    ]


def test_load_history_uses_active_variant(universe_db):
    db, save_id = universe_db
    events = EventSourcer(db)
    events.append_event(
        save_id, 1, "narrative_text", "narrator",
        {"active": 1, "variants": ["A", "B"]},
    )
    sess = Session(db, save_id, llm=_DummyLLM(), vector_memory=_DummyVectorMemory())
    assert sess._load_history() == [{"role": "assistant", "content": "B"}]
