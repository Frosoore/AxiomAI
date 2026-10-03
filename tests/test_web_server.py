import sys
import threading
import time
import socket
import urllib.request
import urllib.parse
import json
from pathlib import Path
import pytest

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

def get_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port

@pytest.fixture(scope="module")
def web_server():
    # Find free port
    port = get_free_port()
    
    # Import handlers
    from main_web import ThreadingHTTPServer, AxiomWebHandler
    
    # Create server instance
    server = ThreadingHTTPServer(("127.0.0.1", port), AxiomWebHandler)
    
    # Run in background daemon thread
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    
    # Allow server a brief moment to boot up
    time.sleep(0.5)
    
    yield f"http://127.0.0.1:{port}"
    
    # Shutdown server
    server.shutdown()
    server.server_close()
    thread.join()


class _NarrativeStub:
    """Fake main LLM backend: always answers the same fixed prose turn."""
    last_finish_reason = "stop"

    def complete(self, messages, stream: bool = False, **kwargs):
        from axiom.backends.base import LLMResponse
        return LLMResponse("The story continues.", None, "stop")

    def stream_tokens(self, messages, **kwargs):
        yield "The story continues."

    def parse_tool_call(self, text):
        return text, None

    def is_available(self) -> bool:
        return True


class _TimeStub:
    """Fake Timekeeper backend: always reports a fixed elapsed_minutes."""
    def complete(self, messages, stream: bool = False, **kwargs):
        from axiom.backends.base import LLMResponse
        return LLMResponse('{"elapsed_minutes": 5}', None, "stop")

    def stream_tokens(self, messages, **kwargs):
        yield '{"elapsed_minutes": 5}'

    def is_available(self) -> bool:
        return True

def test_no_qt_imports():
    """Verify that main_web.py does not leak any Qt/PySide6 dependency,
    maintaining the engine's strict headless mandate.
    """
    # Verify main_web is loadable without PySide6
    # Let's inspect the file content
    main_web_path = PROJECT_ROOT / "main_web.py"
    content = main_web_path.read_text(encoding="utf-8")
    assert "PySide6" not in content
    assert "PyQt" not in content

def test_static_routes(web_server):
    """Verify the server serves static frontend assets successfully, AND that
    index.html actually references them (a servable asset nobody links to is
    dead weight: the page loaded fine but had zero interactivity -- every
    button in the app silently did nothing -- because index.html had no
    <script src="app.js"> tag at all; this exact assertion would have caught it).
    """
    # Test index.html
    req = urllib.request.urlopen(f"{web_server}/")
    assert req.status == 200
    html = req.read().decode("utf-8")
    assert "<title>Axiom AI - AI Role Playing Game</title>" in html
    assert 'href="style.css"' in html
    assert 'src="app.js"' in html

    # Test style.css
    req = urllib.request.urlopen(f"{web_server}/style.css")
    assert req.status == 200
    css = req.read().decode("utf-8")
    assert "Catppuccin Mocha" in css

    # Test app.js
    req = urllib.request.urlopen(f"{web_server}/app.js")
    assert req.status == 200
    js = req.read().decode("utf-8")
    assert "Axiom AI - Single Page Application Core" in js

def test_api_settings(web_server):
    """Test getting and saving LLM/general settings config."""
    # Get settings
    req = urllib.request.urlopen(f"{web_server}/api/settings")
    assert req.status == 200
    data = json.loads(req.read().decode("utf-8"))
    assert "llm_backend" in data

    # Post settings
    post_data = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        f"{web_server}/api/settings",
        data=post_data,
        headers={"Content-Type": "application/json"}
    )
    res = urllib.request.urlopen(req)
    assert res.status == 200
    res_data = json.loads(res.read().decode("utf-8"))
    assert res_data.get("status") == "success"

def test_api_translations(web_server):
    """Test retrieving active language i18n translations dictionary."""
    req = urllib.request.urlopen(f"{web_server}/api/translations")
    assert req.status == 200
    data = json.loads(req.read().decode("utf-8"))
    assert "app_title" in data
    assert "ready" in data

def test_api_universes(web_server):
    """Test scanning and retrieving list of installed universes."""
    req = urllib.request.urlopen(f"{web_server}/api/universes")
    assert req.status == 200
    data = json.loads(req.read().decode("utf-8"))
    assert isinstance(data, list)

def test_api_saves_export_and_edit(web_server):
    """Verify that export and edit save state endpoints are functional."""
    from axiom.db_helpers import provision_blank_universe, create_new_save
    from axiom.schema import create_universe_db
    import tempfile
    
    # Create a temporary universe DB
    tmp_dir = PROJECT_ROOT / "scratch"
    tmp_dir.mkdir(exist_ok=True)
    db_file = tmp_dir / "test_web_saves.db"
    if db_file.exists():
        db_file.unlink()
        
    try:
        create_universe_db(str(db_file))
        provision_blank_universe(str(db_file), "Web Test Universe")
        save_id = create_new_save(str(db_file), "Alice", "Normal", "A clever test spy")
        
        # 1. Export Save State TOML
        url_enc = urllib.parse.quote(str(db_file))
        req = urllib.request.urlopen(f"{web_server}/api/saves/export?universe={url_enc}&save_id={save_id}")
        assert req.status == 200
        export_data = json.loads(req.read().decode("utf-8"))
        assert "toml" in export_data
        original_toml = export_data["toml"]
        assert "Alice" in original_toml
        assert "Normal" in original_toml
        
        # 2. Modify TOML (add player stat)
        edited_toml = original_toml + "\n[state.player]\nIntelligence = \"18\"\n"
        
        # 3. Apply Save State Edits via POST
        post_payload = {
            "universe_path": str(db_file),
            "save_id": save_id,
            "original_toml": original_toml,
            "edited_toml": edited_toml
        }
        req_post = urllib.request.Request(
            f"{web_server}/api/saves/edit",
            data=json.dumps(post_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        res_post = urllib.request.urlopen(req_post)
        assert res_post.status == 200
        res_data = json.loads(res_post.read().decode("utf-8"))
        assert res_data.get("status") == "success"
        
        # 4. Export again to verify the Intelligence stat is present
        req_verify = urllib.request.urlopen(f"{web_server}/api/saves/export?universe={url_enc}&save_id={save_id}")
        verify_data = json.loads(req_verify.read().decode("utf-8"))
        assert 'Intelligence = "18"' in verify_data["toml"]

    finally:
        if db_file.exists():
            db_file.unlink()


def _post_json(url: str, payload: dict):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        res = urllib.request.urlopen(req)
        return res.status, json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_universes_delete_removes_flat_db(web_server):
    """POST /api/universes/delete removes a flat-db universe from disk.

    Regression test: web/app.js's Hub "Delete" button called this route while
    main_web.py defined no such handler (unconditional 404).
    """
    from axiom.db_helpers import provision_blank_universe
    from axiom.schema import create_universe_db

    tmp_dir = PROJECT_ROOT / "scratch"
    tmp_dir.mkdir(exist_ok=True)
    db_file = tmp_dir / "test_web_delete_universe.db"
    if db_file.exists():
        db_file.unlink()

    create_universe_db(str(db_file))
    provision_blank_universe(str(db_file), "Deletable Universe")
    assert db_file.exists()

    status, data = _post_json(f"{web_server}/api/universes/delete", {"path": str(db_file)})
    assert status == 200
    assert data.get("status") == "success"
    assert not db_file.exists()


def test_diagnostic_endpoint_returns_report(web_server):
    """GET /api/diagnostic wires to tools.diagnostic and returns a text report.

    Regression test: the Diagnostic modal's "Run Diagnostics" button called
    this route while main_web.py defined no such handler (unconditional 404).
    `tests=false` keeps this fast (skips the pytest-in-pytest batch).
    """
    req = urllib.request.urlopen(f"{web_server}/api/diagnostic?tests=false")
    assert req.status == 200
    data = json.loads(req.read().decode("utf-8"))
    assert "report" in data
    assert isinstance(data["report"], str)
    assert len(data["report"]) > 0


def test_session_lifecycle_start_turn_rewind(web_server):
    """Full gameplay loop through the HTTP API: create save -> start -> turn -> rewind.

    Regression test: /api/session/start|turn|rewind formatted in-game time via
    a nonexistent `Session._time_system` attribute (AttributeError on every
    call, caught and turned into a JSON {"error": ...} response) -- this test
    would have failed on `res.status == 200` before the fix. It also checks
    that the opening narrative (first_message, with @tag substitution from
    setup answers) is actually written at save creation, which it previously
    was not.
    """
    from unittest.mock import patch
    from axiom.db_helpers import provision_blank_universe
    from axiom.schema import create_universe_db, get_connection

    tmp_dir = PROJECT_ROOT / "scratch"
    tmp_dir.mkdir(exist_ok=True)
    db_file = tmp_dir / "test_web_session_lifecycle.db"
    if db_file.exists():
        db_file.unlink()

    try:
        create_universe_db(str(db_file))
        provision_blank_universe(str(db_file), "Lifecycle Universe")
        with get_connection(str(db_file)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO Universe_Meta (key, value) VALUES "
                "('first_message', 'Hello @traveler, welcome.---VARIANT---Another greeting.');"
            )
            conn.commit()

        # 1. Create save with a setup answer -> opening narrative should have
        #    "@traveler" replaced by "Explorer".
        status, data = _post_json(f"{web_server}/api/saves/create", {
            "universe_path": str(db_file),
            "player_name": "Aria",
            "player_persona": "",
            "difficulty": "Normal",
            "setup_answers": {"traveler": "Explorer"},
        })
        assert status == 200, data
        save_id = data["save_id"]

        narrative_stub = _NarrativeStub()
        time_stub = _TimeStub()

        # build_llm_from_config feeds both main_web.py's own resolution AND
        # Session._resolve_time_llm's internal call -- short-circuit the
        # latter directly so the Timekeeper never makes a real network call.
        with patch("axiom.config.build_llm_from_config", return_value=narrative_stub), \
             patch("axiom.session.resolve_llm_backend", return_value=narrative_stub), \
             patch("axiom.session.Session._resolve_time_llm", return_value=time_stub):

            # 2. Start session -> opening narrative must be present in history.
            #    History is a turn_id-tagged raw event list (mirrors
            #    workers/db_tasks.py::LoadSessionHistoryTask), not role/content
            #    pairs, so the client can drive edit/regenerate/variant-nav.
            status, data = _post_json(f"{web_server}/api/session/start", {
                "universe_path": str(db_file),
                "save_id": save_id,
                "difficulty": "Normal",
            })
            assert status == 200, data
            assert data["turn_id"] == 0
            assert len(data["history"]) == 1
            opening = data["history"][0]
            assert opening["turn_id"] == 0 and opening["event_type"] == "narrative_text"
            assert opening["payload"]["variants"][opening["payload"]["active"]] == "Hello Explorer, welcome."
            assert data["time_formatted"]  # would previously KeyError/crash upstream

            # 3. Play a turn -> history now also carries the user_input + new narrative_text.
            status, data = _post_json(f"{web_server}/api/session/turn", {
                "player_input": "I look around.",
            })
            assert status == 200, data
            assert data["turn_id"] == 1
            assert data["narrative_text"]
            assert data["time_formatted"]
            assert len(data["history"]) == 3
            assert [e["event_type"] for e in data["history"]] == [
                "narrative_text", "user_input", "narrative_text"
            ]
            assert data["history"][1]["turn_id"] == 1
            assert data["history"][1]["payload"]["text"] == "I look around."

            # 4. Rewind back to turn 0 -> only the opening narrative remains.
            status, data = _post_json(f"{web_server}/api/session/rewind", {
                "target_turn_id": 0,
            })
            assert status == 200, data
            assert data["turn_id"] == 0
            assert len(data["history"]) == 1
    finally:
        if db_file.exists():
            db_file.unlink()


def test_saves_fork_preserves_modifiers_and_fired_events(web_server):
    """POST /api/saves/fork delegates to axiom.saves.fork_save and therefore
    carries over Active_Modifiers and Fired_Scheduled_Events (fired_turn_id
    included), unlike the previous hand-rolled copy which only duplicated
    Saves + Event_Log (regressing TICKET-034/075/086).
    """
    from axiom.db_helpers import provision_blank_universe, create_new_save
    from axiom.schema import create_universe_db, get_connection
    from axiom.events import EventSourcer

    tmp_dir = PROJECT_ROOT / "scratch"
    tmp_dir.mkdir(exist_ok=True)
    db_file = tmp_dir / "test_web_saves_fork.db"
    if db_file.exists():
        db_file.unlink()

    try:
        create_universe_db(str(db_file))
        provision_blank_universe(str(db_file), "Fork Universe")
        save_id = create_new_save(str(db_file), "Aria", "Normal")

        events = EventSourcer(str(db_file))
        events.append_event(save_id, 0, "entity_create", "player1",
                             {"entity_id": "player1", "entity_type": "player", "name": "Aria"})

        with get_connection(str(db_file)) as conn:
            conn.execute(
                "INSERT INTO Entities (entity_id, entity_type, name, is_active) "
                "VALUES ('player1', 'player', 'Aria', 1);"
            )
            conn.execute(
                "INSERT INTO Scheduled_Events (event_id, trigger_minute, title, description) "
                "VALUES ('ev1', 60, 'Bell tolls', 'The town bell rings.');"
            )
            conn.execute(
                "INSERT INTO Fired_Scheduled_Events (save_id, event_id, fired_turn_id) "
                "VALUES (?, 'ev1', 0);", (save_id,)
            )
            conn.execute(
                "INSERT INTO Active_Modifiers (modifier_id, save_id, entity_id, stat_key, delta, minutes_remaining) "
                "VALUES ('mod1', ?, 'player1', 'HP', -5, 30);", (save_id,)
            )
            conn.commit()

        status, data = _post_json(f"{web_server}/api/saves/fork", {
            "universe_path": str(db_file),
            "save_id": save_id,
            "turn_id": 0,
            "name": "Timeline B",
        })
        assert status == 200, data
        new_save_id = data["new_save_id"]
        assert new_save_id != save_id

        with get_connection(str(db_file)) as conn:
            mods = conn.execute(
                "SELECT entity_id, stat_key, delta, minutes_remaining FROM Active_Modifiers WHERE save_id=?;",
                (new_save_id,)
            ).fetchall()
            fired = conn.execute(
                "SELECT event_id, fired_turn_id FROM Fired_Scheduled_Events WHERE save_id=?;",
                (new_save_id,)
            ).fetchall()

        assert len(mods) == 1
        assert mods[0]["entity_id"] == "player1" and mods[0]["stat_key"] == "HP"
        assert len(fired) == 1
        assert fired[0]["event_id"] == "ev1" and fired[0]["fired_turn_id"] == 0
    finally:
        if db_file.exists():
            db_file.unlink()


def test_session_inventory_endpoint(web_server):
    """GET /api/session/inventory mirrors workers/db_tasks.py::LoadInventoryTask:
    all active entities' items, joined against Item_Definitions (name/rarity).
    """
    from unittest.mock import patch
    from axiom.db_helpers import provision_blank_universe, create_new_save
    from axiom.schema import create_universe_db, get_connection

    tmp_dir = PROJECT_ROOT / "scratch"
    tmp_dir.mkdir(exist_ok=True)
    db_file = tmp_dir / "test_web_inventory.db"
    if db_file.exists():
        db_file.unlink()

    try:
        create_universe_db(str(db_file))
        provision_blank_universe(str(db_file), "Inventory Universe")
        save_id = create_new_save(str(db_file), "Aria", "Normal")

        with get_connection(str(db_file)) as conn:
            conn.execute(
                "INSERT INTO Entities (entity_id, entity_type, name, is_active) "
                "VALUES ('player', 'player', 'Aria', 1);"
            )
            conn.execute(
                "INSERT INTO Item_Definitions (item_id, name, description, category, weight, rarity) "
                "VALUES ('sword1', 'Rusty Sword', 'An old blade.', 'weapon', 2.5, 'rare');"
            )
            conn.execute(
                "INSERT INTO Items_Inventory (save_id, entity_id, item_id, quantity) "
                "VALUES (?, 'player', 'sword1', 1);", (save_id,)
            )
            conn.commit()

        with patch("axiom.config.build_llm_from_config", return_value=_NarrativeStub()), \
             patch("axiom.session.resolve_llm_backend", return_value=_NarrativeStub()), \
             patch("axiom.session.Session._resolve_time_llm", return_value=_TimeStub()):
            status, data = _post_json(f"{web_server}/api/session/start", {
                "universe_path": str(db_file),
                "save_id": save_id,
                "difficulty": "Normal",
            })
            assert status == 200, data

            req = urllib.request.urlopen(f"{web_server}/api/session/inventory")
            assert req.status == 200
            inv = json.loads(req.read().decode("utf-8"))
            if "tree" in inv:
                roots = [r for r in inv["tree"] if r.get("holder_id") == "player"]
                assert roots, inv
                items = roots[0].get("contents") or []
                assert len(items) == 1
                assert items[0]["name"] == "Rusty Sword"
                assert items[0]["rarity"] == "rare"
                assert items[0]["quantity"] == 1
            else:
                assert "player" in inv
                assert len(inv["player"]) == 1
                assert inv["player"][0]["name"] == "Rusty Sword"
    finally:
        if db_file.exists():
            db_file.unlink()


def _start_lifecycle_session(web_server, db_file, universe_name):
    """Shared setup for the edit/regenerate/variant tests: a fresh universe,
    one save, and a live ACTIVE_SESSION (LLM/Timekeeper mocked). Returns save_id.
    Caller is responsible for entering the same `patch(...)` context for any
    further turn/regenerate/edit calls (mocks are only active inside the `with`).
    """
    from axiom.db_helpers import provision_blank_universe
    from axiom.schema import create_universe_db

    create_universe_db(str(db_file))
    provision_blank_universe(str(db_file), universe_name)

    status, data = _post_json(f"{web_server}/api/saves/create", {
        "universe_path": str(db_file),
        "player_name": "Aria",
        "player_persona": "",
        "difficulty": "Normal",
        "setup_answers": {},
    })
    assert status == 200, data
    save_id = data["save_id"]

    status, data = _post_json(f"{web_server}/api/session/start", {
        "universe_path": str(db_file),
        "save_id": save_id,
        "difficulty": "Normal",
    })
    assert status == 200, data
    return save_id


def test_session_edit_message_ai_patches_active_variant(web_server):
    """POST /api/session/edit-message on a narrative_text event rewrites the
    active variant's text in place (no rewind, no new turn), mirroring
    ui/tabletop_view.py::_on_edit_message_requested's AI-message branch.
    """
    from unittest.mock import patch

    tmp_dir = PROJECT_ROOT / "scratch"
    tmp_dir.mkdir(exist_ok=True)
    db_file = tmp_dir / "test_web_edit_ai_message.db"
    if db_file.exists():
        db_file.unlink()

    try:
        with patch("axiom.config.build_llm_from_config", return_value=_NarrativeStub()), \
             patch("axiom.session.resolve_llm_backend", return_value=_NarrativeStub()), \
             patch("axiom.session.Session._resolve_time_llm", return_value=_TimeStub()):
            save_id = _start_lifecycle_session(web_server, db_file, "Edit AI Universe")

            status, data = _post_json(f"{web_server}/api/session/turn", {"player_input": "I look around."})
            assert status == 200, data
            assert data["turn_id"] == 1

            status, data = _post_json(f"{web_server}/api/session/edit-message", {
                "event_type": "narrative_text",
                "turn_id": 1,
                "new_text": "A hand-edited narrative.",
            })
            assert status == 200, data
            assert data["turn_id"] == 1  # no new turn created
            turn1_narrative = [e for e in data["history"] if e["turn_id"] == 1 and e["event_type"] == "narrative_text"][0]
            active = turn1_narrative["payload"]["active"]
            assert turn1_narrative["payload"]["variants"][active] == "A hand-edited narrative."
    finally:
        if db_file.exists():
            db_file.unlink()


def test_session_edit_message_user_input_rewinds_and_resubmits(web_server):
    """POST /api/session/edit-message on a user_input event rewinds to just
    before that turn and resubmits the corrected text as a new turn.
    """
    from unittest.mock import patch

    tmp_dir = PROJECT_ROOT / "scratch"
    tmp_dir.mkdir(exist_ok=True)
    db_file = tmp_dir / "test_web_edit_user_message.db"
    if db_file.exists():
        db_file.unlink()

    try:
        with patch("axiom.config.build_llm_from_config", return_value=_NarrativeStub()), \
             patch("axiom.session.resolve_llm_backend", return_value=_NarrativeStub()), \
             patch("axiom.session.Session._resolve_time_llm", return_value=_TimeStub()):
            save_id = _start_lifecycle_session(web_server, db_file, "Edit User Universe")

            status, data = _post_json(f"{web_server}/api/session/turn", {"player_input": "I look around."})
            assert status == 200, data

            status, data = _post_json(f"{web_server}/api/session/edit-message", {
                "event_type": "user_input",
                "turn_id": 1,
                "new_text": "I open the door instead.",
            })
            assert status == 200, data
            assert data["turn_id"] == 1  # rewound to 0, then resubmitted -> back to 1
            turn1_input = [e for e in data["history"] if e["turn_id"] == 1 and e["event_type"] == "user_input"][0]
            assert turn1_input["payload"]["text"] == "I open the door instead."
    finally:
        if db_file.exists():
            db_file.unlink()


def test_session_regenerate_appends_variant_and_switches_active(web_server):
    """POST /api/session/regenerate appends a new variant to the turn's
    narrative_text payload and makes it active, without touching stats/rules.
    """
    from unittest.mock import patch

    tmp_dir = PROJECT_ROOT / "scratch"
    tmp_dir.mkdir(exist_ok=True)
    db_file = tmp_dir / "test_web_regenerate.db"
    if db_file.exists():
        db_file.unlink()

    try:
        with patch("axiom.config.build_llm_from_config", return_value=_NarrativeStub()), \
             patch("axiom.session.resolve_llm_backend", return_value=_NarrativeStub()), \
             patch("axiom.session.Session._resolve_time_llm", return_value=_TimeStub()):
            save_id = _start_lifecycle_session(web_server, db_file, "Regenerate Universe")

            status, data = _post_json(f"{web_server}/api/session/turn", {"player_input": "I look around."})
            assert status == 200, data

            status, data = _post_json(f"{web_server}/api/session/regenerate", {"turn_id": 1})
            assert status == 200, data
            turn1_narrative = [e for e in data["history"] if e["turn_id"] == 1 and e["event_type"] == "narrative_text"][0]
            payload = turn1_narrative["payload"]
            assert len(payload["variants"]) == 2
            assert payload["active"] == 1
    finally:
        if db_file.exists():
            db_file.unlink()


def test_session_variant_switch(web_server):
    """POST /api/session/variant flips the active index of an existing
    multi-variant narrative_text event without generating anything new.
    """
    from unittest.mock import patch

    tmp_dir = PROJECT_ROOT / "scratch"
    tmp_dir.mkdir(exist_ok=True)
    db_file = tmp_dir / "test_web_variant_switch.db"
    if db_file.exists():
        db_file.unlink()

    try:
        with patch("axiom.config.build_llm_from_config", return_value=_NarrativeStub()), \
             patch("axiom.session.resolve_llm_backend", return_value=_NarrativeStub()), \
             patch("axiom.session.Session._resolve_time_llm", return_value=_TimeStub()):
            save_id = _start_lifecycle_session(web_server, db_file, "Variant Switch Universe")

            status, data = _post_json(f"{web_server}/api/session/turn", {"player_input": "I look around."})
            assert status == 200, data
            status, data = _post_json(f"{web_server}/api/session/regenerate", {"turn_id": 1})
            assert status == 200, data  # now 2 variants, active=1

            status, data = _post_json(f"{web_server}/api/session/variant", {"turn_id": 1, "variant_index": 0})
            assert status == 200, data
            turn1_narrative = [e for e in data["history"] if e["turn_id"] == 1 and e["event_type"] == "narrative_text"][0]
            assert turn1_narrative["payload"]["active"] == 0
    finally:
        if db_file.exists():
            db_file.unlink()


def test_personas_crud(web_server, tmp_path, monkeypatch):
    """GET/POST /api/personas round-trips the Global_Personas table (mirrors
    ui/widgets/persona_editor.py + workers/db_tasks.py::{Load,Save}GlobalPersonasTask).

    Uses AXIOM_CONFIG_DIR so this never touches the real machine-global
    ~/.config/AxiomAI/global.db (main_web.py resolves it via the override-aware
    axiom.config._resolve_global_db_file(), not the frozen GLOBAL_DB_FILE constant).
    """
    monkeypatch.setenv("AXIOM_CONFIG_DIR", str(tmp_path / "axiom_config"))

    req = urllib.request.urlopen(f"{web_server}/api/personas")
    assert req.status == 200
    assert json.loads(req.read().decode("utf-8")) == []

    personas = [
        {"persona_id": "p1", "name": "Reformed Thief", "description": "A clockwork cat burglar."},
        {"persona_id": "p2", "name": "Exiled Noble", "description": "Lost their title, kept their manners."},
    ]
    status, data = _post_json(f"{web_server}/api/personas", {"personas": personas})
    assert status == 200, data
    assert data.get("status") == "success"

    req = urllib.request.urlopen(f"{web_server}/api/personas")
    assert req.status == 200
    saved = json.loads(req.read().decode("utf-8"))
    assert len(saved) == 2
    assert {p["name"] for p in saved} == {"Reformed Thief", "Exiled Noble"}

    # Replacing with a shorter list drops the removed entry (matches SaveGlobalPersonasTask's
    # DELETE-then-reinsert semantics).
    status, data = _post_json(f"{web_server}/api/personas", {"personas": [personas[0]]})
    assert status == 200, data
    req = urllib.request.urlopen(f"{web_server}/api/personas")
    saved = json.loads(req.read().decode("utf-8"))
    assert len(saved) == 1
    assert saved[0]["name"] == "Reformed Thief"


def test_audio_track_no_bundled_assets_returns_null(web_server):
    """GET /api/audio/track gracefully returns file=null when no ambiance
    tracks are bundled for the tag (the app ships with none by default,
    mirrors ui/ambiance_manager.py::_pick_random_file's None-returning path).
    """
    req = urllib.request.urlopen(f"{web_server}/api/audio/track?tag=combat")
    assert req.status == 200
    data = json.loads(req.read().decode("utf-8"))
    assert data["tag"] == "combat"
    assert data["file"] is None


def test_audio_track_picks_and_serves_bundled_file(web_server, tmp_path, monkeypatch):
    """When ambiance tracks ARE present under assets/audio/<tag>/, the endpoint
    picks one and it's servable from /audio/<tag>/<file>.
    """
    import main_web

    audio_root = tmp_path / "assets" / "audio"
    (audio_root / "combat").mkdir(parents=True)
    track_file = audio_root / "combat" / "battle.mp3"
    track_file.write_bytes(b"fake-mp3-bytes")

    monkeypatch.setattr(main_web, "AUDIO_ASSETS_DIR", audio_root)

    req = urllib.request.urlopen(f"{web_server}/api/audio/track?tag=combat")
    data = json.loads(req.read().decode("utf-8"))
    assert data["file"] == "battle.mp3"

    req = urllib.request.urlopen(f"{web_server}/audio/combat/battle.mp3")
    assert req.status == 200
    assert req.read() == b"fake-mp3-bytes"
    assert req.headers.get("Content-Type") == "audio/mpeg"


def test_session_turn_includes_game_state_tag(web_server):
    """POST /api/session/turn surfaces ArbitratorResult.game_state_tag so the
    client can drive ambiance crossfading (mirrors
    ui/tabletop_view.py:754-755's update_audio_ambiance(game_state_tag) call).
    """
    from unittest.mock import patch

    tmp_dir = PROJECT_ROOT / "scratch"
    tmp_dir.mkdir(exist_ok=True)
    db_file = tmp_dir / "test_web_game_state_tag.db"
    if db_file.exists():
        db_file.unlink()

    try:
        with patch("axiom.config.build_llm_from_config", return_value=_NarrativeStub()), \
             patch("axiom.session.resolve_llm_backend", return_value=_NarrativeStub()), \
             patch("axiom.session.Session._resolve_time_llm", return_value=_TimeStub()):
            save_id = _start_lifecycle_session(web_server, db_file, "Ambiance Universe")

            status, data = _post_json(f"{web_server}/api/session/turn", {"player_input": "I look around."})
            assert status == 200, data
            assert data["game_state_tag"] == "exploration"  # _NarrativeStub returns no tool_call -> default
    finally:
        if db_file.exists():
            db_file.unlink()


def test_saves_delete_removes_only_the_targeted_save(web_server):
    """POST /api/saves/delete removes one save and leaves its universe/siblings
    intact.

    Regression test: the handler used to call
    axiom.checkpoint.CheckpointManager.delete_save(save_id) -- missing that
    method's required `universe_dir` argument (TypeError on every call) and,
    worse, the wrong function entirely (it's Hardcore-only and wipes the whole
    universe directory). Fixed to axiom.savestore.delete_save, the same one
    the Qt Hub's Delete button uses (workers/db_tasks.py::DeleteSaveTask).
    """
    from axiom.db_helpers import provision_blank_universe, create_new_save
    from axiom.schema import create_universe_db

    tmp_dir = PROJECT_ROOT / "scratch"
    tmp_dir.mkdir(exist_ok=True)
    db_file = tmp_dir / "test_web_saves_delete.db"
    if db_file.exists():
        db_file.unlink()

    try:
        create_universe_db(str(db_file))
        provision_blank_universe(str(db_file), "Delete Save Universe")
        keep_id = create_new_save(str(db_file), "Keep Me", "Normal")
        gone_id = create_new_save(str(db_file), "Delete Me", "Normal")

        status, data = _post_json(f"{web_server}/api/saves/delete", {
            "universe_path": str(db_file),
            "save_id": gone_id,
        })
        assert status == 200, data
        assert data.get("status") == "success"

        # The universe .db itself must still exist (only one save was deleted).
        assert db_file.exists()
        from axiom.savestore import list_saves
        remaining = list_saves(str(db_file))
        assert {s["save_id"] for s in remaining} == {keep_id}
    finally:
        if db_file.exists():
            db_file.unlink()


def test_is_player_death_triggered():
    """Unit test for the Player_Death rule-scan, mirrors
    ui/tabletop_hardcore.py::HardcoreMixin._check_for_player_death's detection
    (case-insensitive match on a trigger_event action's 'event' field).
    """
    from main_web import is_player_death_triggered

    class _FakeResult:
        def __init__(self, triggered_rules):
            self.triggered_rules = triggered_rules

    assert is_player_death_triggered(_FakeResult([])) is False
    assert is_player_death_triggered(_FakeResult([
        {"type": "stat_change", "stat": "HP", "delta": -10},
    ])) is False
    assert is_player_death_triggered(_FakeResult([
        {"type": "trigger_event", "event": "Player_Death"},
    ])) is True
    assert is_player_death_triggered(_FakeResult([
        {"type": "trigger_event", "event": "player_death"},  # case-insensitive
    ])) is True
    assert is_player_death_triggered(_FakeResult([
        {"type": "trigger_event", "event": "World_News_Update"},
    ])) is False


def test_hardcore_delete_removes_save_and_blocks_non_hardcore(web_server):
    """POST /api/session/hardcore-delete performs the irrevocable deletion for
    a Hardcore-mode session, and refuses on a Normal-mode one.
    """
    from unittest.mock import patch
    from axiom.db_helpers import provision_blank_universe
    from axiom.schema import create_universe_db

    tmp_dir = PROJECT_ROOT / "scratch"
    tmp_dir.mkdir(exist_ok=True)
    db_file = tmp_dir / "test_web_hardcore_delete.db"
    if db_file.exists():
        db_file.unlink()

    try:
        with patch("axiom.config.build_llm_from_config", return_value=_NarrativeStub()), \
             patch("axiom.session.resolve_llm_backend", return_value=_NarrativeStub()), \
             patch("axiom.session.Session._resolve_time_llm", return_value=_TimeStub()):
            create_universe_db(str(db_file))
            provision_blank_universe(str(db_file), "Hardcore Universe")

            # Normal-mode session: hardcore-delete must be refused, save survives.
            status, data = _post_json(f"{web_server}/api/saves/create", {
                "universe_path": str(db_file), "player_name": "Aria",
                "player_persona": "", "difficulty": "Normal", "setup_answers": {},
            })
            normal_save_id = data["save_id"]
            status, data = _post_json(f"{web_server}/api/session/start", {
                "universe_path": str(db_file), "save_id": normal_save_id, "difficulty": "Normal",
            })
            assert status == 200, data
            status, data = _post_json(f"{web_server}/api/session/hardcore-delete", {})
            assert status == 400, data
            from axiom.savestore import list_saves
            assert any(s["save_id"] == normal_save_id for s in list_saves(str(db_file)))

            # Hardcore-mode session: hardcore-delete wipes the save.
            status, data = _post_json(f"{web_server}/api/saves/create", {
                "universe_path": str(db_file), "player_name": "Rex",
                "player_persona": "", "difficulty": "Hardcore", "setup_answers": {},
            })
            hardcore_save_id = data["save_id"]
            status, data = _post_json(f"{web_server}/api/session/start", {
                "universe_path": str(db_file), "save_id": hardcore_save_id, "difficulty": "Hardcore",
            })
            assert status == 200, data
            status, data = _post_json(f"{web_server}/api/session/hardcore-delete", {})
            assert status == 200, data
            assert data.get("status") == "success"
            assert not any(s["save_id"] == hardcore_save_id for s in list_saves(str(db_file)))

            # The session is gone: further turns must fail cleanly (no dangling ACTIVE_SESSION).
            status, data = _post_json(f"{web_server}/api/session/turn", {"player_input": "hello"})
            assert status == 400, data
    finally:
        if db_file.exists():
            db_file.unlink()


def test_session_multiplayer_turn_intents(web_server):
    """POST /api/session/turn with "intents" payload resolves a multiplayer turn."""
    from unittest.mock import patch
    from axiom.db_helpers import provision_blank_universe
    from axiom.schema import create_universe_db

    tmp_dir = PROJECT_ROOT / "scratch"
    tmp_dir.mkdir(exist_ok=True)
    db_file = tmp_dir / "test_web_multiplayer.db"
    if db_file.exists():
        db_file.unlink()

    try:
        with patch("axiom.config.build_llm_from_config", return_value=_NarrativeStub()), \
             patch("axiom.session.resolve_llm_backend", return_value=_NarrativeStub()), \
             patch("axiom.session.Session._resolve_time_llm", return_value=_TimeStub()):
            create_universe_db(str(db_file))
            provision_blank_universe(str(db_file), "Multiplayer Universe")

            # Create game save in Multiplayer mode
            status, data = _post_json(f"{web_server}/api/saves/create", {
                "universe_path": str(db_file),
                "player_name": "Multiplayer Group",
                "player_persona": "",
                "difficulty": "Multiplayer",
                "setup_answers": {},
            })
            save_id = data["save_id"]

            # Start multiplayer session
            status, data = _post_json(f"{web_server}/api/session/start", {
                "universe_path": str(db_file),
                "save_id": save_id,
                "difficulty": "Multiplayer",
            })
            assert status == 200
            assert "players" in data
            
            # Submit turn with multiple player intents
            intents = {
                "player_1": "I look around.",
                "player_2": "I check the door."
            }
            status, data = _post_json(f"{web_server}/api/session/turn", {
                "intents": intents
            })
            assert status == 200
            # History must contain both user_input events
            history = data["history"]
            user_input_events = [h for h in history if h["event_type"] == "user_input"]
            assert len(user_input_events) >= 2
            p1_event = next(e for e in user_input_events if e["payload"].get("text") == "I look around.")
            p2_event = next(e for e in user_input_events if e["payload"].get("text") == "I check the door.")
            assert p1_event["turn_id"] == data["turn_id"]
            assert p2_event["turn_id"] == data["turn_id"]
    finally:
        if db_file.exists():
            db_file.unlink()


def test_creator_data_map_connections_round_trip(web_server):
    """GET/POST /api/creator/data|save read/write the Map tab's connections
    against the real table name.

    Regression test: the handler queried/wrote a table literally called
    "Connections", which has never existed (the schema calls it
    Location_Connections) -- GET /api/creator/data raised
    "no such table: Connections" on ANY universe with map data, which 500'd
    the *entire* response (not just the Map tab), so every Creator Studio tab
    rendered empty with no error shown (openCreatorStudio didn't check
    res.ok either, compounding the silent failure -- also fixed).
    """
    from axiom.db_helpers import provision_blank_universe
    from axiom.schema import create_universe_db, get_connection

    tmp_dir = PROJECT_ROOT / "scratch"
    tmp_dir.mkdir(exist_ok=True)
    db_file = tmp_dir / "test_web_creator_map.db"
    if db_file.exists():
        db_file.unlink()

    try:
        create_universe_db(str(db_file))
        provision_blank_universe(str(db_file), "Map Universe")
        with get_connection(str(db_file)) as conn:
            conn.execute(
                "INSERT INTO Locations (location_id, name, scale, parent_id, description, x, y) "
                "VALUES ('town', 'Town', 'city', NULL, '', 0, 0);"
            )
            conn.execute(
                "INSERT INTO Locations (location_id, name, scale, parent_id, description, x, y) "
                "VALUES ('forest', 'Forest', 'zone', NULL, '', 1, 1);"
            )
            conn.execute(
                "INSERT INTO Location_Connections (source_id, target_id, distance_km) "
                "VALUES ('town', 'forest', 5);"
            )
            conn.commit()

        url_enc = urllib.parse.quote(str(db_file))
        req = urllib.request.urlopen(f"{web_server}/api/creator/data?universe={url_enc}")
        assert req.status == 200
        data = json.loads(req.read().decode("utf-8"))
        assert len(data["locations"]) == 2
        assert len(data["connections"]) == 1
        assert data["connections"][0] == {"source_id": "town", "target_id": "forest", "distance_km": 5}

        # Round-trip through the Studio "Save" path: add a second connection.
        data["connections"].append({"source_id": "forest", "target_id": "town", "distance_km": 5})
        status, save_result = _post_json(f"{web_server}/api/creator/save?universe={url_enc}", data)
        assert status == 200, save_result

        req2 = urllib.request.urlopen(f"{web_server}/api/creator/data?universe={url_enc}")
        data2 = json.loads(req2.read().decode("utf-8"))
        assert len(data2["connections"]) == 2
    finally:
        if db_file.exists():
            db_file.unlink()


def test_settings_update_reloads_active_session_llm(web_server):
    """Test that modifying settings dynamically updates the active session's LLM backend."""
    from unittest.mock import patch
    from axiom.db_helpers import provision_blank_universe
    from axiom.schema import create_universe_db

    tmp_dir = PROJECT_ROOT / "scratch"
    tmp_dir.mkdir(exist_ok=True)
    db_file = tmp_dir / "test_web_settings_llm.db"
    if db_file.exists():
        db_file.unlink()

    try:
        with patch("axiom.config.build_llm_from_config", return_value=_NarrativeStub()), \
             patch("axiom.session.resolve_llm_backend", return_value=_NarrativeStub()), \
             patch("axiom.session.Session._resolve_time_llm", return_value=_TimeStub()):
            create_universe_db(str(db_file))
            provision_blank_universe(str(db_file), "Settings LLM Universe")

            # Create & start session
            status, data = _post_json(f"{web_server}/api/saves/create", {
                "universe_path": str(db_file), "player_name": "Aria",
                "player_persona": "", "difficulty": "Normal", "setup_answers": {},
            })
            save_id = data["save_id"]
            status, data = _post_json(f"{web_server}/api/session/start", {
                "universe_path": str(db_file), "save_id": save_id, "difficulty": "Normal",
            })
            assert status == 200

            # Re-fetch settings
            req = urllib.request.urlopen(f"{web_server}/api/settings")
            current_settings = json.loads(req.read().decode("utf-8"))

            # Update settings via POST
            current_settings["llm_backend"] = "Universal"
            status, data = _post_json(f"{web_server}/api/settings", current_settings)
            assert status == 200
            
            # Verify that the server rebuilt the LLM backend on the active session
            import main_web
            assert main_web.ACTIVE_SESSION is not None
            assert main_web.ACTIVE_SESSION._llm is not None
    finally:
        if db_file.exists():
            db_file.unlink()


def test_session_lore_search(web_server):
    """GET /api/session/lore queries the MiniDico pipeline, returning LLM-powered answers."""
    from unittest.mock import patch
    from axiom.db_helpers import provision_blank_universe
    from axiom.schema import create_universe_db

    tmp_dir = PROJECT_ROOT / "scratch"
    tmp_dir.mkdir(exist_ok=True)
    db_file = tmp_dir / "test_web_lore.db"
    if db_file.exists():
        db_file.unlink()

    try:
        with patch("axiom.config.build_llm_from_config", return_value=_NarrativeStub()), \
             patch("axiom.session.resolve_llm_backend", return_value=_NarrativeStub()), \
             patch("axiom.session.Session._resolve_time_llm", return_value=_TimeStub()):
            create_universe_db(str(db_file))
            provision_blank_universe(str(db_file), "Lore Test Universe")

            # Create & start session
            status, data = _post_json(f"{web_server}/api/saves/create", {
                "universe_path": str(db_file), "player_name": "Aria",
                "player_persona": "", "difficulty": "Normal", "setup_answers": {},
            })
            save_id = data["save_id"]
            status, data = _post_json(f"{web_server}/api/session/start", {
                "universe_path": str(db_file), "save_id": save_id, "difficulty": "Normal",
            })
            assert status == 200

            # Query Lore API
            url_enc = urllib.parse.quote("What is magic?")
            req = urllib.request.urlopen(f"{web_server}/api/session/lore?query={url_enc}")
            assert req.status == 200
            res = json.loads(req.read().decode("utf-8"))
            assert "answer" in res
            # The narrative stub returns standard mock text in its narration
            assert len(res["answer"]) > 0
    finally:
        if db_file.exists():
            db_file.unlink()


def test_settings_post_preserves_per_provider_keys(web_server):
    """POST /api/settings must keep fireworks/claude fields (not clobber them
    into gemini_*). The old web client wrote every cloud backend into Gemini.
    """
    req = urllib.request.urlopen(f"{web_server}/api/settings")
    original = json.loads(req.read().decode("utf-8"))
    cfg = dict(original)
    cfg["llm_backend"] = "fireworks"
    cfg["fireworks_api_key"] = "fw-secret-test"
    cfg["fireworks_model"] = "accounts/fireworks/models/gpt-oss-120b"
    cfg["anthropic_api_key"] = "claude-secret-test"
    cfg["anthropic_model"] = "claude-opus-4-8"
    cfg["gemini_api_key"] = "gemini-should-stay"
    cfg["gemini_model"] = "gemini-2.0-flash"

    try:
        status, data = _post_json(f"{web_server}/api/settings", cfg)
        assert status == 200, data

        req = urllib.request.urlopen(f"{web_server}/api/settings")
        saved = json.loads(req.read().decode("utf-8"))
        assert saved["fireworks_api_key"] == "fw-secret-test"
        assert saved["fireworks_model"] == "accounts/fireworks/models/gpt-oss-120b"
        assert saved["anthropic_api_key"] == "claude-secret-test"
        assert saved["anthropic_model"] == "claude-opus-4-8"
        assert saved["gemini_api_key"] == "gemini-should-stay"
        assert saved["gemini_model"] == "gemini-2.0-flash"
    finally:
        _post_json(f"{web_server}/api/settings", original)


def test_session_snapshot_uses_named_player_entity(web_server):
    """Location / player_entity_id must follow Entities.entity_type=player,
    not the literal stats key 'player'. Myria's authored cast uses named
    ids (e.g. ysolde_brask), the same shape a custom player entity has.
    """
    from unittest.mock import patch
    from axiom.db_helpers import provision_blank_universe
    from axiom.schema import create_universe_db, get_connection

    tmp_dir = PROJECT_ROOT / "scratch"
    tmp_dir.mkdir(exist_ok=True)
    db_file = tmp_dir / "test_web_named_player.db"
    if db_file.exists():
        db_file.unlink()

    try:
        create_universe_db(str(db_file))
        provision_blank_universe(str(db_file), "Myria")
        with get_connection(str(db_file)) as conn:
            conn.execute(
                "INSERT INTO Entities (entity_id, entity_type, name, is_active) "
                "VALUES ('ysolde_brask', 'player', 'Captain Ysolde Brask', 1);"
            )
            conn.commit()

        with patch("axiom.config.build_llm_from_config", return_value=_NarrativeStub()), \
             patch("axiom.session.resolve_llm_backend", return_value=_NarrativeStub()), \
             patch("axiom.session.Session._resolve_time_llm", return_value=_TimeStub()):
            status, data = _post_json(f"{web_server}/api/saves/create", {
                "universe_path": str(db_file),
                "player_name": "Captain Ysolde Brask",
                "player_persona": "",
                "difficulty": "Normal",
                "setup_answers": {},
            })
            assert status == 200, data
            save_id = data["save_id"]
            # Definition is copied into the save db; re-insert on the play db
            # after start if create_save copies entities from universe.
            status, data = _post_json(f"{web_server}/api/session/start", {
                "universe_path": str(db_file),
                "save_id": save_id,
                "difficulty": "Normal",
            })
            assert status == 200, data
            assert data.get("player_entity_id") == "ysolde_brask"
            assert "verbosity" in data
    finally:
        if db_file.exists():
            db_file.unlink()


def test_session_turn_stream_emits_done(web_server):
    """POST /api/session/turn/stream is SSE: a mocked turn must end with done."""
    from unittest.mock import patch

    tmp_dir = PROJECT_ROOT / "scratch"
    tmp_dir.mkdir(exist_ok=True)
    db_file = tmp_dir / "test_web_turn_stream.db"
    if db_file.exists():
        db_file.unlink()

    try:
        with patch("axiom.config.build_llm_from_config", return_value=_NarrativeStub()), \
             patch("axiom.session.resolve_llm_backend", return_value=_NarrativeStub()), \
             patch("axiom.session.Session._resolve_time_llm", return_value=_TimeStub()):
            _start_lifecycle_session(web_server, db_file, "Stream Universe")
            req = urllib.request.Request(
                f"{web_server}/api/session/turn/stream",
                data=json.dumps({"player_input": "I look around."}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req) as res:
                assert res.status == 200
                assert "text/event-stream" in res.headers.get("Content-Type", "")
                body = res.read().decode("utf-8")
            assert "event: done" in body
            assert "The story continues." in body
    finally:
        if db_file.exists():
            db_file.unlink()


def test_session_cancel_without_turn(web_server):
    """POST /api/session/cancel is always 200; count=0 when nothing is running."""
    status, data = _post_json(f"{web_server}/api/session/cancel", {})
    assert status == 200
    assert data["cancelled"] is False
    assert data["count"] == 0


def test_session_verbosity_and_timeline(web_server):
    """Verbosity persists on Universe_Meta; timeline is a JSON list."""
    from unittest.mock import patch

    tmp_dir = PROJECT_ROOT / "scratch"
    tmp_dir.mkdir(exist_ok=True)
    db_file = tmp_dir / "test_web_verbosity.db"
    if db_file.exists():
        db_file.unlink()

    try:
        with patch("axiom.config.build_llm_from_config", return_value=_NarrativeStub()), \
             patch("axiom.session.resolve_llm_backend", return_value=_NarrativeStub()), \
             patch("axiom.session.Session._resolve_time_llm", return_value=_TimeStub()):
            _start_lifecycle_session(web_server, db_file, "Verbosity Universe")
            status, data = _post_json(f"{web_server}/api/session/verbosity", {"level": "short"})
            assert status == 200, data
            assert data["level"] == "short"

            req = urllib.request.urlopen(f"{web_server}/api/session/timeline")
            assert req.status == 200
            timeline = json.loads(req.read().decode("utf-8"))
            assert isinstance(timeline, list)

            req = urllib.request.urlopen(f"{web_server}/api/models")
            assert req.status == 200
            models = json.loads(req.read().decode("utf-8"))
            assert "models" in models
    finally:
        if db_file.exists():
            db_file.unlink()


def test_canonize_requires_folder_universe(web_server):
    """Canonize on a flat .db (no Universe-as-Code folder) is 422."""
    from unittest.mock import patch

    tmp_dir = PROJECT_ROOT / "scratch"
    tmp_dir.mkdir(exist_ok=True)
    db_file = tmp_dir / "test_web_canonize_flat.db"
    if db_file.exists():
        db_file.unlink()

    try:
        with patch("axiom.config.build_llm_from_config", return_value=_NarrativeStub()), \
             patch("axiom.session.resolve_llm_backend", return_value=_NarrativeStub()), \
             patch("axiom.session.Session._resolve_time_llm", return_value=_TimeStub()):
            _start_lifecycle_session(web_server, db_file, "Flat Canon Universe")
            status, data = _post_json(
                f"{web_server}/api/session/canonize",
                {"preview": True, "text": "The hero entered the hall."},
            )
            assert status == 422, data
            assert "error" in data
    finally:
        if db_file.exists():
            db_file.unlink()


def test_saves_duplicate_and_rename(web_server):
    """POST /api/saves/duplicate and /api/saves/rename wrap savestore helpers."""
    from axiom.db_helpers import provision_blank_universe
    from axiom.schema import create_universe_db

    tmp_dir = PROJECT_ROOT / "scratch"
    tmp_dir.mkdir(exist_ok=True)
    db_file = tmp_dir / "test_web_dup_rename.db"
    if db_file.exists():
        db_file.unlink()
    try:
        create_universe_db(str(db_file))
        provision_blank_universe(str(db_file), "Dup Universe")
        status, data = _post_json(f"{web_server}/api/saves/create", {
            "universe_path": str(db_file),
            "player_name": "Aria",
            "player_persona": "",
            "difficulty": "Normal",
            "setup_answers": {},
        })
        assert status == 200, data
        save_id = data["save_id"]

        status, data = _post_json(f"{web_server}/api/saves/duplicate", {
            "universe_path": str(db_file),
            "save_id": save_id,
            "name": "Aria Copy",
        })
        assert status == 200, data
        assert data["save_id"] != save_id

        status, data = _post_json(f"{web_server}/api/saves/rename", {
            "universe_path": str(db_file),
            "save_id": save_id,
            "name": "Renamed Aria",
        })
        assert status == 200, data
        assert data["name"] == "Renamed Aria"
    finally:
        if db_file.exists():
            db_file.unlink()


def test_saves_pack_and_unpack_roundtrip(web_server):
    """GET /api/saves/pack downloads an archive; POST unpack restores it."""
    import tempfile
    from axiom.db_helpers import provision_blank_universe
    from axiom.schema import create_universe_db
    from axiom.savestore import list_saves

    tmp_dir = PROJECT_ROOT / "scratch"
    tmp_dir.mkdir(exist_ok=True)
    db_file = tmp_dir / "test_web_pack_unpack.db"
    if db_file.exists():
        db_file.unlink()
    archive = None
    try:
        create_universe_db(str(db_file))
        provision_blank_universe(str(db_file), "Pack Universe")
        status, data = _post_json(f"{web_server}/api/saves/create", {
            "universe_path": str(db_file),
            "player_name": "Aria",
            "player_persona": "",
            "difficulty": "Normal",
            "setup_answers": {},
        })
        assert status == 200, data
        save_id = data["save_id"]

        url = (
            f"{web_server}/api/saves/pack?universe={urllib.parse.quote(str(db_file))}"
            f"&save_id={urllib.parse.quote(save_id)}"
        )
        req = urllib.request.urlopen(url)
        assert req.status == 200
        blob = req.read()
        assert len(blob) > 20
        archive = Path(tempfile.mkstemp(suffix=".axiomsave")[1])
        archive.write_bytes(blob)

        status, data = _post_json(f"{web_server}/api/saves/unpack", {
            "universe_path": str(db_file),
            "path": str(archive),
        })
        assert status == 200, data
        assert data["save_id"]
        ids = {s["save_id"] for s in list_saves(str(db_file))}
        assert save_id in ids
        assert data["save_id"] in ids
    finally:
        if db_file.exists():
            db_file.unlink()
        if archive is not None:
            archive.unlink(missing_ok=True)


def test_universe_export_download(web_server):
    """GET /api/universes/export returns a .axiom archive for a flat db."""
    from axiom.db_helpers import provision_blank_universe
    from axiom.schema import create_universe_db

    tmp_dir = PROJECT_ROOT / "scratch"
    tmp_dir.mkdir(exist_ok=True)
    db_file = tmp_dir / "test_web_uni_export.db"
    if db_file.exists():
        db_file.unlink()
    try:
        create_universe_db(str(db_file))
        provision_blank_universe(str(db_file), "Export Universe")
        url = f"{web_server}/api/universes/export?universe={urllib.parse.quote(str(db_file))}"
        req = urllib.request.urlopen(url)
        assert req.status == 200
        data = req.read()
        assert data[:2] == b"PK"  # zip / .axiom
    finally:
        if db_file.exists():
            db_file.unlink()


def test_session_integrity_endpoint(web_server):
    """GET /api/session/integrity reports EventSourcer.validate_integrity."""
    from unittest.mock import patch

    tmp_dir = PROJECT_ROOT / "scratch"
    tmp_dir.mkdir(exist_ok=True)
    db_file = tmp_dir / "test_web_integrity.db"
    if db_file.exists():
        db_file.unlink()
    try:
        with patch("axiom.config.build_llm_from_config", return_value=_NarrativeStub()), \
             patch("axiom.session.resolve_llm_backend", return_value=_NarrativeStub()), \
             patch("axiom.session.Session._resolve_time_llm", return_value=_TimeStub()):
            _start_lifecycle_session(web_server, db_file, "Integrity Universe")
            req = urllib.request.urlopen(f"{web_server}/api/session/integrity")
            assert req.status == 200
            data = json.loads(req.read().decode("utf-8"))
            assert "ok" in data
            assert "mismatches" in data
    finally:
        if db_file.exists():
            db_file.unlink()


def test_canonize_apply_save_scope_writes_lore_to_save(web_server):
    """Selected lore goes into this save's Lore_Book, not a missing world tree."""
    from unittest.mock import patch
    from axiom.schema import get_connection

    tmp_dir = PROJECT_ROOT / "scratch"
    tmp_dir.mkdir(exist_ok=True)
    db_file = tmp_dir / "test_web_canon_save.db"
    if db_file.exists():
        db_file.unlink()
    try:
        with patch("axiom.config.build_llm_from_config", return_value=_NarrativeStub()), \
             patch("axiom.session.resolve_llm_backend", return_value=_NarrativeStub()), \
             patch("axiom.session.Session._resolve_time_llm", return_value=_TimeStub()):
            _start_lifecycle_session(web_server, db_file, "Canon Save Universe")
            status, data = _post_json(f"{web_server}/api/session/canonize/apply", {
                "scope": "save",
                "lore_entries": [{
                    "category": "history",
                    "name": "The Usurper of the Ash Throne",
                    "keywords": "arven deymar, usurper, coup, empire",
                    "content": "A commoner took the Ash Throne; every power on Myria is watching.",
                }],
                "entities": [],
            })
            assert status == 200, data
            assert data.get("scope") == "save"
            from main_web import ACTIVE_SESSION
            with get_connection(ACTIVE_SESSION._db_path) as conn:
                row = conn.execute(
                    "SELECT name, keywords FROM Session_Lore "
                    "WHERE name = 'The Usurper of the Ash Throne';"
                ).fetchone()
                if row is None:
                    row = conn.execute(
                        "SELECT name, keywords FROM Lore_Book "
                        "WHERE name = 'The Usurper of the Ash Throne';"
                    ).fetchone()
            assert row is not None
            assert "usurper" in (row["keywords"] or "").lower()
    finally:
        if db_file.exists():
            db_file.unlink()


def test_canonize_apply_ignores_client_paths(web_server, tmp_path):
    """staged_dir/src_dir/universe_db from the client are never trusted
    (apply mirrors with orphan purge + rmtree → arbitrary file deletion)."""
    from unittest.mock import patch

    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "keep.txt").write_text("precious", encoding="utf-8")
    empty = tmp_path / "empty" / "staged"
    empty.mkdir(parents=True)

    tmp_dir = PROJECT_ROOT / "scratch"
    tmp_dir.mkdir(exist_ok=True)
    db_file = tmp_dir / "test_web_canon_paths.db"
    if db_file.exists():
        db_file.unlink()
    try:
        with patch("axiom.config.build_llm_from_config", return_value=_NarrativeStub()), \
             patch("axiom.session.resolve_llm_backend", return_value=_NarrativeStub()), \
             patch("axiom.session.Session._resolve_time_llm", return_value=_TimeStub()):
            _start_lifecycle_session(web_server, db_file, "Canon Paths Universe")
            with patch("axiom.canonize.apply_canonize_preview") as apply_mock:
                status, _ = _post_json(f"{web_server}/api/session/canonize/apply", {
                    "staged_dir": str(empty),
                    "src_dir": str(victim),
                    "universe_db": str(tmp_path / "x.db"),
                })
            assert status == 400
            apply_mock.assert_not_called()
        assert (victim / "keep.txt").exists()
        assert empty.exists()
    finally:
        if db_file.exists():
            db_file.unlink()


# ── TICKET-094: CORS / CSRF / DNS-rebinding / traversal hardening ──

def test_no_cors_header_on_responses(web_server):
    """The front is same-origin: no Access-Control-Allow-Origin should ever
    be sent (it used to be '*', letting any page in the browser read the API).
    """
    req = urllib.request.urlopen(f"{web_server}/api/translations")
    assert req.status == 200
    assert "Access-Control-Allow-Origin" not in req.headers

    req2 = urllib.request.urlopen(f"{web_server}/")
    assert req2.status == 200
    assert "Access-Control-Allow-Origin" not in req2.headers


def test_post_with_foreign_origin_is_rejected(web_server):
    """A cross-origin POST (Origin header from another site) must be 403'd,
    even with a correct Host and a JSON Content-Type -- this is the anti-CSRF
    check, independent of the Host/DNS-rebinding check."""
    req = urllib.request.Request(
        f"{web_server}/api/session/cancel",
        data=json.dumps({}).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Origin": "http://evil.example",
        },
        method="POST",
    )
    try:
        urllib.request.urlopen(req)
        assert False, "expected HTTPError 403"
    except urllib.error.HTTPError as exc:
        assert exc.code == 403
        data = json.loads(exc.read().decode("utf-8"))
        assert "error" in data


def test_post_with_legitimate_origin_is_accepted(web_server):
    """A same-origin POST (Origin matches http://127.0.0.1:<port>) must go
    through normally."""
    port = urllib.parse.urlsplit(web_server).port
    req = urllib.request.Request(
        f"{web_server}/api/session/cancel",
        data=json.dumps({}).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Origin": f"http://127.0.0.1:{port}",
        },
        method="POST",
    )
    res = urllib.request.urlopen(req)
    assert res.status == 200
    data = json.loads(res.read().decode("utf-8"))
    assert "cancelled" in data


def test_post_without_origin_or_referer_is_accepted(web_server):
    """Non-browser clients (curl, this test suite's own _post_json) send
    neither Origin nor Referer -- they must still be able to call the API."""
    status, data = _post_json(f"{web_server}/api/session/cancel", {})
    assert status == 200
    assert "cancelled" in data


def test_foreign_host_header_is_rejected(web_server):
    """DNS-rebinding: a request whose Host header does not name this server
    (127.0.0.1/localhost/[::1] + the real port) must be rejected, even for a
    plain GET."""
    req = urllib.request.Request(
        f"{web_server}/api/translations",
        headers={"Host": "evil.example"},
    )
    try:
        urllib.request.urlopen(req)
        assert False, "expected HTTPError 403"
    except urllib.error.HTTPError as exc:
        assert exc.code == 403


def test_post_without_json_content_type_is_rejected(web_server):
    """A cross-site form/fetch cannot set Content-Type: application/json
    without a CORS preflight, so a JSON API route receiving a POST without
    that header must be rejected (except the whitelisted no-body routes)."""
    req = urllib.request.Request(
        f"{web_server}/api/session/cancel",
        data=json.dumps({}).encode("utf-8"),
        method="POST",
    )
    try:
        urllib.request.urlopen(req)
        assert False, "expected HTTPError 403"
    except urllib.error.HTTPError as exc:
        assert exc.code == 403


def test_post_test_connection_exempt_from_json_content_type(web_server):
    """/api/settings/test-connection is called by the front with no body and
    no Content-Type header at all -- it must stay reachable."""
    req = urllib.request.Request(
        f"{web_server}/api/settings/test-connection",
        method="POST",
    )
    res = urllib.request.urlopen(req)
    assert res.status == 200


def test_creator_file_traversal_sibling_prefix_rejected(web_server, tmp_path):
    """Regression for the `startswith` traversal guard: a sibling directory
    that merely shares a name prefix (MyWorld vs MyWorld2) used to pass the
    old `str(target).startswith(str(base))` check because it has no trailing
    separator. `Path.is_relative_to` must correctly reject it."""
    my_world = tmp_path / "MyWorld"
    my_world.mkdir()
    my_world2 = tmp_path / "MyWorld2"
    my_world2.mkdir()
    (my_world2 / "secret.txt").write_text("do not leak", encoding="utf-8")

    url = (
        f"{web_server}/api/creator/file"
        f"?universe={urllib.parse.quote(str(my_world))}"
        f"&rel_path={urllib.parse.quote('../MyWorld2/secret.txt')}"
    )
    try:
        urllib.request.urlopen(url)
        assert False, "expected HTTPError 404"
    except urllib.error.HTTPError as exc:
        assert exc.code == 404




def test_settings_save_keeps_the_server_mod_settings(web_server):
    """The browser posts its whole (possibly stale) config: the mods' settings, owned
    by the server (mods page, mod settings tabs, Canon auto), must not be overwritten."""
    from axiom.config import load_config, save_config

    cfg = load_config()
    cfg.mod_settings.setdefault("axiom.turn", {})["auto_canonize"] = True
    save_config(cfg)

    with urllib.request.urlopen(f"{web_server}/api/settings") as res:
        browser_copy = json.loads(res.read().decode("utf-8"))
    browser_copy["mod_settings"] = {}          # stale copy taken before the toggle
    status, _ = _post_json(f"{web_server}/api/settings", browser_copy)
    assert status == 200
    assert load_config().mod_settings["axiom.turn"]["auto_canonize"] is True


def test_mod_web_extensions_endpoints(web_server):
    from axiom.kernel.loader import get_kernel_registry

    reg = get_kernel_registry()
    reg.add_to_slot("axiom.ui.web:settings_tab", "probe.web", {
        "id": "probe_tab", "title": "Probe",
        "fields": [{"key": "level", "label": "Level", "type": "number", "default": 1}],
    })
    try:
        with urllib.request.urlopen(f"{web_server}/api/mods/web-extensions") as res:
            data = json.loads(res.read().decode("utf-8"))
        tab = next(t for t in data["settings_tabs"] if t["id"] == "probe_tab")
        assert tab["fields"][0]["value"] == 1

        status, _ = _post_json(f"{web_server}/api/mods/web-settings", {"id": "probe_tab", "values": {"level": "3"}})
        assert status == 200
        from axiom.config import load_config
        assert load_config().mod_settings["probe.web"]["level"] == 3

        status, _ = _post_json(f"{web_server}/api/mods/web-settings", {"id": "nope", "values": {}})
        assert status == 404
    finally:
        reg.remove_slot_contribution("axiom.ui.web:settings_tab", "probe.web")
