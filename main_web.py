#!/usr/bin/env python3
"""
main_web.py

A standard-library-only multi-threaded HTTP server that provides a web interface
for Axiom AI. It serves static assets from web/ and acts as a JSON API gateway
to the headless axiom engine.

To run:
    python3 main_web.py
"""

import sys
import os
import json
import re
import urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import threading
import webbrowser
from datetime import datetime, timezone
import uuid

# Ensure the root is on sys.path so axiom can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent))

from axiom.config import load_config, save_config, AppConfig
from axiom.db_helpers import (
    create_new_save,
    load_saves,
    provision_blank_universe,
    load_rules_for_session,
    load_active_entities,
    get_max_turn_id,
    get_current_time,
)
from axiom.universe import Universe
from axiom.session import Session
from axiom.logger import logger
from axiom.schema import create_universe_db, get_connection
from axiom.paths import UNIVERSES_DIR, get_settings_file, get_config_dir
from core.localization import get_translations_dict, tr
from core.st_parser import parse_st_card

# Active session reference
ACTIVE_SESSION = None
ACTIVE_SESSION_LOCK = threading.Lock()

# Define static directories
PROJECT_ROOT = Path(__file__).resolve().parent
WEB_DIR = PROJECT_ROOT / "web"
ASSETS_BASE_DIR = Path.home() / "AxiomAI" / "assets"
# Repo-bundled ambiance tracks (opt-in: the app ships with none), mirrors
# ui/ambiance_manager.py::_pick_random_file's `assets/audio/<tag>/` layout.
AUDIO_ASSETS_DIR = PROJECT_ROOT / "assets" / "audio"

_AUDIO_CONTENT_TYPES = {".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".wav": "audio/wav"}


def pick_ambiance_track(tag: str) -> str | None:
    """Pick a random ambiance track for `tag`, or None if none are bundled.

    Mirrors ui/ambiance_manager.py::_pick_random_file. `AUDIO_ASSETS_DIR` is a
    module attribute (not a call-time constant) so tests can monkeypatch it
    without writing into the real repo's assets/ folder.
    """
    import random
    safe_tag = "".join(c for c in tag if c.isalnum() or c in "_-")
    audio_dir = AUDIO_ASSETS_DIR / safe_tag
    if not audio_dir.is_dir():
        return None
    files = [f.name for f in audio_dir.iterdir() if f.is_file() and f.suffix.lower() in _AUDIO_CONTENT_TYPES]
    return random.choice(files) if files else None

class AxiomWebHandler(BaseHTTPRequestHandler):
    
    def log_message(self, format, *args):
        # Override to suppress spam in terminal logs
        pass

    def send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        # Handle API routes
        if path.startswith("/api/"):
            self.handle_api_get(path, parsed_url.query)
            return

        # Serve static files
        if path == "/":
            self.serve_file(WEB_DIR / "index.html", "text/html")
        elif path == "/style.css":
            self.serve_file(WEB_DIR / "style.css", "text/css")
        elif path == "/app.js":
            self.serve_file(WEB_DIR / "app.js", "application/javascript")
        elif path.startswith("/assets/"):
            # Serve game assets (illustrations, etc.) from ~/AxiomAI/assets/
            rel_path = path[len("/assets/"):]
            target_file = ASSETS_BASE_DIR / rel_path
            # Resolve to prevent directory traversal
            try:
                target_file = target_file.resolve()
                if target_file.is_file() and str(target_file).startswith(str(ASSETS_BASE_DIR)):
                    self.serve_file(target_file, "image/png")
                else:
                    self.send_error_json(404, "Asset not found")
            except Exception:
                self.send_error_json(404, "Asset error")
        elif path.startswith("/audio/"):
            # Serve repo-bundled ambiance tracks from assets/audio/<tag>/<file>.
            rel_path = path[len("/audio/"):]
            target_file = AUDIO_ASSETS_DIR / rel_path
            try:
                target_file = target_file.resolve()
                content_type = _AUDIO_CONTENT_TYPES.get(target_file.suffix.lower())
                if content_type and target_file.is_file() and str(target_file).startswith(str(AUDIO_ASSETS_DIR.resolve())):
                    self.serve_file(target_file, content_type)
                else:
                    self.send_error_json(404, "Audio track not found")
            except Exception:
                self.send_error_json(404, "Audio track error")
        else:
            self.send_error_json(404, "Not Found")

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path.startswith("/api/"):
            # Read body
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else ""
            
            payload = {}
            if body:
                try:
                    payload = json.loads(body)
                except json.JSONDecodeError:
                    self.send_error_json(400, "Invalid JSON payload")
                    return

            self.handle_api_post(path, payload)
        else:
            self.send_error_json(404, "Not Found")

    def serve_file(self, file_path: Path, content_type: str):
        if not file_path.exists():
            self.send_error_json(404, f"File not found: {file_path.name}")
            return
        try:
            content = file_path.read_bytes()
            self.send_response(200)
            self.send_cors_headers()
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as exc:
            self.send_error_json(500, f"Error serving file: {exc}")

    def send_json(self, data, status=200):
        try:
            content = json.dumps(data).encode("utf-8")
            self.send_response(status)
            self.send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as exc:
            self.send_error_json(500, f"Serialization error: {exc}")

    def send_error_json(self, status, message):
        self.send_json({"error": message}, status)

    # ── API GET Handlers ──
    def handle_api_get(self, path: str, query_str: str):
        global ACTIVE_SESSION
        query_params = urllib.parse.parse_qs(query_str)
        
        if path == "/api/translations":
            # Load translation dictionary for configured language
            try:
                cfg = load_config()
                lang = getattr(cfg, "language", "en")
                dicts = get_translations_dict()
                lang_dict = dicts.get(lang, dicts.get("en", {}))
                self.send_json(lang_dict)
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/settings":
            try:
                cfg = load_config()
                self.send_json(cfg.__dict__)
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/personas":
            try:
                # load_config() ensures GLOBAL_DB_FILE is provisioned (lazy
                # create_global_db), same as every Qt entry point that touches personas.
                load_config()
                from axiom.config import _resolve_global_db_file
                GLOBAL_DB_FILE = _resolve_global_db_file()
                with get_connection(str(GLOBAL_DB_FILE)) as conn:
                    rows = conn.execute("SELECT persona_id, name, description FROM Global_Personas;").fetchall()
                self.send_json([{"persona_id": r["persona_id"], "name": r["name"], "description": r["description"]} for r in rows])
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/universes":
            try:
                # Scan ~/AxiomAI/universes
                UNIVERSES_DIR.mkdir(parents=True, exist_ok=True)
                universes = []
                for p in UNIVERSES_DIR.glob("*"):
                    if p.suffix == ".db" or (p.is_dir() and not p.name.startswith(".")):
                        # Load saves
                        db_path = p
                        if p.is_dir():
                            db_path = p / ".axiom-cache" / "universe.db"
                        
                        saves = []
                        uni_name = p.stem
                        uni_desc = ""
                        
                        if db_path.exists():
                            try:
                                saves = load_saves(str(db_path))
                                # Fetch meta info
                                with get_connection(str(db_path)) as conn:
                                    row = conn.execute("SELECT value FROM Universe_Meta WHERE key='universe_name';").fetchone()
                                    if row:
                                        uni_name = row[0]
                                    row = conn.execute("SELECT value FROM Universe_Meta WHERE key='universe_description';").fetchone()
                                    if row:
                                        uni_desc = row[0]
                            except Exception:
                                pass
                        
                        universes.append({
                            "name": uni_name,
                            "description": uni_desc,
                            "path": str(p),
                            "is_folder": p.is_dir(),
                            "saves": saves
                        })
                self.send_json(universes)
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/setup/questions":
            uni_path = query_params.get("universe", [None])[0]
            if not uni_path:
                self.send_error_json(400, "Missing 'universe' parameter")
                return
            
            db_path = Path(uni_path)
            if db_path.is_dir():
                db_path = db_path / ".axiom-cache" / "universe.db"

            if not db_path.exists():
                self.send_json({"questions": []})
                return

            try:
                questions = []
                with get_connection(str(db_path)) as conn:
                    # Select setup questions from db
                    rows = conn.execute("SELECT setup_id, question, type, options, max_selections, priority FROM Story_Setup ORDER BY priority ASC;").fetchall()
                    for r in rows:
                        questions.append({
                            "setup_id": r["setup_id"],
                            "question": r["question"],
                            "type": r["type"],
                            "options": r["options"],
                            "max_selections": r["max_selections"],
                            "priority": r["priority"]
                        })
                self.send_json({"questions": questions})
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/saves/export":
            uni_path = query_params.get("universe", [None])[0]
            save_id = query_params.get("save_id", [None])[0]
            if not uni_path or not save_id:
                self.send_error_json(400, "Missing parameters")
                return

            db_path = Path(uni_path)
            if db_path.is_dir():
                db_path = db_path / ".axiom-cache" / "universe.db"

            try:
                from axiom.saves import export_save_state
                from axiom.savestore import resolve_save_db
                
                db = resolve_save_db(str(db_path), save_id) or str(db_path)
                
                import tempfile
                tmp_fd, tmp_name = tempfile.mkstemp(suffix=".toml")
                os.close(tmp_fd)
                tmp_path = Path(tmp_name)
                
                try:
                    export_save_state(db, save_id, tmp_path)
                    toml_content = tmp_path.read_text(encoding="utf-8")
                finally:
                    tmp_path.unlink(missing_ok=True)
                
                self.send_json({"toml": toml_content})
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/session/checkpoints":
            if not ACTIVE_SESSION:
                self.send_error_json(400, "No active session loaded")
                return
            try:
                chk = ACTIVE_SESSION.list_checkpoints()
                self.send_json(chk)
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/session/inventory":
            if not ACTIVE_SESSION:
                self.send_error_json(400, "No active session loaded")
                return
            try:
                # Mirrors workers/db_tasks.py::LoadInventoryTask: all active
                # entities' items via the engine's own get_inventory() helper.
                from axiom.db_helpers import get_inventory
                with get_connection(ACTIVE_SESSION._db_path) as conn:
                    rows = conn.execute("SELECT entity_id FROM Entities WHERE is_active = 1;").fetchall()
                inventory_map = {}
                for row in rows:
                    eid = row["entity_id"]
                    inv = get_inventory(ACTIVE_SESSION._db_path, ACTIVE_SESSION._save_id, eid)
                    if inv:
                        inventory_map[eid] = inv
                self.send_json(inventory_map)
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/session/lore":
            query = query_params.get("query", [""])[0]
            if not query:
                self.send_json({"answer": ""})
                return
            if not ACTIVE_SESSION:
                self.send_error_json(400, "No active session loaded")
                return
            try:
                # Load structured lore book and global lore from DB
                with get_connection(ACTIVE_SESSION._db_path) as conn:
                    lore_rows = conn.execute(
                        "SELECT entry_id, category, name, keywords, content FROM Lore_Book;"
                    ).fetchall()
                    lore_book = [dict(r) for r in lore_rows]

                    meta_row = conn.execute(
                        "SELECT value FROM Universe_Meta WHERE key = 'global_lore';"
                    ).fetchone()
                    global_lore = meta_row["value"] if meta_row else ""

                from axiom.mini_dico import answer_lore_question
                
                # Retrieve configuration to respect LLM parameters
                cfg = load_config()
                temperature = getattr(cfg, "llm_temperature", 0.7)
                top_p = getattr(cfg, "llm_top_p", 1.0)

                # Ask the LLM the question scoped to this universe's lore
                answer = answer_lore_question(
                    llm=ACTIVE_SESSION._llm,
                    vector_memory=ACTIVE_SESSION._vector_memory,
                    question=query,
                    save_id=ACTIVE_SESSION._save_id,
                    lore_book=lore_book,
                    global_lore=global_lore,
                    temperature=temperature,
                    top_p=top_p,
                )

                self.send_json({"answer": answer})
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/creator/data":
            uni_path = query_params.get("universe", [None])[0]
            if not uni_path:
                self.send_error_json(400, "Missing 'universe' parameter")
                return
            
            db_path = Path(uni_path)
            if db_path.is_dir():
                db_path = db_path / ".axiom-cache" / "universe.db"

            if not db_path.exists():
                self.send_error_json(404, "Universe database not compiled or missing.")
                return

            try:
                # Load all Creator Studio tables
                data = {
                    "is_folder": Path(uni_path).is_dir(),
                    "metadata": {},
                    "stats": [],
                    "entities": [],
                    "locations": [],
                    "connections": [],
                    "rules": [],
                    "events": [],
                    "setup_questions": [],
                    "lore": [],
                    "stat_presets": {},
                    "files": []
                }
                
                # Fetch metadata
                with get_connection(str(db_path)) as conn:
                    # Metadata keys
                    meta_rows = conn.execute("SELECT key, value FROM Universe_Meta;").fetchall()
                    for r in meta_rows:
                        data["metadata"][r["key"]] = r["value"]
                        if r["key"] == "calendar_config":
                            try:
                                cal_data = json.loads(r["value"])
                                data["calendar"] = {
                                    "minutes_per_hour": cal_data.get("mph", 60),
                                    "hours_per_day": cal_data.get("hpd", 24),
                                    "start_day": cal_data.get("sd", 1),
                                    "start_hour": cal_data.get("sh", 0),
                                    "start_minute": cal_data.get("sm", 0),
                                    "month_names": cal_data.get("months", [])
                                }
                            except Exception:
                                pass
                        
                    # Stats
                    stats_rows = conn.execute("SELECT stat_id, name, value_type, description, parameters FROM Stat_Definitions;").fetchall()
                    for r in stats_rows:
                        data["stats"].append({
                            "stat_id": r["stat_id"],
                            "name": r["name"],
                            "value_type": r["value_type"],
                            "description": r["description"],
                            "parameters": json.loads(r["parameters"]) if r["parameters"] else {}
                        })
                        
                    # Entities
                    ent_rows = conn.execute("SELECT entity_id, entity_type, name, description, is_active FROM Entities;").fetchall()
                    for r in ent_rows:
                        # Fetch initial stats
                        stats = {}
                        s_rows = conn.execute("SELECT stat_key, stat_value FROM Entity_Stats WHERE entity_id=?;", (r["entity_id"],)).fetchall()
                        for s in s_rows:
                            stats[s["stat_key"]] = s["stat_value"]
                        data["entities"].append({
                            "entity_id": r["entity_id"],
                            "entity_type": r["entity_type"],
                            "name": r["name"],
                            "description": r["description"],
                            "is_active": bool(r["is_active"]),
                            "stats": stats
                        })
                        
                    # Map locations
                    loc_rows = conn.execute("SELECT location_id, name, scale, parent_id, description, x, y FROM Locations;").fetchall()
                    for r in loc_rows:
                        data["locations"].append({
                            "location_id": r["location_id"],
                            "name": r["name"],
                            "scale": r["scale"],
                            "parent_id": r["parent_id"],
                            "description": r["description"],
                            "x": r["x"],
                            "y": r["y"]
                        })
                        
                    # Map connections
                    conn_rows = conn.execute("SELECT source_id, target_id, distance_km FROM Location_Connections;").fetchall()
                    for r in conn_rows:
                        data["connections"].append({
                            "source_id": r["source_id"],
                            "target_id": r["target_id"],
                            "distance_km": r["distance_km"]
                        })

                    # Rules
                    rule_rows = conn.execute("SELECT rule_id, priority, target_entity, conditions, actions FROM Rules;").fetchall()
                    for r in rule_rows:
                        data["rules"].append({
                            "rule_id": r["rule_id"],
                            "priority": r["priority"],
                            "target_entity": r["target_entity"],
                            "conditions": json.loads(r["conditions"]) if r["conditions"] else [],
                            "actions": json.loads(r["actions"]) if r["actions"] else []
                        })
                        
                    # Calendar events
                    ev_rows = conn.execute("SELECT event_id, trigger_minute, title, description FROM Scheduled_Events;").fetchall()
                    for r in ev_rows:
                        data["events"].append({
                            "event_id": r["event_id"],
                            "trigger_minute": r["trigger_minute"],
                            "title": r["title"],
                            "description": r["description"]
                        })

                    # Setup Questions
                    setup_rows = conn.execute("SELECT setup_id, question, type, options, max_selections, priority FROM Story_Setup;").fetchall()
                    for r in setup_rows:
                        data["setup_questions"].append({
                            "setup_id": r["setup_id"],
                            "question": r["question"],
                            "type": r["type"],
                            "options": json.loads(r["options"]) if r["options"] else [],
                            "max_selections": r["max_selections"],
                            "priority": r["priority"]
                        })

                    # Lore Book
                    lore_rows = conn.execute("SELECT entry_id, category, name, keywords, content FROM Lore_Book;").fetchall()
                    for r in lore_rows:
                        data["lore"].append({
                            "entry_id": r["entry_id"],
                            "category": r["category"],
                            "name": r["name"],
                            "keywords": r["keywords"],
                            "text": r["content"]
                        })

                # Presets
                try:
                    from axiom.presets import STAT_PRESETS
                    data["stat_presets"] = STAT_PRESETS
                except ImportError:
                    pass

                # Files list if folder
                if Path(uni_path).is_dir():
                    files = []
                    for f in Path(uni_path).glob("**/*"):
                        if f.is_file() and f.suffix in (".toml", ".md", ".json") and ".axiom-cache" not in f.parts and ".git" not in f.parts:
                            files.append({
                                "rel_path": str(f.relative_to(uni_path)),
                                "size": f.stat().st_size
                            })
                    data["files"] = files

                self.send_json(data)
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/creator/file":
            uni_path = query_params.get("universe", [None])[0]
            rel_path = query_params.get("rel_path", [None])[0]
            if not uni_path or not rel_path:
                self.send_error_json(400, "Missing parameters")
                return
            try:
                target = Path(uni_path) / rel_path
                if target.exists() and str(target.resolve()).startswith(str(Path(uni_path).resolve())):
                    content = target.read_text(encoding="utf-8")
                    self.send_json({"content": content})
                else:
                    self.send_error_json(404, "File not found")
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/diagnostic":
            run_tests = query_params.get("tests", ["false"])[0].lower() == "true"
            try:
                from tools.diagnostic import run_diagnostics, format_report
                sections = run_diagnostics(run_tests=run_tests, offline=False)
                self.send_json({"report": format_report(sections)})
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/audio/track":
            tag = query_params.get("tag", [""])[0]
            if not tag:
                self.send_error_json(400, "Missing 'tag' parameter")
                return
            try:
                track = pick_ambiance_track(tag)
                self.send_json({"tag": tag, "file": track})
            except Exception as exc:
                self.send_error_json(500, str(exc))

        else:
            self.send_error_json(404, "Not Found")

    # ── API POST Handlers ──
    def handle_api_post(self, path: str, payload: dict):
        global ACTIVE_SESSION

        if path == "/api/settings":
            try:
                # Save config
                cfg = AppConfig(**payload)
                save_config(cfg)

                # Re-load translations in case language changed
                from core.localization import reload_translations
                reload_translations()

                # Update live active session LLM immediately if loaded
                if ACTIVE_SESSION:
                    from axiom.config import build_llm_from_config
                    with ACTIVE_SESSION_LOCK:
                        ACTIVE_SESSION._llm = build_llm_from_config(cfg)
                        if ACTIVE_SESSION._mode == "Companion":
                            from axiom.config import resolve_extraction_model
                            ACTIVE_SESSION._hero_llm = build_llm_from_config(cfg, model_override=resolve_extraction_model(cfg))

                self.send_json({"status": "success"})
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/personas":
            try:
                # Mirrors workers/db_tasks.py::SaveGlobalPersonasTask: replace the
                # whole Global_Personas table (small, editor-owned list).
                load_config()
                from axiom.config import _resolve_global_db_file
                GLOBAL_DB_FILE = _resolve_global_db_file()
                personas = payload.get("personas", [])
                with get_connection(str(GLOBAL_DB_FILE)) as conn:
                    conn.execute("DELETE FROM Global_Personas;")
                    for p in personas:
                        conn.execute(
                            "INSERT INTO Global_Personas (persona_id, name, description) VALUES (?, ?, ?);",
                            (p["persona_id"], p.get("name", ""), p.get("description", ""))
                        )
                    conn.commit()
                self.send_json({"status": "success"})
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/settings/test-connection":
            try:
                cfg = load_config()
                # Run connection check asynchronously or synchronously
                from axiom.backends.base import LLMBackend
                from axiom.config import build_llm_from_config
                llm = build_llm_from_config(cfg)
                available = llm.is_available()
                if available:
                    self.send_json({"message": f"Connection OK: {cfg.llm_backend}"})
                else:
                    self.send_json({"message": "LLM backend is not responding."})
            except Exception as exc:
                self.send_json({"message": f"Connection Error: {exc}"})

        elif path == "/api/universes/create":
            name = payload.get("name", "New Universe").strip()
            if not name:
                self.send_error_json(400, "Invalid name")
                return
            try:
                safe_name = "".join(c if c.isalnum() or c in "_ " else "_" for c in name)
                db_path = UNIVERSES_DIR / f"{safe_name}.db"
                create_universe_db(str(db_path))
                provision_blank_universe(str(db_path), name)
                self.send_json({"status": "success", "path": str(db_path)})
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/universes/import":
            axiom_path = payload.get("path", "").strip()
            if not axiom_path or not Path(axiom_path).exists():
                self.send_error_json(400, "Archive file does not exist")
                return
            try:
                from axiom.package import unpack_universe
                dest_folder = UNIVERSES_DIR / Path(axiom_path).stem
                unpack_universe(axiom_path, str(dest_folder))
                self.send_json({"status": "success", "path": str(dest_folder)})
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/universes/import-st":
            st_path = payload.get("path", "").strip()
            if not st_path or not Path(st_path).exists():
                self.send_error_json(400, "PNG/JSON card does not exist")
                return
            try:
                data = parse_st_card(st_path)
                name = data.get("name", "Unknown Character")
                safe_name = "".join(c if c.isalnum() or c in "_ " else "_" for c in name)
                db_path = UNIVERSES_DIR / f"ST_{safe_name}.db"
                
                # Check duplicate
                counter = 1
                while db_path.exists():
                    db_path = UNIVERSES_DIR / f"ST_{safe_name}_{counter}.db"
                    counter += 1
                
                db_path_str = str(db_path)
                create_universe_db(db_path_str)
                
                # Default prompt
                default_prompt = (
                    "You are the Game Master and the characters of this world. "
                    "You MUST NOT act, speak, or think for the User/Player. "
                    "Wait for the User input."
                )
                system_prompt = data.get("system_prompt", default_prompt) or default_prompt
                
                lore_parts = []
                if data.get("description"): lore_parts.append(f"### Description\n{data['description']}")
                if data.get("personality"): lore_parts.append(f"### Personality\n{data['personality']}")
                if data.get("scenario"):    lore_parts.append(f"### Scenario\n{data['scenario']}")
                composite_lore = "\n\n".join(lore_parts)

                # Alternate greetings setup
                first_mes = data.get("first_mes", "")
                alt_greetings = data.get("alternate_greetings", [])
                if not alt_greetings and "data" in data:
                    alt_greetings = data.get("data", {}).get("alternate_greetings", [])
                
                all_variants = [first_mes] if first_mes else []
                if isinstance(alt_greetings, list):
                    for alt in alt_greetings:
                        if isinstance(alt, str) and alt.strip():
                            all_variants.append(alt.strip())
                        elif isinstance(alt, dict) and alt.get("message"):
                            all_variants.append(alt["message"].strip())

                first_msg_meta = "\n\n---VARIANT---\n\n".join(all_variants) if all_variants else ""

                # Insert metadata and tables
                with get_connection(db_path_str) as conn:
                    conn.execute("INSERT OR REPLACE INTO Universe_Meta (key, value) VALUES ('universe_name', ?);", (name,))
                    conn.execute("INSERT OR REPLACE INTO Universe_Meta (key, value) VALUES ('system_prompt', ?);", (system_prompt,))
                    conn.execute("INSERT OR REPLACE INTO Universe_Meta (key, value) VALUES ('global_lore', ?);", (composite_lore,))
                    conn.execute("INSERT OR REPLACE INTO Universe_Meta (key, value) VALUES ('first_message', ?);", (first_msg_meta,))
                    
                    # Entity player & character
                    char_id = safe_name.replace(" ", "_").lower() or "npc_character"
                    conn.execute("INSERT INTO Entities (entity_id, entity_type, name, description) VALUES (?, 'npc', ?, ?);",
                                 (char_id, name, data.get("description", "")))
                    
                    # Example messages
                    if data.get("mes_example"):
                        conn.execute("INSERT INTO Lore_Book (entry_id, category, name, keywords, content) VALUES (?, 'Example Messages', ?, '', ?);",
                                     (str(uuid.uuid4()), name, data["mes_example"]))

                    # Character book/lorebook V2
                    char_book = data.get("character_book", {})
                    if not char_book and "data" in data:
                        char_book = data.get("data", {}).get("character_book", {})
                    if char_book:
                        entries = char_book.get("entries", [])
                        if isinstance(entries, dict):
                            entries = list(entries.values())
                        for entry in entries:
                            if not entry.get("enabled", True):
                                continue
                            entry_name = entry.get("name") or entry.get("comment") or "Lore Entry"
                            entry_content = entry.get("content", "")
                            keys = entry.get("keys", [])
                            keywords_str = ", ".join(keys) if isinstance(keys, list) else str(keys)
                            
                            conn.execute("INSERT INTO Lore_Book (entry_id, category, name, keywords, content) VALUES (?, 'SillyTavern', ?, ?, ?);",
                                         (str(uuid.uuid4()), entry_name, keywords_str, entry_content))

                    # Insert default player save turn 0
                    if all_variants:
                        default_save_id = str(uuid.uuid4())
                        conn.execute("INSERT INTO Saves (save_id, player_name, difficulty, last_updated, player_persona) VALUES (?, 'Player', 'Normal', ?, '');",
                                     (default_save_id, datetime.now().isoformat()))
                        
                        import random
                        active_idx = random.randint(0, len(all_variants) - 1)
                        event_payload = {"active": active_idx, "variants": all_variants}
                        conn.execute("INSERT INTO Event_Log (save_id, turn_id, event_type, target_entity, payload) VALUES (?, 0, 'narrative_text', ?, ?);",
                                     (default_save_id, char_id, json.dumps(event_payload)))
                    
                    conn.commit()

                self.send_json({"status": "success", "path": db_path_str})
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/universes/delete":
            uni_path = payload.get("path", "").strip()
            if not uni_path or not Path(uni_path).exists():
                self.send_error_json(400, "Universe path does not exist")
                return
            try:
                # Mirrors ui/hub_view.py::_on_card_delete_requested: a folder-backed
                # universe's source root must go too (deleting only the compiled
                # .db cache would leave it to be recompiled on the next refresh).
                import shutil
                from axiom import paths
                from axiom.library import universe_root_for
                from axiom.savestore import delete_universe_saves, list_saves

                db_path_str = uni_path
                target = Path(uni_path)
                if target.is_dir():
                    db_path_str = str(target / ".axiom-cache" / "universe.db")

                try:
                    save_ids = [s["save_id"] for s in list_saves(db_path_str)]
                except Exception:
                    save_ids = []
                for sid in save_ids:
                    vector_dir = paths.get_vector_dir() / sid
                    if vector_dir.is_dir():
                        shutil.rmtree(str(vector_dir), ignore_errors=True)
                delete_universe_saves(db_path_str)

                src_root = universe_root_for(db_path_str)
                if src_root is not None:
                    shutil.rmtree(src_root)
                elif target.exists():
                    target.unlink()
                    for suffix in ("-wal", "-shm"):
                        sidecar = Path(uni_path + suffix)
                        if sidecar.exists():
                            sidecar.unlink()

                self.send_json({"status": "success"})
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/saves/create":
            uni_path = payload.get("universe_path", "")
            player_name = payload.get("player_name", "Alice")
            player_persona = payload.get("player_persona", "")
            difficulty = payload.get("difficulty", "Normal")
            answers = payload.get("setup_answers", {})

            if not uni_path:
                self.send_error_json(400, "Missing universe_path")
                return

            db_path = Path(uni_path)
            if db_path.is_dir():
                db_path = db_path / ".axiom-cache" / "universe.db"

            try:
                save_id = create_new_save(str(db_path), player_name, difficulty, player_persona)

                with get_connection(str(db_path)) as conn:
                    # Log setup answers (audit trail; not read back by the engine).
                    for q_id, ans in answers.items():
                        conn.execute(
                            "INSERT INTO Event_Log (save_id, turn_id, event_type, target_entity, payload) VALUES (?, 0, 'setup_answer', ?, ?);",
                            (save_id, q_id, json.dumps({"answer": ans}))
                        )

                    # Write the turn-0 opening narrative (first_message variant with
                    # @tag substitution from setup answers), mirroring
                    # ui/tabletop_view.py::_show_first_message. Without this, new
                    # web saves started on a blank chat: history has no turn 0.
                    row = conn.execute(
                        "SELECT value FROM Universe_Meta WHERE key='first_message';"
                    ).fetchone()
                    first_message = row["value"] if row else ""
                    if first_message:
                        variants = [
                            v.strip() for v in
                            re.split(r"\s*---VARIANT---\s*", first_message, flags=re.IGNORECASE)
                            if v.strip()
                        ]
                        if not variants:
                            variants = [first_message.strip()]
                        if answers:
                            for i, v in enumerate(variants):
                                for key, val in answers.items():
                                    v = re.sub(rf"@{re.escape(str(key))}", str(val), v, flags=re.IGNORECASE)
                                variants[i] = v
                        event_payload = {"active": 0, "variants": variants}
                        conn.execute(
                            "INSERT INTO Event_Log (save_id, turn_id, event_type, target_entity, payload) VALUES (?, 0, 'narrative_text', 'world', ?);",
                            (save_id, json.dumps(event_payload))
                        )

                    conn.commit()

                self.send_json({"status": "success", "save_id": save_id})
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/saves/delete":
            uni_path = payload.get("universe_path", "")
            save_id = payload.get("save_id", "")
            if not uni_path or not save_id:
                self.send_error_json(400, "Missing parameters")
                return
            db_path = Path(uni_path)
            if db_path.is_dir():
                db_path = db_path / ".axiom-cache" / "universe.db"
            try:
                # NOT axiom.checkpoint.CheckpointManager.delete_save: that one is
                # Hardcore-only (wipes the whole universe_dir) and requires a
                # universe_dir arg this call site never had -- every call here
                # raised TypeError. axiom.savestore.delete_save is the general
                # single-save deletion the Qt Hub's Delete button also uses
                # (via workers/db_tasks.py::DeleteSaveTask).
                from axiom.savestore import delete_save
                deleted = delete_save(str(db_path), save_id)
                if deleted:
                    # DeleteSaveTask also purges the save's VectorMemory dir --
                    # savestore.delete_save only handles Saves rows + illustrations.
                    import shutil
                    from axiom import paths
                    vector_dir = paths.get_vector_dir() / save_id
                    if vector_dir.exists():
                        shutil.rmtree(str(vector_dir))
                    self.send_json({"status": "success"})
                else:
                    self.send_error_json(404, "Save not found")
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/saves/fork":
            uni_path = payload.get("universe_path", "")
            save_id = payload.get("save_id", "")
            turn_id = payload.get("turn_id", 0)
            name = payload.get("name", "Timeline B")
            if not uni_path or not save_id:
                self.send_error_json(400, "Missing parameters")
                return
            db_path = Path(uni_path)
            if db_path.is_dir():
                db_path = db_path / ".axiom-cache" / "universe.db"
            try:
                # Delegate to the engine's fork_save (axiom/saves.py) rather than
                # hand-rolling the copy here: it also carries over Active_Modifiers,
                # Fired_Scheduled_Events (with fired_turn_id), Timeline and
                # Items_Inventory, and rebuilds/snapshots the state cache
                # (TICKET-034/075/086 fixes this reimplementation was missing).
                from axiom.saves import fork_save
                new_save_id = fork_save(str(db_path), save_id, at_turn=int(turn_id), player_name=name)

                self.send_json({"status": "success", "new_save_id": new_save_id})
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/saves/edit":
            uni_path = payload.get("universe_path", "")
            save_id = payload.get("save_id", "")
            original_toml = payload.get("original_toml", "")
            edited_toml = payload.get("edited_toml", "")

            if not uni_path or not save_id:
                self.send_error_json(400, "Missing parameters")
                return

            db_path = Path(uni_path)
            if db_path.is_dir():
                db_path = db_path / ".axiom-cache" / "universe.db"

            try:
                import tomllib
                from axiom.saves import SaveError, apply_correction, diff_save_states
                from axiom.savestore import resolve_save_db

                before = tomllib.loads(original_toml)
                after = tomllib.loads(edited_toml)

                patch = diff_save_states(before, after)
                if not any(patch.values()):
                    self.send_json({"status": "no_change", "turn": -1})
                    return

                db = resolve_save_db(str(db_path), save_id) or str(db_path)
                turn = apply_correction(db, save_id, patch)
                
                from axiom.events import EventSourcer
                sourcer = EventSourcer(db)
                sourcer.rebuild_state_cache(save_id)

                self.send_json({"status": "success", "turn": turn})
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/session/start":
            uni_path = payload.get("universe_path", "")
            save_id = payload.get("save_id", "")
            difficulty = payload.get("difficulty", "Normal")
            if not uni_path or not save_id:
                self.send_error_json(400, "Missing parameters")
                return
            
            db_path = Path(uni_path)
            if db_path.is_dir():
                db_path = db_path / ".axiom-cache" / "universe.db"

            try:
                cfg = load_config()
                from axiom.config import build_llm_from_config
                llm = build_llm_from_config(cfg)
                
                # Check for companion mode models
                hero_llm = None
                if difficulty == "Companion":
                    from axiom.config import resolve_extraction_model
                    hero_llm = build_llm_from_config(cfg, model_override=resolve_extraction_model(cfg))

                with ACTIVE_SESSION_LOCK:
                    ACTIVE_SESSION = Session(
                        str(db_path),
                        save_id,
                        llm=llm,
                        mode=difficulty,
                        hero_llm=hero_llm
                    )

                self.send_json(build_session_snapshot())
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/session/turn":
            if not ACTIVE_SESSION:
                self.send_error_json(400, "No active session loaded")
                return

            player_input = payload.get("player_input", "").strip()
            intents = payload.get("intents", None)
            if not player_input and not intents:
                self.send_error_json(400, "Missing input text or intents")
                return

            try:
                # Lock session while processing turn
                with ACTIVE_SESSION_LOCK:
                    if intents and isinstance(intents, dict):
                        res = ACTIVE_SESSION.take_turn_multiplayer(intents)
                    else:
                        res = ACTIVE_SESSION.take_turn(player_input)

                # include_history=True (default): the client rebuilds the chat
                # from the canonical turn_id-tagged history on every turn, so
                # edit/regenerate/variant-nav controls stay in sync (no
                # client-side event bookkeeping to drift out of sync).
                snapshot = build_session_snapshot()
                snapshot["narrative_text"] = res.narrative_text
                snapshot["image_path"] = res.image_path.name if res.image_path else None
                snapshot["game_state_tag"] = getattr(res, "game_state_tag", "exploration")
                # Hardcore permadeath: mirrors ui/tabletop_hardcore.py's
                # detection (Player_Death rule + Hardcore-mode save). Reported
                # here, not acted on -- the client confirms with the player
                # before calling /api/session/hardcore-delete.
                snapshot["hardcore_death"] = (
                    ACTIVE_SESSION._mode == "Hardcore" and is_player_death_triggered(res)
                )
                self.send_json(snapshot)
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/session/hardcore-delete":
            if not ACTIVE_SESSION:
                self.send_error_json(400, "No active session loaded")
                return
            try:
                with ACTIVE_SESSION_LOCK:
                    db_path = ACTIVE_SESSION._db_path
                    save_id = ACTIVE_SESSION._save_id
                    if ACTIVE_SESSION._mode != "Hardcore":
                        self.send_error_json(400, "Active session is not in Hardcore mode")
                        return
                    ACTIVE_SESSION = None  # drop engine references before deleting

                    deleted = perform_hardcore_deletion(db_path, save_id)
                if deleted:
                    self.send_json({"status": "success"})
                else:
                    self.send_error_json(500, "Deletion failed: save not found")
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/session/rewind":
            if not ACTIVE_SESSION:
                self.send_error_json(400, "No active session loaded")
                return
            target_turn = payload.get("target_turn_id", 0)
            try:
                with ACTIVE_SESSION_LOCK:
                    ACTIVE_SESSION.rewind(target_turn)

                self.send_json(build_session_snapshot())
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/session/variant":
            if not ACTIVE_SESSION:
                self.send_error_json(400, "No active session loaded")
                return
            turn_id = payload.get("turn_id")
            variant_index = payload.get("variant_index")
            if turn_id is None or variant_index is None:
                self.send_error_json(400, "Missing parameters")
                return
            try:
                with ACTIVE_SESSION_LOCK:
                    with get_connection(ACTIVE_SESSION._db_path) as conn:
                        row = conn.execute(
                            "SELECT payload FROM Event_Log WHERE save_id=? AND turn_id=? AND event_type='narrative_text';",
                            (ACTIVE_SESSION._save_id, turn_id)
                        ).fetchone()
                    if not row:
                        self.send_error_json(404, "Narrative event not found for this turn")
                        return

                    variant_payload = json.loads(row["payload"])
                    if not isinstance(variant_payload, dict) or "variants" not in variant_payload:
                        text = variant_payload.get("text", "") if isinstance(variant_payload, dict) else str(variant_payload)
                        variant_payload = {"active": 0, "variants": [text]}
                    if not (0 <= variant_index < len(variant_payload["variants"])):
                        self.send_error_json(400, "Variant index out of range")
                        return
                    variant_payload["active"] = variant_index

                    from axiom.events import EventSourcer
                    EventSourcer(ACTIVE_SESSION._db_path).update_event_payload(
                        ACTIVE_SESSION._save_id, turn_id, "narrative_text", variant_payload
                    )

                self.send_json(build_session_snapshot())
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/session/regenerate":
            if not ACTIVE_SESSION:
                self.send_error_json(400, "No active session loaded")
                return
            turn_id = payload.get("turn_id")
            if turn_id is None:
                self.send_error_json(400, "Missing turn_id")
                return
            try:
                with ACTIVE_SESSION_LOCK:
                    from axiom.events import EventSourcer
                    events = EventSourcer(ACTIVE_SESSION._db_path)

                    turn_events = events.get_events(
                        ACTIVE_SESSION._save_id, start_turn_id=turn_id - 1, up_to_turn_id=turn_id
                    )
                    user_message = ""
                    for ev in turn_events:
                        if ev["turn_id"] == turn_id and ev["event_type"] in ("user_input", "hero_intent"):
                            p = ev["payload"]
                            user_message = p.get("text", "") if isinstance(p, dict) else str(p)
                            break
                    if not user_message:
                        user_message = "..."

                    # -1 (not 0) so turn 0's genesis events are included, mirroring
                    # Session._load_history's early-game handling.
                    sub_history = events.get_events(
                        ACTIVE_SESSION._save_id, start_turn_id=-1, up_to_turn_id=turn_id - 1
                    )

                    with get_connection(ACTIVE_SESSION._db_path) as conn:
                        meta_row = conn.execute(
                            "SELECT key, value FROM Universe_Meta WHERE key IN ('llm_temperature', 'llm_top_p');"
                        ).fetchall()
                    meta = {r["key"]: r["value"] for r in meta_row}
                    try:
                        temperature = float(meta.get("llm_temperature", "0.7")) + 0.1
                    except ValueError:
                        temperature = 0.8
                    try:
                        top_p = float(meta.get("llm_top_p", "1.0"))
                    except ValueError:
                        top_p = 1.0

                    ACTIVE_SESSION.regenerate_variant(
                        turn_id, sub_history, user_message,
                        temperature=temperature, top_p=top_p,
                    )

                self.send_json(build_session_snapshot())
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/session/edit-message":
            if not ACTIVE_SESSION:
                self.send_error_json(400, "No active session loaded")
                return
            event_type = payload.get("event_type", "")
            turn_id = payload.get("turn_id")
            new_text = (payload.get("new_text") or "").strip()
            if turn_id is None or not new_text or event_type not in ("user_input", "narrative_text"):
                self.send_error_json(400, "Missing/invalid parameters")
                return
            try:
                with ACTIVE_SESSION_LOCK:
                    if event_type == "user_input":
                        # Rewind to just before this turn, then resubmit the corrected
                        # text as a new turn -- mirrors
                        # ui/tabletop_view.py::_on_edit_message_requested.
                        ACTIVE_SESSION.rewind(turn_id - 1)
                        res = ACTIVE_SESSION.take_turn(new_text)
                        snapshot = build_session_snapshot()
                        snapshot["narrative_text"] = res.narrative_text
                        snapshot["image_path"] = res.image_path.name if res.image_path else None
                        snapshot["game_state_tag"] = getattr(res, "game_state_tag", "exploration")
                    else:
                        from axiom.events import EventSourcer
                        events = EventSourcer(ACTIVE_SESSION._db_path)
                        with get_connection(ACTIVE_SESSION._db_path) as conn:
                            row = conn.execute(
                                "SELECT payload FROM Event_Log WHERE save_id=? AND turn_id=? AND event_type='narrative_text';",
                                (ACTIVE_SESSION._save_id, turn_id)
                            ).fetchone()
                        if not row:
                            self.send_error_json(404, "Narrative event not found for this turn")
                            return

                        edited_payload = json.loads(row["payload"])
                        if isinstance(edited_payload, dict) and "variants" in edited_payload and "active" in edited_payload:
                            variants = list(edited_payload["variants"])
                            active = edited_payload["active"]
                            if 0 <= active < len(variants):
                                variants[active] = new_text
                                edited_payload["variants"] = variants
                            else:
                                edited_payload["text"] = new_text
                        elif isinstance(edited_payload, dict):
                            edited_payload["text"] = new_text
                        else:
                            edited_payload = {"text": new_text}

                        events.update_event_payload(ACTIVE_SESSION._save_id, turn_id, "narrative_text", edited_payload)

                        if ACTIVE_SESSION._vector_memory is not None:
                            try:
                                ACTIVE_SESSION._vector_memory.update_turn_narrative(
                                    ACTIVE_SESSION._save_id, turn_id, new_text, "narrative"
                                )
                            except Exception:
                                logger.warning("Vector memory update failed on message edit.", exc_info=True)

                        snapshot = build_session_snapshot()

                self.send_json(snapshot)
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/creator/save":
            uni_path = query_params_from_url(self.path).get("universe", "")
            if not uni_path:
                self.send_error_json(400, "Missing 'universe' parameter")
                return

            db_path = Path(uni_path)
            is_folder = db_path.is_dir()
            if is_folder:
                db_path = db_path / ".axiom-cache" / "universe.db"

            try:
                # Write changes back to SQLite database
                with get_connection(str(db_path)) as conn:
                    # Sync metadata
                    meta = payload.get("metadata", {})
                    for k, v in meta.items():
                        conn.execute("INSERT OR REPLACE INTO Universe_Meta (key, value) VALUES (?, ?);", (k, str(v)))
                        
                    # Sync Calendar
                    cal = payload.get("calendar", {})
                    if cal:
                        cal_config_val = json.dumps({
                            "mph": int(cal.get("minutes_per_hour", 60)),
                            "hpd": int(cal.get("hours_per_day", 24)),
                            "dpm": [30] * len(cal.get("month_names", [])),
                            "months": cal.get("month_names", []),
                            "sd": int(cal.get("start_day", 1)),
                            "sh": int(cal.get("start_hour", 0)),
                            "sm": int(cal.get("start_minute", 0))
                        })
                        conn.execute("INSERT OR REPLACE INTO Universe_Meta (key, value) VALUES ('calendar_config', ?);", (cal_config_val,))
                        
                    # Sync Stats
                    conn.execute("DELETE FROM Stat_Definitions;")
                    for s in payload.get("stats", []):
                        conn.execute("INSERT INTO Stat_Definitions (stat_id, name, value_type, description, parameters) VALUES (?, ?, ?, ?, ?);",
                                     (s["stat_id"], s["name"], s["value_type"], s["description"], json.dumps(s.get("parameters", {}))))
                        
                    # Sync Entities
                    conn.execute("DELETE FROM Entities;")
                    conn.execute("DELETE FROM Entity_Stats;")
                    for ent in payload.get("entities", []):
                        conn.execute("INSERT INTO Entities (entity_id, entity_type, name, description) VALUES (?, ?, ?, ?);",
                                     (ent["entity_id"], ent["entity_type"], ent["name"], ent["description"]))
                        for sk, sv in ent.get("stats", {}).items():
                            conn.execute("INSERT INTO Entity_Stats (entity_id, stat_key, stat_value) VALUES (?, ?, ?);",
                                         (ent["entity_id"], sk, str(sv)))
                            
                    # Sync Map
                    conn.execute("DELETE FROM Locations;")
                    conn.execute("DELETE FROM Location_Connections;")
                    for loc in payload.get("locations", []):
                        conn.execute("INSERT INTO Locations (location_id, name, scale, parent_id, description, x, y) VALUES (?, ?, ?, ?, ?, ?, ?);",
                                     (loc["location_id"], loc["name"], loc["scale"], loc.get("parent_id"), loc.get("description", ""), loc.get("x", 0.0), loc.get("y", 0.0)))
                    for c in payload.get("connections", []):
                        conn.execute("INSERT INTO Location_Connections (source_id, target_id, distance_km) VALUES (?, ?, ?);",
                                     (c["source_id"], c["target_id"], c.get("distance_km", 1)))

                    # Sync Rules
                    conn.execute("DELETE FROM Rules;")
                    for r in payload.get("rules", []):
                        conn.execute("INSERT INTO Rules (rule_id, priority, target_entity, conditions, actions) VALUES (?, ?, ?, ?, ?);",
                                     (r["rule_id"], r["priority"], r["target_entity"], json.dumps(r.get("conditions", [])), json.dumps(r.get("actions", []))))
                        
                    # Sync calendar events
                    conn.execute("DELETE FROM Scheduled_Events;")
                    for ev in payload.get("events", []):
                        conn.execute("INSERT INTO Scheduled_Events (event_id, trigger_minute, title, description) VALUES (?, ?, ?, ?);",
                                     (ev["event_id"], ev["trigger_minute"], ev["title"], ev["description"]))

                    # Sync Setup Questions
                    conn.execute("DELETE FROM Story_Setup;")
                    for q in payload.get("setup_questions", []):
                        conn.execute("INSERT INTO Story_Setup (setup_id, question, type, options, max_selections, priority) VALUES (?, ?, ?, ?, ?, ?);",
                                     (q["setup_id"], q["question"], q["type"], json.dumps(q.get("options", [])), q.get("max_selections", 1), q.get("priority", 0)))

                    # Sync Lore Book
                    conn.execute("DELETE FROM Lore_Book;")
                    for l in payload.get("lore", []):
                        conn.execute("INSERT INTO Lore_Book (entry_id, category, name, keywords, content) VALUES (?, ?, ?, ?, ?);",
                                     (l["entry_id"], l["category"], l["name"], l.get("keywords", ""), l.get("text", "")))
                    
                    conn.commit()

                # If folder-backed, decompile database back into text files
                if is_folder:
                    from axiom.decompile import decompile_universe
                    decompile_universe(str(db_path), uni_path)

                self.send_json({"status": "success"})
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/creator/file":
            uni_path = query_params_from_url(self.path).get("universe", "")
            rel_path = query_params_from_url(self.path).get("rel_path", "")
            content = payload.get("content", "")
            if not uni_path or not rel_path:
                self.send_error_json(400, "Missing parameters")
                return
            try:
                target = Path(uni_path) / rel_path
                if str(target.resolve()).startswith(str(Path(uni_path).resolve())):
                    target.write_text(content, encoding="utf-8")
                    
                    # Hot-compile folder back to db
                    db_path = Path(uni_path) / ".axiom-cache" / "universe.db"
                    from axiom.compile import compile_universe
                    compile_universe(uni_path, str(db_path), force=True)
                    
                    self.send_json({"status": "success"})
                else:
                    self.send_error_json(400, "Invalid file path")
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/creator/convert":
            uni_path = payload.get("universe_path", "")
            if not uni_path or not Path(uni_path).exists():
                self.send_error_json(400, "Universe database not found")
                return
            try:
                from axiom.library import convert_flat_db_to_folder
                new_folder = Path(uni_path).parent / Path(uni_path).stem
                convert_flat_db_to_folder(uni_path, str(new_folder))
                
                # Delete old db if successful
                Path(uni_path).unlink(missing_ok=True)
                
                self.send_json({"status": "success", "new_path": str(new_folder)})
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/creator/populate":
            uni_path = query_params_from_url(self.path).get("universe", "")
            targets = payload.get("targets", [])
            prompt = payload.get("prompt", "")
            preview = payload.get("preview", False)

            if not uni_path or not targets:
                self.send_error_json(400, "Missing parameters")
                return

            db_path = Path(uni_path)
            if db_path.is_dir():
                db_path = db_path / ".axiom-cache" / "universe.db"

            try:
                cfg = load_config()
                from axiom.config import build_llm_from_config
                from axiom.populate import POPULATE_TARGETS
                
                # Build target functions
                llm = build_llm_from_config(cfg)
                
                # In order to support preview/diff, we can populate to a temporary DB copy,
                # generate diff vs original, and apply if requested.
                temp_db = str(db_path)
                if preview:
                    # Copy to temp file
                    import shutil
                    temp_db = str(Path(uni_path) / ".axiom-cache" / "temp_populate.db")
                    shutil.copyfile(str(db_path), temp_db)

                # Generate content
                for t in targets:
                    func = POPULATE_TARGETS.get(t)
                    if func:
                        func(temp_db, text=prompt, llm=llm)

                if preview:
                    # Decompile temp populate to see diff
                    diff_text = "Proposed edits loaded in temporary schema. Click Apply to overwrite."
                    self.send_json({"status": "success", "diff": diff_text})
                else:
                    # Save and decompile if folder
                    if Path(uni_path).is_dir():
                        from axiom.decompile import decompile_universe
                        decompile_universe(str(db_path), uni_path)
                    self.send_json({"status": "success"})
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/creator/populate/apply":
            uni_path = query_params_from_url(self.path).get("universe", "")
            if not uni_path:
                self.send_error_json(400, "Missing parameters")
                return
            try:
                temp_db = Path(uni_path) / ".axiom-cache" / "temp_populate.db"
                db_path = Path(uni_path) / ".axiom-cache" / "universe.db"
                if temp_db.exists():
                    import shutil
                    shutil.copyfile(str(temp_db), str(db_path))
                    temp_db.unlink()
                    
                    if Path(uni_path).is_dir():
                        from axiom.decompile import decompile_universe
                        decompile_universe(str(db_path), uni_path)
                        
                    self.send_json({"status": "success"})
                else:
                    self.send_error_json(404, "No proposed populated preview found.")
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/audio/volume":
            # Volume setter no-op/success (volume resolved client side on HTML Audio loops)
            self.send_json({"status": "success"})

        else:
            self.send_error_json(404, "Not Found")

def get_time_system(db_path: str):
    """Build a TimeSystem from a universe's Universe_Meta.calendar_config.

    Session has no time system of its own: CalendarConfig/TimeSystem are
    presentation-side helpers built by ui/tabletop_view.py::_on_meta_loaded
    from the compiled universe's calendar. Mirrored here so /api/session/*
    can format in-game time the same way the Qt app does.
    """
    from axiom.time_system import TimeSystem, CalendarConfig
    try:
        with get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT value FROM Universe_Meta WHERE key='calendar_config';"
            ).fetchone()
        cal_str = row["value"] if row else "{}"
    except Exception:
        cal_str = "{}"
    return TimeSystem(CalendarConfig.from_json(cal_str))


def build_session_snapshot(include_history: bool = True) -> dict:
    """Common response payload shared by every /api/session/* endpoint that
    hands the client a fresh view of the active session (start, turn, rewind,
    variant switch, edit, regenerate): stats, location, travel options,
    formatted time, and (optionally) the full chat history.
    """
    stats = ACTIVE_SESSION.current_stats()
    player_loc = stats.get("player", {}).get("Location", "")

    neighbors = []
    if player_loc:
        from axiom.db_helpers import get_spatial_context
        spatial = get_spatial_context(ACTIVE_SESSION._db_path, player_loc)
        if spatial and "connections" in spatial:
            for n in spatial["connections"]:
                neighbors.append({
                    "location_id": n["location_id"],
                    "name": n["name"],
                    "distance_km": n["distance_km"]
                })

    time_val = get_current_time(ACTIVE_SESSION._db_path, ACTIVE_SESSION._save_id)
    from core.localization import format_time
    time_formatted = format_time(get_time_system(ACTIVE_SESSION._db_path), time_val)

    result = {
        "turn_id": ACTIVE_SESSION.turn_id,
        "current_stats": stats,
        "current_location": player_loc,
        "spatial_neighbors": neighbors,
        "time_formatted": time_formatted,
    }
    if include_history:
        # Raw turn_id-tagged events (mirrors workers/db_tasks.py::LoadSessionHistoryTask)
        # rather than Session._load_history()'s role/content pairs: the client
        # needs turn_id (+ variant metadata) per message to drive edit/
        # regenerate/variant-nav controls, exactly like the Qt chat display.
        with get_connection(ACTIVE_SESSION._db_path) as conn:
            rows = conn.execute(
                "SELECT turn_id, event_type, payload FROM Event_Log "
                "WHERE save_id = ? AND event_type IN ('user_input', 'narrative_text', 'hero_intent') "
                "ORDER BY event_id ASC;",
                (ACTIVE_SESSION._save_id,)
            ).fetchall()
        result["history"] = [
            {"turn_id": r["turn_id"], "event_type": r["event_type"], "payload": json.loads(r["payload"])}
            for r in rows
        ]
        result["universe_name"] = ACTIVE_SESSION.universe.name
        result["player_name"] = player_name_from_save(ACTIVE_SESSION._db_path, ACTIVE_SESSION._save_id)
        result["difficulty"] = ACTIVE_SESSION._mode
        result["save_id"] = ACTIVE_SESSION._save_id
        if ACTIVE_SESSION._mode == "Multiplayer":
            try:
                with get_connection(ACTIVE_SESSION._db_path) as conn:
                    player_rows = conn.execute(
                        "SELECT entity_id, name FROM Entities WHERE entity_type = 'player';"
                    ).fetchall()
                result["players"] = [{"entity_id": r["entity_id"], "name": r["name"]} for r in player_rows]
            except Exception:
                result["players"] = [{"entity_id": "player", "name": result["player_name"]}]
    return result


def is_player_death_triggered(result) -> bool:
    """Scan an ArbitratorResult's triggered rules for a Player_Death event.

    Mirrors ui/tabletop_hardcore.py::HardcoreMixin._check_for_player_death's
    detection (the deletion decision itself also needs the save's difficulty,
    checked separately -- Hardcore only).
    """
    triggered = getattr(result, "triggered_rules", None) or []
    return any(
        isinstance(action, dict)
        and action.get("type") == "trigger_event"
        and "player_death" in str(action.get("event", "")).lower()
        for action in triggered
    )


def perform_hardcore_deletion(db_path: str, save_id: str) -> bool:
    """Irrevocably delete a Hardcore save: fail-safe backup, WAL flush, then
    the same save+assets+vector-store deletion /api/saves/delete uses.

    Mirrors workers/hardcore_worker.py::HardcoreWorker._execute() (backup,
    WAL checkpoint, row deletion, vector/asset cleanup) minus its Qt-thread
    lock-release choreography: the web server holds no long-lived handles
    across requests (each get_connection() is closed within its own request),
    so there is nothing analogous to release before deleting.
    """
    import shutil
    import sqlite3
    from contextlib import closing

    try:
        from database.backup_manager import create_auto_backup
        create_auto_backup(db_path, "hardcore_death")
    except Exception:
        logger.warning("Hardcore auto-backup failed (non-fatal).", exc_info=True)

    try:
        with closing(sqlite3.connect(db_path, timeout=2.0)) as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            conn.execute("PRAGMA journal_mode=DELETE;")
    except sqlite3.Error:
        logger.warning("Hardcore WAL flush failed (non-fatal).", exc_info=True)

    from axiom.savestore import delete_save
    deleted = delete_save(db_path, save_id)
    if deleted:
        from axiom import paths
        vector_dir = paths.get_vector_dir() / save_id
        if vector_dir.exists():
            shutil.rmtree(str(vector_dir))
    return deleted

# Helper to read player name from saves table
def player_name_from_save(db_path: str, save_id: str) -> str:
    try:
        with get_connection(db_path) as conn:
            row = conn.execute("SELECT player_name FROM Saves WHERE save_id=?;", (save_id,)).fetchone()
            return row["player_name"] if row else "Alice"
    except Exception:
        return "Alice"

# URL parameter parsing helpers
def query_params_from_url(url: str) -> dict:
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    return {k: v[0] for k, v in params.items()}

def run_server(port=8000):
    server = ThreadingHTTPServer(("127.0.0.1", port), AxiomWebHandler)
    url = f"http://127.0.0.1:{port}/"
    print("================================================================")
    print(f" Axiom AI Web Server running on: {url}")
    print(" Close this terminal (Ctrl+C) to stop the server.")
    print("================================================================")
    
    # Launch browser
    threading.Thread(target=lambda: webbrowser.open(url), daemon=True).start()
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.shutdown()

if __name__ == "__main__":
    port = 8000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    run_server(port)
