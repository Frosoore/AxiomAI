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
    def query(self, *args, **kwargs):
        return []


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


# ---------------------------------------------------------------------------
# Étape 6 — Parité de Session vs NarrativeWorker (décision du héros Companion)
# ---------------------------------------------------------------------------


class _ScriptedLLM:
    """Backend héros factice : renvoie une décision fixe et capte le prompt reçu."""

    def __init__(self, decision: str = "  Hero draws sword.  ") -> None:
        self._decision = decision
        self.last_prompt = None

    def complete(self, prompt, max_tokens=None):
        self.last_prompt = prompt

        class _Resp:
            narrative_text = self._decision

        return _Resp()


def _add_entity(db, entity_id, entity_type, name, description="", stats=None):
    """Insère une entité active (+ stats) dans la base de l'univers."""
    from axiom.schema import get_connection

    with get_connection(db) as conn:
        conn.execute(
            "INSERT INTO Entities (entity_id, entity_type, name, description, is_active) "
            "VALUES (?, ?, ?, ?, 1);",
            (entity_id, entity_type, name, description),
        )
        for k, v in (stats or {}).items():
            conn.execute(
                "INSERT INTO Entity_Stats (entity_id, stat_key, stat_value) VALUES (?, ?, ?);",
                (entity_id, k, v),
            )


def _set_meta(db, key, value):
    from axiom.schema import get_connection

    with get_connection(db) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO Universe_Meta (key, value) VALUES (?, ?);",
            (key, value),
        )


def _companion_session(db, save_id, hero_llm=None):
    return Session(
        db, save_id, llm=_DummyLLM(), vector_memory=_DummyVectorMemory(),
        mode="Companion", hero_llm=hero_llm,
    )


def test_load_active_entities_returns_worker_shape(universe_db):
    """load_active_entities renvoie les entités actives avec leurs stats, dans
    la forme attendue par la logique héros (parité avec le db_worker)."""
    from axiom.db_helpers import load_active_entities

    db, _ = universe_db
    _add_entity(db, "kael", "npc", "Kael the Brave", "A bold knight", {"HP": "10"})
    ents = load_active_entities(db)
    kael = next(e for e in ents if e["entity_id"] == "kael")
    assert kael == {
        "entity_id": "kael",
        "entity_type": "npc",
        "name": "Kael the Brave",
        "description": "A bold knight",
        "stats": {"HP": "10"},
    }


def test_find_hero_entity_prefers_metadata_id(universe_db):
    """En mode Companion, _find_hero_entity privilégie l'ID configuré dans
    Universe_Meta (companion_hero_id) sur les heuristiques de repli."""
    db, save_id = universe_db
    _add_entity(db, "kael", "npc", "Kael")
    _add_entity(db, "hero", "npc", "Default Hero")  # piège du repli 'hero'
    _set_meta(db, "companion_hero_id", "kael")

    sess = _companion_session(db, save_id)
    assert sess._get_hero_id_from_metadata() == "kael"
    hero = sess._find_hero_entity(sess._get_hero_id_from_metadata())
    assert hero["entity_id"] == "kael"


def test_find_hero_entity_falls_back_to_id_then_name_then_npc(universe_db):
    """Sans métadonnée, _find_hero_entity retombe sur l'ID 'hero', puis un nom
    contenant 'hero', puis le premier NPC (mêmes replis que le worker)."""
    db, save_id = universe_db
    sess = _companion_session(db, save_id)

    # Repli 3 : premier NPC.
    _add_entity(db, "guard", "npc", "Town Guard")
    sess._entities = None
    assert sess._find_hero_entity()["entity_id"] == "guard"

    # Repli 2 : nom contenant 'hero'.
    _add_entity(db, "champ", "npc", "The Hero of Time")
    sess._entities = None
    assert sess._find_hero_entity()["entity_id"] == "champ"

    # Repli 1 : ID explicite 'hero'.
    _add_entity(db, "hero", "npc", "Anon")
    sess._entities = None
    assert sess._find_hero_entity()["entity_id"] == "hero"


def test_get_hero_decision_uses_injected_llm_and_strips(universe_db):
    """_get_hero_decision passe par le hero_llm injecté, construit le prompt avec
    nom/persona du héros, et renvoie la décision nettoyée (strip)."""
    db, save_id = universe_db
    _add_entity(db, "kael", "npc", "Kael", "A bold knight")
    hero_llm = _ScriptedLLM("  Hero draws sword.  ")
    sess = _companion_session(db, save_id, hero_llm=hero_llm)
    hero_ent = sess._find_hero_entity("kael")

    decision = sess._get_hero_decision(hero_ent, [], {})
    assert decision == "Hero draws sword."
    # Le prompt contient bien le contexte du héros.
    blob = " ".join(m["content"] for m in hero_llm.last_prompt)
    assert "Kael" in blob and "A bold knight" in blob


def test_find_hero_entity_none_when_no_entities(universe_db):
    """Sans entité héros résoluble, _find_hero_entity renvoie None (take_turn
    n'engagera donc pas de décision héros — parité avec le worker)."""
    db, save_id = universe_db
    sess = _companion_session(db, save_id)
    assert sess._find_hero_entity() is None


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


def test_load_history_with_hero_intent(universe_db):
    """_load_history correctly groups simultaneous intents when hero_intent is present."""
    db, save_id = universe_db
    events = EventSourcer(db)
    
    # Inject user input and companion intent for turn 1
    events.append_event(save_id, 1, "user_input", "player", {"text": "I attack"})
    events.append_event(save_id, 1, "hero_intent", "kael", {"text": "I heal the player"})
    events.append_event(save_id, 1, "narrative_text", "narrator", {"text": "The goblin is wounded."})

    # Add entities to DB to resolve names
    _add_entity(db, "kael", "npc", "Kael the Brave")
    _add_entity(db, "player", "player", "Aria")

    sess = Session(db, save_id, llm=_DummyLLM(), vector_memory=_DummyVectorMemory())
    history = sess._load_history()
    
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert "[SIMULTANEOUS ACTIONS FOR THIS TICK]" in history[0]["content"]
    assert "[Aria] INTENT: I attack" in history[0]["content"]
    assert "[Kael the Brave] INTENT: I heal the player" in history[0]["content"]
    assert history[1] == {"role": "assistant", "content": "The goblin is wounded."}


def test_get_hero_decision_passes_player_context_and_stats(universe_db):
    """_get_hero_decision retrieves player name/persona and builds a multi-entity stats block."""
    db, save_id = universe_db
    
    # Update saves table with player persona
    from axiom.schema import get_connection
    with get_connection(db) as conn:
        conn.execute(
            "UPDATE Saves SET player_name = 'Aria', player_persona = 'A skilled rogue' WHERE save_id = ?;",
            (save_id,)
        )
        
    _add_entity(db, "kael", "npc", "Kael", "A bold knight", {"HP": "50", "Location": "Forest"})
    _add_entity(db, "player", "player", "Aria", "", {"HP": "100", "Location": "Forest"})
    _add_entity(db, "goblin", "npc", "Grum", "A nasty goblin", {"HP": "20", "Location": "Forest"})
    # An NPC in another location, should not be included in local stats block
    _add_entity(db, "merchant", "npc", "Bob", "A merchant", {"HP": "80", "Location": "Town"})

    # Seed events so rebuild_state_cache doesn't wipe out the stats
    events = EventSourcer(db)
    events.append_event(save_id, 0, "entity_create", "player", {"entity_id": "player"})
    events.append_event(save_id, 0, "entity_create", "kael", {"entity_id": "kael"})
    events.append_event(save_id, 0, "entity_create", "goblin", {"entity_id": "goblin"})
    events.append_event(save_id, 0, "entity_create", "merchant", {"entity_id": "merchant"})
    
    events.append_event(save_id, 0, "stat_set", "player", {"entity_id": "player", "stat_key": "Location", "value": "Forest"})
    events.append_event(save_id, 0, "stat_set", "kael", {"entity_id": "kael", "stat_key": "Location", "value": "Forest"})
    events.append_event(save_id, 0, "stat_set", "goblin", {"entity_id": "goblin", "stat_key": "Location", "value": "Forest"})
    events.append_event(save_id, 0, "stat_set", "merchant", {"entity_id": "merchant", "stat_key": "Location", "value": "Town"})

    hero_llm = _ScriptedLLM("  Hero draws sword.  ")
    sess = _companion_session(db, save_id, hero_llm=hero_llm)
    hero_ent = sess._find_hero_entity("kael")

    decision = sess._get_hero_decision(hero_ent, [], {"player": "I attack Grum"})
    assert decision == "Hero draws sword."
    
    # Verify the prompt passed to the LLM
    blob = " ".join(m["content"] for m in hero_llm.last_prompt)
    assert "A skilled rogue" in blob
    assert "COMPANION TO (PLAYER): Aria" in blob
    
    # Should see local entities' stats in the prompt
    assert "Kael (id: kael)" in blob
    assert "Aria (id: player)" in blob
    assert "Grum (id: goblin)" in blob
    # Town merchant should not be there
    assert "Bob (id: merchant)" not in blob
    
    # Verify the current intents keys were mapped from entity ID to name
    assert "[Aria] INTENT: I attack Grum" in blob



def test_load_history_solo_named_player_keeps_raw_text(universe_db):
    """TICKET-047 : une action solo garde son texte brut, même si le joueur
    porte un nom personnalisé (le format groupé est réservé aux ticks à
    plusieurs intentions)."""
    db, save_id = universe_db
    events = EventSourcer(db)
    events.append_event(save_id, 1, "user_input", "aria", {"text": "I open the door"})
    events.append_event(save_id, 1, "narrative_text", "narrator", {"text": "It creaks."})
    _add_entity(db, "aria", "player", "Aria")

    sess = Session(db, save_id, llm=_DummyLLM(), vector_memory=_DummyVectorMemory())
    history = sess._load_history()

    assert history[0] == {"role": "user", "content": "I open the door"}
    assert "[SIMULTANEOUS ACTIONS FOR THIS TICK]" not in history[0]["content"]


def test_get_hero_decision_resolves_named_player_id(universe_db):
    """TICKET-043 : l'id joueur réel (dérivé du nom, pas 'player') est résolu
    depuis les intents — ses stats et sa localisation alimentent le Héros."""
    db, save_id = universe_db
    from axiom.schema import get_connection
    with get_connection(db) as conn:
        conn.execute(
            "UPDATE Saves SET player_name = 'Aria' WHERE save_id = ?;", (save_id,)
        )

    _add_entity(db, "kael", "npc", "Kael", "A bold knight", {"Location": "Forest"})
    _add_entity(db, "aria", "player", "Aria", "", {"Location": "Forest"})
    _add_entity(db, "goblin", "npc", "Grum", "A nasty goblin", {"Location": "Forest"})

    events = EventSourcer(db)
    for eid in ("aria", "kael", "goblin"):
        events.append_event(save_id, 0, "entity_create", eid, {"entity_id": eid})
        events.append_event(
            save_id, 0, "stat_set", eid,
            {"entity_id": eid, "stat_key": "Location", "value": "Forest"},
        )

    hero_llm = _ScriptedLLM("Hero draws sword.")
    sess = _companion_session(db, save_id, hero_llm=hero_llm)
    hero_ent = sess._find_hero_entity("kael")

    sess._get_hero_decision(hero_ent, [], {"aria": "I attack Grum"})
    blob = " ".join(m["content"] for m in hero_llm.last_prompt)

    # Le joueur (id réel) est dans le bloc de stats, et le PNJ co-localisé est
    # trouvé via SA localisation — les deux échouaient avec "player" en dur.
    assert "Aria (id: aria)" in blob
    assert "Grum (id: goblin)" in blob
