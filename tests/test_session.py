"""Tests de l'API publique headless du moteur : axiom.Session / axiom.Universe.

Ces tests valident le câblage de la façade (construction, turn_id, checkpoints,
stats, reconstruction d'historique) contre une vraie base SQLite, SANS Qt et
SANS LLM réel. La correction de `process_turn` lui-même est couverte par
tests/test_arbitrator.py.
"""

import logging
from logging.handlers import RotatingFileHandler

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
    """Universe.load surfaces the db path, a non-empty name, and lists the
    save that was created in the fixture."""
    db, save_id = universe_db
    universe = Universe.load(db)
    assert universe.path == db
    assert universe.name  # non vide (nom ou stem du fichier)
    saves = universe.list_saves()
    assert any(s.get("save_id") == save_id for s in saves)


def test_session_constructs_against_real_db(universe_db):
    """Session wires up against a real SQLite universe and exposes it via
    .universe.path (façade construction smoke test)."""
    # NB : l'absence de Qt est prouvée hors-pytest (conftest charge QApplication
    # pour toute la suite). Ici on valide juste le câblage de la façade.
    db, save_id = universe_db
    sess = Session(db, save_id, llm=_DummyLLM(), vector_memory=_DummyVectorMemory())
    assert sess.universe.path == db


def test_new_save_starts_at_turn_zero_with_no_checkpoints(universe_db):
    """A freshly-created save reports turn 0, no checkpoints, empty stats and
    empty history."""
    db, save_id = universe_db
    sess = Session(db, save_id, llm=_DummyLLM(), vector_memory=_DummyVectorMemory())
    assert sess.turn_id == 0
    assert sess.list_checkpoints() == []
    assert sess.current_stats() == {}
    assert sess._load_history() == []


def test_load_history_maps_events_to_roles(universe_db):
    """_load_history maps user_input events to the 'user' role and
    narrative_text events to the 'assistant' role, in order."""
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
    """When a narrative_text event carries multiple variants, _load_history
    returns the one pointed to by the 'active' index."""
    db, save_id = universe_db
    events = EventSourcer(db)
    events.append_event(
        save_id, 1, "narrative_text", "narrator",
        {"active": 1, "variants": ["A", "B"]},
    )
    sess = Session(db, save_id, llm=_DummyLLM(), vector_memory=_DummyVectorMemory())
    assert sess._load_history() == [{"role": "assistant", "content": "B"}]


def test_data_dir_sandboxes_vector_and_logs_under_injected_root(universe_db, tmp_path):
    """Étape 5 : `Session(data_dir=...)` range vector ET logs sous le dossier injecté.

    Prouve l'injection de chemins (Pilier 1) : la VectorMemory par défaut et le
    fichier de logs atterrissent sous `data_dir`, pas dans les dossiers globaux.
    L'état global (overrides paths + handler de logs) est restauré en fin de test.
    """
    from axiom import paths
    from axiom import logger as axiom_logger

    db, save_id = universe_db
    data_dir = tmp_path / "embedded"
    try:
        # vector_memory=None → Session construit la VectorMemory par défaut.
        sess = Session(db, save_id, llm=_DummyLLM(), data_dir=data_dir)

        # 1. VectorMemory sous <data_dir>/vector/<save_id>.
        assert sess._vector_memory._persist_dir == str(data_dir / "vector" / save_id)

        # 2. Le file handler de logs pointe sous <data_dir>/logs.
        file_handlers = [
            h for h in logging.getLogger("Axiom AI").handlers
            if isinstance(h, RotatingFileHandler)
        ]
        assert file_handlers, "un RotatingFileHandler est attendu après injection"
        assert str(data_dir / "logs") in file_handlers[0].baseFilename
    finally:
        paths.reset()
        axiom_logger.reconfigure()  # restaure le handler de logs par défaut


def test_config_stays_machine_global_without_override(tmp_path, monkeypatch):
    """Hybride (Étape 5) : sans surcharge, la config reste machine-globale.

    `data_dir` injecté ne doit PAS déplacer settings.json/global.db : seul un
    `config_dir` explicite (ou AXIOM_CONFIG_DIR) le fait.
    """
    from axiom import paths

    monkeypatch.delenv("AXIOM_CONFIG_DIR", raising=False)
    try:
        paths.configure(data_dir=tmp_path / "data")
        assert paths.has_config_override() is False
        assert paths.get_config_dir() == paths.CONFIG_DIR

        paths.configure(config_dir=tmp_path / "cfg")
        assert paths.has_config_override() is True
        assert paths.get_settings_file() == tmp_path / "cfg" / "settings.json"
        assert paths.get_global_db_file() == tmp_path / "cfg" / "global.db"
    finally:
        paths.reset()
