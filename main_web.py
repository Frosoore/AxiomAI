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

from axiom.config import load_config, save_config, AppConfig, get_default_verbosity
from axiom.db_helpers import (
    create_new_save,
    provision_blank_universe,
    load_rules_for_session,
    load_active_entities,
    get_max_turn_id,
    get_current_time,
)
from axiom.savestore import (
    create_save,
    list_saves,
    prepare_save_for_play,
    resolve_save_db,
    find_save_db,
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

# Cooperative cancel for the in-flight turn (mirrors LLMBackend.cancel_event).
# A separate request thread sets the event; the turn thread raises GenerationCancelled.
TURN_CANCEL = threading.Event()
TURN_BUSY = False
TURN_BUSY_LOCK = threading.Lock()

# Paths of the last canonize preview, kept server-side: /canonize/apply must
# never trust staged_dir/src_dir/universe_db sent by the client (apply mirrors
# a tree with orphan purge + rmtree → arbitrary file deletion otherwise).
LAST_CANONIZE_PREVIEW: dict = {}

# Living-memory buffer (mirrors ui/tabletop_view.py::_fact_pending).
# Web had no post-turn extraction before — facts only appeared if desktop
# had distilled them earlier.
_FACT_PENDING: list[str] = []
_FACT_TURN_COUNTER: int = 0
_FACT_WORKER_LOCK = threading.Lock()
_FACT_WORKER_BUSY: bool = False

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

    # Ports/hosts the local web UI may legitimately be reached on. TICKET-094:
    # the front is served by this same process (same-origin `fetch('/api/...')`
    # calls), so it needs no CORS grant -- Access-Control-Allow-Origin was
    # previously "*", which let ANY page open in the same browser read/mutate
    # this local API (saves, memory, hardcore-delete...) regardless of origin.
    _MUTATING_METHODS = ("POST", "PUT", "DELETE", "PATCH")
    # These POST routes take no meaningful JSON body (front calls them as
    # `fetch(url, {method: 'POST'})` with no Content-Type/body at all), so the
    # JSON Content-Type gate below would reject legitimate same-origin calls.
    _JSON_CT_EXEMPT_PATHS = (
        "/api/settings/test-connection",
        "/api/creator/populate/apply",
    )

    def send_cors_headers(self):
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _security_guard(self) -> bool:
        """Anti DNS-rebinding / anti-CSRF gate, run before any route logic.

        1. `Host` must name this server (127.0.0.1/localhost/[::1] + the real
           bound port) -- rejects DNS-rebinding attacks that point an
           attacker-controlled hostname at 127.0.0.1.
        2. For mutating methods, an `Origin` (or, failing that, `Referer`)
           header that names a *different* origin is rejected. Absent both
           headers, the request is allowed through (curl, the test suite, and
           other non-browser clients don't send them; a same-origin browser
           fetch always does).
        3. For mutating `/api/...` requests that are not multipart uploads,
           the body must be declared `application/json` -- a third-party page
           cannot set that header on a cross-origin `fetch`/form submission
           without triggering a CORS preflight, which this server (having no
           Access-Control-Allow-Origin) will not satisfy.
        Sends a 403 JSON error and returns False on rejection.
        """
        port = self.server.server_port
        allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
        host = self.headers.get("Host", "")
        if host not in allowed_hosts:
            self.send_error_json(403, "Invalid Host header")
            return False

        if self.command not in self._MUTATING_METHODS:
            return True

        allowed_origins = {
            f"http://127.0.0.1:{port}", f"http://localhost:{port}", f"http://[::1]:{port}",
        }
        origin = self.headers.get("Origin")
        referer = self.headers.get("Referer")
        if origin:
            if origin not in allowed_origins:
                self.send_error_json(403, "Origin not allowed")
                return False
        elif referer:
            try:
                parts = urllib.parse.urlsplit(referer)
                referer_origin = f"{parts.scheme}://{parts.netloc}"
            except Exception:
                referer_origin = ""
            if referer_origin not in allowed_origins:
                self.send_error_json(403, "Referer not allowed")
                return False
        # else: neither header present -> non-browser client, allow through.

        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/api/") and path not in self._JSON_CT_EXEMPT_PATHS:
            ctype_base = self.headers.get("Content-Type", "").split(";")[0].strip().lower()
            if ctype_base not in ("application/json", "multipart/form-data"):
                self.send_error_json(403, "Content-Type must be application/json")
                return False

        return True

    def do_OPTIONS(self):
        if not self._security_guard():
            return
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self):
        if not self._security_guard():
            return
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
                if target_file.is_file() and target_file.is_relative_to(ASSETS_BASE_DIR.resolve()):
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
                if content_type and target_file.is_file() and target_file.is_relative_to(AUDIO_ASSETS_DIR.resolve()):
                    self.serve_file(target_file, content_type)
                else:
                    self.send_error_json(404, "Audio track not found")
            except Exception:
                self.send_error_json(404, "Audio track error")
        else:
            self.send_error_json(404, "Not Found")

    def do_POST(self):
        if not self._security_guard():
            return
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path.startswith("/api/"):
            ctype = self.headers.get("Content-Type", "")
            if ctype.startswith("multipart/form-data"):
                try:
                    fields, files = self._parse_multipart()
                except ValueError as exc:
                    self.send_error_json(400, str(exc))
                    return
                except Exception as exc:
                    self.send_error_json(400, f"Invalid multipart body: {exc}")
                    return
                self.handle_api_upload(path, fields, files)
                return

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

    def _parse_multipart(self):
        """Parse multipart/form-data into (fields, files) dicts.

        files[name] = {filename, data}. Rejects bodies over 80 MB.
        """
        from email import message_from_bytes
        from email.policy import default as email_policy

        length = int(self.headers.get("Content-Length", 0) or 0)
        if length > 80 * 1024 * 1024:
            raise ValueError("Upload too large (max 80 MB)")
        raw = self.rfile.read(length)
        header = f"Content-Type: {self.headers.get('Content-Type')}\r\nMIME-Version: 1.0\r\n\r\n"
        msg = message_from_bytes(header.encode("utf-8") + raw, policy=email_policy)
        fields: dict = {}
        files: dict = {}
        parts = list(msg.iter_parts()) if msg.is_multipart() else [msg]
        for part in parts:
            name = part.get_param("name", header="content-disposition")
            if not name:
                continue
            filename = part.get_param("filename", header="content-disposition")
            payload = part.get_payload(decode=True)
            if payload is None:
                payload = b""
            if filename:
                files[name] = {"filename": str(filename), "data": payload}
            else:
                fields[name] = payload.decode("utf-8", errors="replace")
        return fields, files

    def send_download(self, file_path: Path, filename: str, content_type: str = "application/octet-stream"):
        data = Path(file_path).read_bytes()
        self.send_response(200)
        self.send_cors_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

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

    def _require_active_session(self) -> bool:
        if not ACTIVE_SESSION:
            self.send_error_json(400, "No active session loaded")
            return False
        return True

    def _handle_memory_fact_mutation(self, payload: dict) -> None:
        if not self._require_active_session():
            return
        action = (payload.get("action") or "").strip().lower()
        db = ACTIVE_SESSION._db_path
        sid = ACTIVE_SESSION._save_id
        try:
            from axiom.facts import Fact, delete_fact, insert_facts, update_fact

            if action == "create":
                statement = (payload.get("statement") or "").strip()
                if not statement:
                    self.send_error_json(400, "Missing statement")
                    return
                turn = int(getattr(ACTIVE_SESSION, "_turn_id", 0) or 0)
                entities = payload.get("entities") or []
                if isinstance(entities, str):
                    entities = [e.strip() for e in entities.split(",") if e.strip()]
                ids = insert_facts(
                    db, sid, turn,
                    [Fact(
                        statement=statement,
                        fact_type=payload.get("fact_type") or "world",
                        entities=list(entities),
                    )],
                )
                self.send_json({"status": "success", "fact_id": ids[0] if ids else None,
                                "memory": build_memory_snapshot()})
            elif action == "update":
                fact_id = payload.get("fact_id")
                if fact_id is None:
                    self.send_error_json(400, "Missing fact_id")
                    return
                ok = update_fact(
                    db, sid, int(fact_id),
                    statement=payload.get("statement"),
                    fact_type=payload.get("fact_type"),
                    entities=payload.get("entities"),
                )
                if not ok:
                    self.send_error_json(404, "Fact not found or invalid update")
                    return
                self.send_json({"status": "success", "memory": build_memory_snapshot()})
            elif action == "delete":
                fact_id = payload.get("fact_id")
                if fact_id is None:
                    self.send_error_json(400, "Missing fact_id")
                    return
                if not delete_fact(db, sid, int(fact_id)):
                    self.send_error_json(404, "Fact not found")
                    return
                self.send_json({"status": "success", "memory": build_memory_snapshot()})
            else:
                self.send_error_json(400, "action must be create|update|delete")
        except Exception as exc:
            self.send_error_json(500, str(exc))

    def _handle_memory_belief_mutation(self, payload: dict) -> None:
        if not self._require_active_session():
            return
        action = (payload.get("action") or "").strip().lower()
        db = ACTIVE_SESSION._db_path
        sid = ACTIVE_SESSION._save_id
        try:
            from axiom.observations import delete_observation, update_observation

            if action == "update":
                oid = payload.get("observation_id")
                if oid is None:
                    self.send_error_json(400, "Missing observation_id")
                    return
                ok = update_observation(
                    db, sid, int(oid),
                    statement=payload.get("statement"),
                    subject=payload.get("subject"),
                )
                if not ok:
                    self.send_error_json(404, "Belief not found or invalid update")
                    return
                self.send_json({"status": "success", "memory": build_memory_snapshot()})
            elif action == "delete":
                oid = payload.get("observation_id")
                if oid is None:
                    self.send_error_json(400, "Missing observation_id")
                    return
                if not delete_observation(db, sid, int(oid)):
                    self.send_error_json(404, "Belief not found")
                    return
                self.send_json({"status": "success", "memory": build_memory_snapshot()})
            else:
                self.send_error_json(400, "action must be update|delete")
        except Exception as exc:
            self.send_error_json(500, str(exc))

    def _handle_memory_model_mutation(self, payload: dict) -> None:
        if not self._require_active_session():
            return
        action = (payload.get("action") or "").strip().lower()
        db = ACTIVE_SESSION._db_path
        sid = ACTIVE_SESSION._save_id
        try:
            from axiom.mental_models import delete_mental_model, update_mental_model

            if action == "update":
                mid = payload.get("model_id")
                if mid is None:
                    self.send_error_json(400, "Missing model_id")
                    return
                ok = update_mental_model(
                    db, sid, int(mid),
                    summary=payload.get("summary"),
                    subject=payload.get("subject"),
                )
                if not ok:
                    self.send_error_json(404, "Mental model not found or invalid update")
                    return
                self.send_json({"status": "success", "memory": build_memory_snapshot()})
            elif action == "delete":
                mid = payload.get("model_id")
                if mid is None:
                    self.send_error_json(400, "Missing model_id")
                    return
                if not delete_mental_model(db, sid, int(mid)):
                    self.send_error_json(404, "Mental model not found")
                    return
                self.send_json({"status": "success", "memory": build_memory_snapshot()})
            else:
                self.send_error_json(400, "action must be update|delete")
        except Exception as exc:
            self.send_error_json(500, str(exc))

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
                                # Same source as the Qt Hub (workers LoadSavesTask):
                                # separate ~/AxiomAI/saves/<universe>/ files + legacy
                                # rows still embedded in the universe db.
                                saves = list_saves(str(db_path))
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

        elif path == "/api/saves/state":
            uni_path = query_params.get("universe", [""])[0]
            save_id = query_params.get("save_id", [""])[0]
            db_hint = query_params.get("db", [""])[0]
            if not save_id:
                self.send_error_json(400, "Missing save_id")
                return
            db_path = Path(uni_path) if uni_path else None
            if db_path and db_path.is_dir():
                db_path = db_path / ".axiom-cache" / "universe.db"
            try:
                from axiom.saves import materialize_state
                from axiom.savestore import find_save_db
                from axiom.schema import migrate_schema
                db = None
                if db_hint:
                    hinted = Path(db_hint)
                    if hinted.is_file() and hinted.suffix == ".db":
                        db = str(hinted)
                if not db and db_path:
                    db = resolve_save_db(str(db_path), save_id)
                if not db:
                    db = find_save_db(save_id)
                if not db:
                    self.send_error_json(404, f"Save not found: {save_id}")
                    return
                migrate_schema(db)
                state = materialize_state(db, save_id)
                entities = []
                meta = state.get("entity_meta") or {}
                for eid, stats in (state.get("entities") or {}).items():
                    info = meta.get(eid) or {}
                    entities.append({
                        "entity_id": eid,
                        "name": info.get("name") or eid,
                        "entity_type": info.get("entity_type") or "npc",
                        "entity_role": info.get("entity_role") or info.get("entity_type") or "npc",
                        "stats": stats,
                    })
                # Stat catalog + links so the editor can hide unlinked stats.
                stat_defs = []
                types = []
                with get_connection(db) as conn:
                    applies: dict[str, list[str]] = {}
                    try:
                        for lr in conn.execute("SELECT stat_id, type_id FROM Stat_Type_Links;"):
                            applies.setdefault(lr["stat_id"], []).append(lr["type_id"])
                    except Exception:
                        applies = {}
                    for r in conn.execute(
                        "SELECT stat_id, name, value_type, description FROM Stat_Definitions;"
                    ):
                        stat_defs.append({
                            "stat_id": r["stat_id"],
                            "name": r["name"],
                            "value_type": r["value_type"],
                            "description": r["description"] or "",
                            "applies_to": applies.get(r["stat_id"], []),
                        })
                    try:
                        for t in conn.execute(
                            "SELECT type_id, name, role, is_builtin FROM Entity_Types "
                            "ORDER BY is_builtin DESC, name;"
                        ):
                            types.append({
                                "type_id": t["type_id"],
                                "name": t["name"],
                                "role": t["role"],
                                "is_builtin": bool(t["is_builtin"]),
                            })
                    except Exception:
                        types = []
                self.send_json({
                    "save": state.get("save") or {},
                    "point": state.get("point") or {},
                    "entities": entities,
                    "inventory": state.get("inventory") or [],
                    "session_lore": state.get("session_lore") or [],
                    "modifiers": state.get("modifiers") or [],
                    "stat_definitions": stat_defs,
                    "entity_types": types,
                    "toml": None,
                    "db_path": db,
                })
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
                from axiom.inventory import load_inventory_tree
                from axiom.schema import migrate_schema
                migrate_schema(ACTIVE_SESSION._db_path)
                tree = load_inventory_tree(ACTIVE_SESSION._db_path, ACTIVE_SESSION._save_id)
                names = {}
                with get_connection(ACTIVE_SESSION._db_path) as conn:
                    for r in conn.execute("SELECT entity_id, name FROM Entities;"):
                        names[r["entity_id"]] = r["name"]
                    try:
                        for r in conn.execute("SELECT location_id, name FROM Locations;"):
                            names[r["location_id"]] = r["name"]
                    except Exception:
                        pass
                self.send_json({"tree": tree, "names": names})
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/session/memory":
            if not ACTIVE_SESSION:
                self.send_error_json(400, "No active session loaded")
                return
            try:
                self.send_json(build_memory_snapshot())
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
                # Folder universes: compile/refresh cache if missing or stale
                # (same as Hub/play). Creator used to 404 after a cache wipe.
                try:
                    from axiom.dev import ensure_compiled
                    db_path = ensure_compiled(db_path)
                except Exception as exc:
                    self.send_error_json(500, f"Failed to compile universe: {exc}")
                    return
            elif not db_path.exists():
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
                    applies: dict[str, list[str]] = {}
                    try:
                        for lr in conn.execute("SELECT stat_id, type_id FROM Stat_Type_Links;"):
                            applies.setdefault(lr["stat_id"], []).append(lr["type_id"])
                    except Exception:
                        applies = {}
                    stats_rows = conn.execute("SELECT stat_id, name, value_type, description, parameters FROM Stat_Definitions;").fetchall()
                    for r in stats_rows:
                        data["stats"].append({
                            "stat_id": r["stat_id"],
                            "name": r["name"],
                            "value_type": r["value_type"],
                            "description": r["description"],
                            "parameters": json.loads(r["parameters"]) if r["parameters"] else {},
                            "applies_to": applies.get(r["stat_id"], []),
                        })
                    data["entity_types"] = []
                    try:
                        for t in conn.execute(
                            "SELECT type_id, name, role, description, is_builtin "
                            "FROM Entity_Types ORDER BY is_builtin DESC, name;"
                        ):
                            data["entity_types"].append({
                                "type_id": t["type_id"],
                                "name": t["name"],
                                "role": t["role"],
                                "description": t["description"] or "",
                                "is_builtin": bool(t["is_builtin"]),
                            })
                    except Exception:
                        data["entity_types"] = [
                            {"type_id": "player", "name": "Player", "role": "player", "is_builtin": True},
                            {"type_id": "npc", "name": "NPC", "role": "npc", "is_builtin": True},
                            {"type_id": "faction", "name": "Faction", "role": "faction", "is_builtin": True},
                            {"type_id": "world", "name": "World", "role": "world", "is_builtin": True},
                        ]
                        
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
                if target.exists() and target.resolve().is_relative_to(Path(uni_path).resolve()):
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

        elif path == "/api/session/timeline":
            if not ACTIVE_SESSION:
                self.send_error_json(400, "No active session loaded")
                return
            try:
                with get_connection(ACTIVE_SESSION._db_path) as conn:
                    rows = conn.execute(
                        "SELECT turn_id, in_game_time, description FROM Timeline "
                        "WHERE save_id = ? ORDER BY turn_id DESC;",
                        (ACTIVE_SESSION._save_id,),
                    ).fetchall()
                self.send_json([
                    {
                        "turn_id": r["turn_id"],
                        "in_game_time": r["in_game_time"],
                        "description": r["description"],
                    }
                    for r in rows
                ])
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/models":
            try:
                cfg = load_config()
                from axiom.config import build_llm_from_config
                llm = build_llm_from_config(cfg)
                list_models = getattr(llm, "list_models", None)
                models = list_models() if callable(list_models) else []
                self.send_json({"models": list(models or [])})
            except Exception as exc:
                logger.warning("Model listing failed: %s", exc)
                self.send_json({"models": [], "error": str(exc)})

        elif path == "/api/universe/params":
            uni_path = query_params.get("universe", [None])[0]
            db_path = _resolve_universe_db_path(uni_path)
            if not db_path:
                self.send_error_json(400, "Missing universe (and no active session)")
                return
            try:
                with get_connection(db_path) as conn:
                    rows = conn.execute(
                        "SELECT key, value FROM Universe_Meta "
                        "WHERE key IN ('llm_temperature', 'llm_top_p', 'llm_verbosity');"
                    ).fetchall()
                meta = {r["key"]: r["value"] for r in rows}
                self.send_json({
                    "llm_temperature": float(meta.get("llm_temperature") or 0.7),
                    "llm_top_p": float(meta.get("llm_top_p") or 1.0),
                    "llm_verbosity": meta.get("llm_verbosity") or resolve_session_verbosity(),
                })
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/universes/export":
            uni_path = query_params.get("universe", [None])[0]
            if not uni_path:
                self.send_error_json(400, "Missing 'universe' parameter")
                return
            self._export_universe_file(uni_path)

        elif path == "/api/saves/pack":
            uni_path = query_params.get("universe", [None])[0]
            save_id = query_params.get("save_id", [None])[0]
            if not uni_path or not save_id:
                self.send_error_json(400, "Missing parameters")
                return
            self._pack_save_file(uni_path, save_id)

        elif path == "/api/session/integrity":
            if not ACTIVE_SESSION:
                self.send_error_json(400, "No active session loaded")
                return
            try:
                from axiom.events import EventSourcer
                ok, mismatches = EventSourcer(ACTIVE_SESSION._db_path).validate_integrity(
                    ACTIVE_SESSION._save_id
                )
                self.send_json({"ok": bool(ok), "mismatches": mismatches or {}})
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
                # Mirror ui/setup_view.py: new games are separate save DBs under
                # ~/AxiomAI/saves/<universe>/, not rows inside the universe db.
                info = create_save(
                    str(db_path), player_name, difficulty, player_persona=player_persona
                )
                save_id = info["save_id"]
                save_db = info["db_path"]

                with get_connection(save_db) as conn:
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

                self.send_json({"status": "success", "save_id": save_id, "db_path": save_db})
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
                play_db = resolve_save_db(str(db_path), save_id) or str(db_path)  # module-level import
                new_save_id = fork_save(play_db, save_id, at_turn=int(turn_id), player_name=name)

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

        elif path == "/api/saves/state":
            uni_path = payload.get("universe_path") or payload.get("universe") or ""
            save_id = payload.get("save_id") or ""
            db_hint = payload.get("db_path") or payload.get("db") or ""
            if not save_id:
                self.send_error_json(400, "Missing save_id")
                return
            db_path = Path(uni_path) if uni_path else None
            if db_path and db_path.is_dir():
                db_path = db_path / ".axiom-cache" / "universe.db"
            try:
                from axiom.saves import apply_structured_state
                db = None
                if db_hint and Path(db_hint).is_file():
                    db = db_hint
                if not db and db_path:
                    db = resolve_save_db(str(db_path), save_id)
                if not db:
                    db = find_save_db(save_id)
                if not db:
                    self.send_error_json(404, f"Save not found: {save_id}")
                    return
                turn = apply_structured_state(db, save_id, payload)
                self.send_json({"status": "success", "turn": turn})
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/session/inventory/move":
            if not ACTIVE_SESSION:
                self.send_error_json(400, "No active session loaded")
                return
            try:
                from axiom.inventory import InventoryError, move_item, snapshot_present_inventory
                from axiom.schema import migrate_schema
                migrate_schema(ACTIVE_SESSION._db_path)
                instance_id = str(payload.get("instance_id") or "")
                dest_kind = str(payload.get("dest_holder_kind") or "")
                dest_id = str(payload.get("dest_holder_id") or "")
                if not instance_id or not dest_kind or not dest_id:
                    self.send_error_json(400, "Missing instance_id or destination")
                    return
                with get_connection(ACTIVE_SESSION._db_path) as conn:
                    move_item(
                        conn, ACTIVE_SESSION._save_id, instance_id, dest_kind, dest_id,
                        quantity=payload.get("quantity"),
                    )
                    snapshot_present_inventory(conn, ACTIVE_SESSION._save_id)  # TICKET-095
                    conn.commit()
                self.send_json({"status": "ok"})
            except InventoryError as exc:
                self.send_error_json(422, str(exc))
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
                # Resolve separate save DBs (and resync definition if the
                # universe source changed) — same as Qt's prepare_save_for_play.
                play_db = prepare_save_for_play(str(db_path), save_id)
                if not play_db:
                    self.send_error_json(404, f"Save not found: {save_id}")
                    return

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
                        play_db,
                        save_id,
                        llm=llm,
                        mode=difficulty,
                        hero_llm=hero_llm
                    )
                reset_living_memory_buffer()
                # If this save is already several turns past the last fact
                # extraction (common after a server restart), kick a catch-up
                # job immediately instead of waiting for N more live turns.
                try:
                    from axiom.config import load_config as _lc, memory_mode_is_living as _living
                    from axiom.living_memory import last_fact_turn as _lft
                    _cfg = _lc()
                    if _living(_cfg):
                        _interval = int(getattr(_cfg, "memory_fact_interval", 0) or 0)
                        _turn = int(getattr(ACTIVE_SESSION, "_turn_id", 0) or 0)
                        _after = _lft(play_db, save_id)
                        if _interval > 0 and (_turn - _after) >= _interval:
                            _spawn_living_memory_job(_cfg, force_catchup=True)
                except Exception:
                    logger.exception("Living-memory session catch-up failed to start")

                self.send_json(build_session_snapshot())
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/session/turn":
            player_input = payload.get("player_input", "").strip()
            intents = payload.get("intents", None)
            snapshot, err_status, err_msg = execute_session_turn(
                player_input=player_input, intents=intents
            )
            if err_status:
                self.send_error_json(err_status, err_msg)
                return
            self.send_json(snapshot)

        elif path == "/api/session/turn/stream":
            player_input = payload.get("player_input", "").strip()
            intents = payload.get("intents", None)
            self._stream_session_turn(player_input=player_input, intents=intents)

        elif path == "/api/session/cancel":
            n = request_turn_cancel()
            self.send_json({"cancelled": n > 0, "count": n})

        elif path == "/api/session/verbosity":
            if not ACTIVE_SESSION:
                self.send_error_json(400, "No active session loaded")
                return
            level = (payload.get("level") or "").strip().lower()
            if level not in ("short", "balanced", "talkative"):
                self.send_error_json(400, "level must be short, balanced, or talkative")
                return
            try:
                with get_connection(ACTIVE_SESSION._db_path) as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO Universe_Meta (key, value) VALUES ('llm_verbosity', ?);",
                        (level,),
                    )
                    conn.commit()
                self.send_json({"status": "success", "level": level})
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/universe/params":
            uni_path = payload.get("universe_path") or payload.get("universe")
            db_path = _resolve_universe_db_path(uni_path)
            if not db_path:
                self.send_error_json(400, "Missing universe (and no active session)")
                return
            try:
                temp = payload.get("llm_temperature")
                top_p = payload.get("llm_top_p")
                with get_connection(db_path) as conn:
                    if temp is not None:
                        conn.execute(
                            "INSERT OR REPLACE INTO Universe_Meta (key, value) VALUES ('llm_temperature', ?);",
                            (str(float(temp)),),
                        )
                    if top_p is not None:
                        conn.execute(
                            "INSERT OR REPLACE INTO Universe_Meta (key, value) VALUES ('llm_top_p', ?);",
                            (str(float(top_p)),),
                        )
                    conn.commit()
                self.send_json({"status": "success"})
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/session/canonize":
            if not ACTIVE_SESSION:
                self.send_error_json(400, "No active session loaded")
                return
            preview = payload.get("preview", True)
            text = (payload.get("text") or "").strip()
            if not text:
                text = recent_narrative_text()
            if not text:
                self.send_error_json(400, "No narrative to canonize")
                return
            try:
                from axiom.canonize import canonize_story
                from axiom.backends.base import GenerationCancelled
                llm = getattr(ACTIVE_SESSION, "_llm", None)
                if llm is not None:
                    llm.cancel_event = TURN_CANCEL
                    TURN_CANCEL.clear()
                info = canonize_story(
                    ACTIVE_SESSION._db_path, text, preview=bool(preview), llm=None
                )
                LAST_CANONIZE_PREVIEW.clear()
                if info.get("staged_dir"):
                    LAST_CANONIZE_PREVIEW.update(
                        staged_dir=info.get("staged_dir"),
                        src_dir=info.get("src_dir") or "",
                        universe_db=info.get("universe_db") or "",
                        save_db=ACTIVE_SESSION._db_path,
                    )
                diffs = info.get("diffs") or []
                diff_text = "\n\n".join(
                    d.get("diff", "") if isinstance(d, dict) else str(d) for d in diffs
                )
                self.send_json({
                    "applied": bool(info.get("applied")),
                    "diffs": diffs,
                    "diff": diff_text,
                    "staged_dir": info.get("staged_dir") or "",
                    "src_dir": info.get("src_dir") or "",
                    "universe_db": info.get("universe_db") or "",
                    "counts": info.get("counts") or {},
                    "entities": info.get("entities") or [],
                    "lore_entries": info.get("lore_entries") or [],
                    "scope": info.get("scope") or "save",
                })
            except GenerationCancelled as exc:
                self.send_error_json(409, str(exc))
            except ValueError as exc:
                self.send_error_json(422, str(exc))
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/session/canonize/apply":
            if not ACTIVE_SESSION:
                self.send_error_json(400, "No active session loaded")
                return
            lore = payload.get("lore_entries")
            entities = payload.get("entities")
            scope = (payload.get("scope") or "save").strip().lower()
            if lore is not None or entities is not None:
                try:
                    from axiom.canonize import apply_canonize_selection, _resolve_universe_db
                    universe_db = ""
                    if scope == "world":
                        universe_db = _resolve_universe_db(ACTIVE_SESSION._db_path)
                    counts = apply_canonize_selection(
                        save_db=ACTIVE_SESSION._db_path,
                        universe_db=universe_db,
                        entities=entities or [],
                        lore=lore or [],
                        scope=scope,
                    )
                    self.send_json({"status": "success", "applied": True, "counts": counts, "scope": counts.get("scope", scope)})
                except ValueError as exc:
                    self.send_error_json(422, str(exc))
                except Exception as exc:
                    self.send_error_json(500, str(exc))
                return
            # Paths come ONLY from the server-side preview of this session;
            # any staged_dir/src_dir/universe_db in the payload is ignored.
            staged = dict(LAST_CANONIZE_PREVIEW)
            staged_dir = staged.get("staged_dir") or ""
            src_dir = staged.get("src_dir") or ""
            universe_db = staged.get("universe_db") or ""
            if (not staged_dir or not src_dir or not universe_db
                    or staged.get("save_db") != ACTIVE_SESSION._db_path):
                self.send_error_json(400, "Missing selection or no pending canonize preview")
                return
            try:
                from axiom.canonize import apply_canonize_preview
                LAST_CANONIZE_PREVIEW.clear()
                apply_canonize_preview(
                    staged_dir, src_dir, universe_db, save_db=ACTIVE_SESSION._db_path
                )
                self.send_json({"status": "success", "applied": True, "scope": "world"})
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
                        verbosity_level=resolve_session_verbosity(),
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
                        res = ACTIVE_SESSION.take_turn(
                            new_text, verbosity_level=resolve_session_verbosity()
                        )
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

        elif path == "/api/session/memory/fact":
            self._handle_memory_fact_mutation(payload)
        elif path == "/api/session/memory/belief":
            self._handle_memory_belief_mutation(payload)
        elif path == "/api/session/memory/model":
            self._handle_memory_model_mutation(payload)
        elif path == "/api/session/memory/extract":
            # Manual "extract now" / catch-up from Event_Log since last facts.
            if not ACTIVE_SESSION:
                self.send_error_json(400, "No active session loaded")
                return
            try:
                result = run_living_memory_extract_now(force_catchup=True)
                self.send_json(result)
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/creator/infer-stats":
            # Classify which stats are temporary and on what basis.
            # Does not persist — Creator applies the returned parameters, then Save.
            stats = payload.get("stats") or []
            hint = str(payload.get("world_hint") or "")
            try:
                from axiom.config import build_llm_from_config, resolve_extraction_model
                from axiom.stat_dynamics import infer_stat_dynamics
                cfg = load_config()
                llm = build_llm_from_config(cfg, model_override=resolve_extraction_model(cfg))
                merged = infer_stat_dynamics(stats, llm, world_hint=hint)
                self.send_json({"stats": merged})
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
                from axiom.schema import ENTITY_ROLES, ensure_entity_type, migrate_schema
                migrate_schema(str(db_path))
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
                        
                    # Sync types then stats (FK order)
                    for t in payload.get("entity_types") or []:
                        tid = str(t.get("type_id") or "").strip()
                        if not tid:
                            continue
                        role = str(t.get("role") or "npc").strip().lower()
                        if role not in ENTITY_ROLES:
                            role = "npc"
                        ensure_entity_type(
                            conn, tid,
                            name=str(t.get("name") or tid),
                            role=role,
                            description=str(t.get("description") or ""),
                            is_builtin=1 if t.get("is_builtin") else 0,
                        )

                    conn.execute("DELETE FROM Stat_Type_Links;")
                    conn.execute("DELETE FROM Stat_Definitions;")
                    from axiom.stat_dynamics import fold_into_parameters
                    for s in payload.get("stats", []):
                        params = fold_into_parameters(s)
                        conn.execute("INSERT INTO Stat_Definitions (stat_id, name, value_type, description, parameters) VALUES (?, ?, ?, ?, ?);",
                                     (s["stat_id"], s["name"], s["value_type"], s["description"], json.dumps(params)))
                        for tid in s.get("applies_to") or []:
                            ensure_entity_type(conn, str(tid))
                            conn.execute(
                                "INSERT OR IGNORE INTO Stat_Type_Links (stat_id, type_id) VALUES (?, ?);",
                                (s["stat_id"], str(tid)),
                            )
                        
                    # Sync Entities
                    conn.execute("DELETE FROM Entities;")
                    conn.execute("DELETE FROM Entity_Stats;")
                    for ent in payload.get("entities", []):
                        ensure_entity_type(conn, ent.get("entity_type") or "npc")
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
                if target.resolve().is_relative_to(Path(uni_path).resolve()):
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

        elif path == "/api/saves/duplicate":
            uni_path = payload.get("universe_path", "")
            save_id = payload.get("save_id", "")
            name = payload.get("name")
            if not uni_path or not save_id:
                self.send_error_json(400, "Missing parameters")
                return
            db_path = Path(uni_path)
            if db_path.is_dir():
                db_path = db_path / ".axiom-cache" / "universe.db"
            try:
                from axiom.savestore import duplicate_save
                info = duplicate_save(str(db_path), save_id, player_name=name)
                self.send_json({"status": "success", "save_id": info["save_id"], "db_path": info["db_path"]})
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/saves/rename":
            uni_path = payload.get("universe_path", "")
            save_id = payload.get("save_id", "")
            name = (payload.get("name") or "").strip()
            if not uni_path or not save_id or not name:
                self.send_error_json(400, "Missing parameters")
                return
            db_path = Path(uni_path)
            if db_path.is_dir():
                db_path = db_path / ".axiom-cache" / "universe.db"
            try:
                from axiom.savestore import rename_save
                ok = rename_save(str(db_path), save_id, name)
                if ok:
                    self.send_json({"status": "success", "name": name})
                else:
                    self.send_error_json(404, "Save not found")
            except Exception as exc:
                self.send_error_json(500, str(exc))

        elif path == "/api/saves/unpack":
            # JSON path fallback (tests). Browser uses multipart handle_api_upload.
            archive = payload.get("path", "").strip()
            uni_path = payload.get("universe_path", "")
            force = bool(payload.get("force"))
            if not archive or not uni_path:
                self.send_error_json(400, "Missing path or universe_path")
                return
            self._unpack_save_archive(archive, uni_path, force)

        elif path == "/api/universes/export":
            uni_path = payload.get("path") or payload.get("universe_path") or ""
            if not uni_path:
                self.send_error_json(400, "Missing path")
                return
            self._export_universe_file(uni_path)

        else:
            self.send_error_json(404, "Not Found")

    def _stream_session_turn(self, *, player_input: str, intents) -> None:
        """SSE turn: status / token / done / error / cancelled events."""

        def emit(event: str, data) -> None:
            payload = json.dumps(data, ensure_ascii=False)
            self.wfile.write(f"event: {event}\ndata: {payload}\n\n".encode("utf-8"))
            try:
                self.wfile.flush()
            except BrokenPipeError:
                pass

        self.send_response(200)
        self.send_cors_headers()
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        snapshot, err_status, err_msg = execute_session_turn(
            player_input=player_input,
            intents=intents,
            on_token=lambda tok: emit("token", {"text": tok}),
            on_status=lambda msg: emit("status", {"message": msg}),
        )
        if err_status:
            event = "cancelled" if err_status == 409 else "error"
            emit(event, {"error": err_msg, "status": err_status})
            return
        emit("done", snapshot)

    def handle_api_upload(self, path: str, fields: dict, files: dict) -> None:
        """Multipart uploads for universe/save import (browser file pickers)."""
        import tempfile

        def _write_upload(key: str, allowed: tuple[str, ...]) -> Path:
            item = files.get(key) or files.get("file")
            if not item:
                raise ValueError("Missing file")
            name = Path(item["filename"]).name
            suffix = Path(name).suffix.lower()
            if suffix not in allowed:
                raise ValueError(f"Unsupported file type: {suffix or '(none)'}")
            tmp = Path(tempfile.mkdtemp(prefix="axiom_upload_")) / name
            tmp.write_bytes(item["data"])
            return tmp

        if path == "/api/universes/import":
            try:
                tmp = _write_upload("file", (".axiom",))
            except ValueError as exc:
                self.send_error_json(400, str(exc))
                return
            try:
                from axiom.package import unpack_universe
                dest_folder = UNIVERSES_DIR / tmp.stem
                unpack_universe(str(tmp), str(dest_folder))
                self.send_json({"status": "success", "path": str(dest_folder)})
            except Exception as exc:
                self.send_error_json(500, str(exc))
            finally:
                import shutil
                shutil.rmtree(tmp.parent, ignore_errors=True)

        elif path == "/api/universes/import-st":
            try:
                tmp = _write_upload("file", (".png", ".json", ".webp"))
            except ValueError as exc:
                self.send_error_json(400, str(exc))
                return
            try:
                # Reuse the JSON path handler by pointing it at the temp file.
                self.handle_api_post(path, {"path": str(tmp)})
            finally:
                import shutil
                shutil.rmtree(tmp.parent, ignore_errors=True)

        elif path == "/api/saves/unpack":
            uni_path = fields.get("universe_path") or fields.get("universe") or ""
            force = (fields.get("force") or "").lower() in ("1", "true", "yes")
            if not uni_path:
                self.send_error_json(400, "Missing universe_path")
                return
            try:
                tmp = _write_upload("file", (".axiomsave", ".zip"))
            except ValueError as exc:
                self.send_error_json(400, str(exc))
                return
            try:
                self._unpack_save_archive(str(tmp), uni_path, force)
            finally:
                import shutil
                shutil.rmtree(tmp.parent, ignore_errors=True)

        else:
            self.send_error_json(404, "Not Found")

    def _export_universe_file(self, uni_path: str) -> None:
        import tempfile
        from axiom.package import pack_universe, export_db_to_axiom, PackageError

        target = Path(uni_path)
        if not target.exists():
            self.send_error_json(400, "Universe path does not exist")
            return
        tmp = Path(tempfile.mkstemp(suffix=".axiom")[1])
        try:
            if target.is_dir():
                pack_universe(target, tmp)
                fname = f"{target.name}.axiom"
            else:
                export_db_to_axiom(target, tmp)
                fname = f"{target.stem}.axiom"
            self.send_download(tmp, fname)
        except PackageError as exc:
            self.send_error_json(400, str(exc))
        except Exception as exc:
            self.send_error_json(500, str(exc))
        finally:
            tmp.unlink(missing_ok=True)

    def _pack_save_file(self, uni_path: str, save_id: str) -> None:
        import tempfile
        from axiom.savestore import pack_save, SaveStoreError

        db_path = Path(uni_path)
        if db_path.is_dir():
            db_path = db_path / ".axiom-cache" / "universe.db"
        tmp = Path(tempfile.mkstemp(suffix=".axiomsave")[1])
        try:
            pack_save(str(db_path), save_id, tmp)
            self.send_download(tmp, f"{save_id[:8]}.axiomsave")
        except SaveStoreError as exc:
            self.send_error_json(400, str(exc))
        except Exception as exc:
            self.send_error_json(500, str(exc))
        finally:
            tmp.unlink(missing_ok=True)

    def _unpack_save_archive(self, archive: str, uni_path: str, force: bool) -> None:
        from axiom.savestore import unpack_save, SaveStoreError

        db_path = Path(uni_path)
        if db_path.is_dir():
            db_path = db_path / ".axiom-cache" / "universe.db"
        try:
            info = unpack_save(archive, str(db_path), force=force)
            self.send_json({"status": "success", "save_id": info["save_id"], "db_path": info["db_path"]})
        except SaveStoreError as exc:
            msg = str(exc)
            if "Use force" in msg or "force" in msg.lower():
                self.send_json({"needs_force": True, "error": msg}, status=409)
            else:
                self.send_error_json(400, msg)
        except Exception as exc:
            self.send_error_json(500, str(exc))

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


def reset_living_memory_buffer() -> None:
    """Clear the pending narrative buffer (e.g. on new session / hardcore wipe)."""
    global _FACT_PENDING, _FACT_TURN_COUNTER
    with _FACT_WORKER_LOCK:
        _FACT_PENDING = []
        _FACT_TURN_COUNTER = 0


def schedule_living_memory_after_turn(narrative_text: str) -> None:
    """Buffer turn prose; kick background distillation every N turns (living mode).

    The interval counter is session-local, but we also fire when the **save** is
    behind: if ``current_turn - last_fact_turn >= interval``, catch up from
    Event_Log. That way a restart/re-open of a turn-9 save does not require five
    *more* live turns before the first automatic extract.
    """
    global _FACT_PENDING, _FACT_TURN_COUNTER
    from axiom.config import load_config, memory_mode_is_living
    from axiom.living_memory import last_fact_turn

    text = (narrative_text or "").strip()
    if not text or ACTIVE_SESSION is None:
        return
    cfg = load_config()
    if not memory_mode_is_living(cfg):
        return
    interval = int(getattr(cfg, "memory_fact_interval", 0) or 0)
    with _FACT_WORKER_LOCK:
        _FACT_PENDING.append(text)
        _FACT_TURN_COUNTER += 1
        counter_hit = interval > 0 and _FACT_TURN_COUNTER >= interval

    if counter_hit:
        # force_catchup=True: drain Event_Log since last_fact_turn, not only
        # the RAM buffer (which is wiped on every server restart / session load).
        _spawn_living_memory_job(cfg, force_catchup=True)


def run_living_memory_extract_now(*, force_catchup: bool = False) -> dict:
    """Synchronous extract for the Memory UI button (or API).

    When the in-memory buffer is empty (typical after playing many web turns
    without distillation), rebuilds a narrative slice from Event_Log since the
    last fact turn so catch-up is possible. If narrative is already distilled
    but beliefs are empty, runs consolidation on stored facts.
    """
    from axiom.config import (
        build_llm_from_config,
        load_config,
        memory_beliefs_active,
        memory_mental_models_active,
        memory_mode_is_living,
    )
    from axiom.living_memory import (
        consolidate_facts_to_beliefs,
        distil_turns_to_memory,
        last_fact_turn,
        recent_narratives_since,
    )
    from axiom.observations import get_observations

    if ACTIVE_SESSION is None:
        return {"status": "error", "error": "No active session", "facts_stored": 0}

    cfg = load_config()
    if not memory_mode_is_living(cfg):
        return {
            "status": "skipped",
            "error": "Living memory is off (Settings → Memory mode).",
            "facts_stored": 0,
            "memory": build_memory_snapshot(),
        }

    db = ACTIVE_SESSION._db_path
    sid = ACTIVE_SESSION._save_id
    turn = int(getattr(ACTIVE_SESSION, "_turn_id", 0) or 0)

    global _FACT_PENDING, _FACT_TURN_COUNTER
    with _FACT_WORKER_LOCK:
        pending = list(_FACT_PENDING)
        _FACT_PENDING = []
        _FACT_TURN_COUNTER = 0

    # Prefer durable Event_Log catch-up (per-turn) over a single glued blob.
    turn_pairs: list[tuple[int, str]] = []
    if force_catchup:
        after = last_fact_turn(db, sid)
        turn_pairs = recent_narratives_since(
            db, sid, after_turn_id=after, up_to_turn_id=turn
        )
        # Cap: one click should not distill a 100-turn novel at once.
        turn_pairs = turn_pairs[-8:]
    if not turn_pairs and pending:
        # RAM buffer only (no turn ids) — treat as a single synthetic slice.
        turn_pairs = [(turn, "\n\n".join(pending))]

    from axiom.config import resolve_memory_fact_model
    override = resolve_memory_fact_model(cfg)
    try:
        llm = build_llm_from_config(cfg, model_override=override)
    except Exception as exc:
        return {
            "status": "error",
            "error": f"Could not build memory LLM: {exc}",
            "facts_stored": 0,
        }

    try:
        if turn_pairs:
            result = distil_turns_to_memory(
                llm,
                db,
                sid,
                turn_pairs,
                consolidate_beliefs=memory_beliefs_active(cfg),
                refresh_mental_models=memory_mental_models_active(cfg),
                raise_on_error=True,
                max_turns=8,
            )
        elif force_catchup and memory_beliefs_active(cfg):
            # Narrative already fact-distilled; still try beliefs/profiles.
            existing_beliefs = get_observations(db, sid, max_turn_id=turn)
            if existing_beliefs:
                return {
                    "status": "ok",
                    "facts_stored": 0,
                    "beliefs_touched": 0,
                    "models_refreshed": 0,
                    "message": "Nothing new to distil (facts and beliefs already up to date).",
                    "memory": build_memory_snapshot(),
                }
            result = consolidate_facts_to_beliefs(
                llm,
                db,
                sid,
                turn,
                refresh_mental_models=memory_mental_models_active(cfg),
                raise_on_error=True,
            )
        else:
            return {
                "status": "ok",
                "facts_stored": 0,
                "message": "Nothing new to distil.",
                "memory": build_memory_snapshot(),
            }
    except Exception as exc:
        logger.exception("Living memory extract failed")
        return {
            "status": "error",
            "error": f"Memory extract failed: {exc}",
            "facts_stored": 0,
            "memory": build_memory_snapshot(),
        }

    if isinstance(result, dict):
        n_facts = int(result.get("facts_stored", 0) or 0)
        n_beliefs = int(result.get("beliefs_touched", 0) or 0)
        n_models = int(result.get("models_refreshed", 0) or 0)
    else:
        n_facts, n_beliefs, n_models = int(result or 0), 0, 0

    parts = []
    if n_facts:
        parts.append(f"{n_facts} fact(s)")
    if n_beliefs:
        parts.append(f"{n_beliefs} belief update(s)")
    if n_models:
        parts.append(f"{n_models} profile(s)")
    if parts:
        message = "Stored " + ", ".join(parts) + "."
    else:
        message = (
            "Model returned no new facts/beliefs for this slice "
            "(try more turns, or check extraction model)."
        )
    return {
        "status": "ok",
        "facts_stored": n_facts,
        "beliefs_touched": n_beliefs,
        "models_refreshed": n_models,
        "message": message,
        "memory": build_memory_snapshot(),
    }


def _spawn_living_memory_job(cfg, *, force_catchup: bool) -> None:
    """Fire-and-forget background distillation (does not block /api/session/turn)."""
    global _FACT_WORKER_BUSY, _FACT_PENDING, _FACT_TURN_COUNTER

    with _FACT_WORKER_LOCK:
        if _FACT_WORKER_BUSY:
            # Keep the counter so the next free turn can still trigger; do not
            # wipe progress while a job is already running.
            return
        pending = list(_FACT_PENDING)
        _FACT_PENDING = []
        _FACT_TURN_COUNTER = 0
        _FACT_WORKER_BUSY = True

    def _job() -> None:
        global _FACT_WORKER_BUSY
        try:
            if ACTIVE_SESSION is None:
                return
            from axiom.config import (
                build_llm_from_config,
                memory_beliefs_active,
                memory_mental_models_active,
            )
            from axiom.living_memory import (
                distil_narrative_to_memory,
                last_fact_turn,
                recent_narratives_since,
            )

            db = ACTIVE_SESSION._db_path
            sid = ACTIVE_SESSION._save_id
            turn = int(getattr(ACTIVE_SESSION, "_turn_id", 0) or 0)

            # Prefer per-turn Event_Log catch-up (survives restarts; avoids
            # one giant prompt that reasoning models empty-out on).
            turn_pairs: list[tuple[int, str]] = []
            try:
                after = last_fact_turn(db, sid)
                pairs = recent_narratives_since(
                    db, sid, after_turn_id=after, up_to_turn_id=turn
                )
                # Auto job: small window so it finishes between turns.
                turn_pairs = pairs[-6:]
            except Exception:
                logger.exception("Living-memory Event_Log catch-up failed")

            if not turn_pairs and pending:
                turn_pairs = [(turn, "\n\n".join(pending))]

            if not turn_pairs:
                return
            from axiom.config import resolve_memory_fact_model
            override = resolve_memory_fact_model(cfg)
            try:
                llm = build_llm_from_config(cfg, model_override=override)
            except Exception:
                logger.exception("Living-memory LLM build failed")
                return
            from axiom.living_memory import distil_turns_to_memory

            result = distil_turns_to_memory(
                llm,
                db,
                sid,
                turn_pairs,
                consolidate_beliefs=memory_beliefs_active(cfg),
                refresh_mental_models=memory_mental_models_active(cfg),
                max_turns=6,
            )
            logger.info(
                "Living-memory job done: facts=%s beliefs=%s models=%s",
                result.get("facts_stored"),
                result.get("beliefs_touched"),
                result.get("models_refreshed"),
            )
        except Exception:
            logger.exception("Background living-memory job failed")
        finally:
            with _FACT_WORKER_LOCK:
                _FACT_WORKER_BUSY = False

    threading.Thread(target=_job, daemon=True).start()


def build_memory_snapshot() -> dict:
    """Facts + beliefs + mental models for the active session (web Memory UI)."""
    if ACTIVE_SESSION is None:
        raise RuntimeError("No active session")
    db = ACTIVE_SESSION._db_path
    sid = ACTIVE_SESSION._save_id
    turn = int(getattr(ACTIVE_SESSION, "_turn_id", 0) or 0)

    from axiom.facts import get_facts
    from axiom.mental_models import get_mental_models
    from axiom.observations import get_observations

    facts = get_facts(db, sid, max_turn_id=turn)
    beliefs = get_observations(db, sid, max_turn_id=turn)
    models = get_mental_models(db, sid, max_turn_id=turn)

    return {
        "turn_id": turn,
        "facts": [
            {
                "fact_id": f.fact_id,
                "turn_id": f.turn_id,
                "fact_type": f.fact_type,
                "statement": f.statement,
                "entities": list(f.entities or []),
                "who": f.who or "",
            }
            for f in facts
        ],
        "beliefs": [
            {
                "observation_id": o.observation_id,
                "subject": o.subject or "",
                "statement": o.statement,
                "proof_count": o.proof_count,
                "updated_turn_id": o.updated_turn_id,
                "trend": o.trend(turn),
            }
            for o in beliefs
        ],
        "mental_models": [
            {
                "model_id": m.model_id,
                "subject": m.subject or "",
                "summary": m.summary,
                "updated_turn_id": m.updated_turn_id,
                "stale": m.stale,
            }
            for m in models
        ],
    }


def _resolve_universe_db_path(uni_path: str | None) -> str | None:
    """Compiled universe.db for a folder/flat path, or the active session db."""
    if uni_path:
        db_path = Path(uni_path)
        if db_path.is_dir():
            db_path = db_path / ".axiom-cache" / "universe.db"
        if db_path.exists():
            return str(db_path)
        return None
    if ACTIVE_SESSION is not None:
        return ACTIVE_SESSION._db_path
    return None


def resolve_player_entity_id(session=None) -> str:
    """Real player entity id (never assume the literal key 'player').

    Myria-style universes use a named entity (e.g. ysolde_brask), not the
    literal key 'player'. Location chips and take_turn intents must target that id.
    """
    sess = session or ACTIVE_SESSION
    if sess is None:
        return "player"
    try:
        with get_connection(sess._db_path) as conn:
            row = conn.execute(
                "SELECT entity_id FROM Entities "
                "WHERE COALESCE(entity_role, entity_type) = 'player' AND is_active = 1 LIMIT 1;"
            ).fetchone()
        if row and row["entity_id"]:
            return row["entity_id"]
    except Exception:
        logger.warning("Could not resolve player entity id", exc_info=True)
    return "player"


def recent_narrative_text(max_entries: int = 8) -> str:
    """Last N narrator turns, for canonize. Mirrors tabletop_view._recent_narrative."""
    if ACTIVE_SESSION is None:
        return ""
    try:
        with get_connection(ACTIVE_SESSION._db_path) as conn:
            rows = conn.execute(
                "SELECT payload FROM Event_Log "
                "WHERE save_id = ? AND event_type = 'narrative_text' "
                "ORDER BY event_id DESC LIMIT ?;",
                (ACTIVE_SESSION._save_id, max_entries),
            ).fetchall()
    except Exception:
        return ""
    chunks: list[str] = []
    for r in reversed(rows):
        try:
            p = json.loads(r["payload"])
        except Exception:
            continue
        if isinstance(p, dict) and isinstance(p.get("variants"), list):
            idx = int(p.get("active") or 0)
            variants = p["variants"]
            text = variants[idx] if 0 <= idx < len(variants) else (variants[0] if variants else "")
        elif isinstance(p, dict):
            text = p.get("text") or ""
        else:
            text = str(p or "")
        if text.strip():
            chunks.append(text.strip())
    return "\n\n".join(chunks)


def request_turn_cancel() -> int:
    """Arm the cooperative cancel flag. Returns 1 if a turn is in flight."""
    TURN_CANCEL.set()
    with TURN_BUSY_LOCK:
        return 1 if TURN_BUSY else 0


def execute_session_turn(
    *,
    player_input: str = "",
    intents=None,
    on_token=None,
    on_status=None,
):
    """Run one Session.take_turn / take_turn_multiplayer.

    Returns (snapshot_or_None, err_status_or_None, err_msg_or_None).
    """
    global TURN_BUSY
    from axiom.backends.base import GenerationCancelled

    if not ACTIVE_SESSION:
        return None, 400, "No active session loaded"
    if not (player_input or "").strip() and not intents:
        return None, 400, "Missing input text or intents"

    with TURN_BUSY_LOCK:
        if TURN_BUSY:
            return None, 409, "A turn is already in progress"
        TURN_BUSY = True
    TURN_CANCEL.clear()

    try:
        verbosity = resolve_session_verbosity()
        player_id = resolve_player_entity_id(ACTIVE_SESSION)
        llm = getattr(ACTIVE_SESSION, "_llm", None)
        hero = getattr(ACTIVE_SESSION, "_hero_llm", None)
        if llm is not None:
            llm.cancel_event = TURN_CANCEL
        if hero is not None:
            hero.cancel_event = TURN_CANCEL

        with ACTIVE_SESSION_LOCK:
            if intents and isinstance(intents, dict):
                res = ACTIVE_SESSION.take_turn_multiplayer(
                    intents,
                    verbosity_level=verbosity,
                    on_token=on_token,
                    on_status=on_status,
                )
            else:
                res = ACTIVE_SESSION.take_turn(
                    player_input,
                    player_id=player_id,
                    verbosity_level=verbosity,
                    on_token=on_token,
                    on_status=on_status,
                )

        snapshot = build_session_snapshot()
        snapshot["narrative_text"] = res.narrative_text
        snapshot["image_path"] = res.image_path.name if res.image_path else None
        snapshot["game_state_tag"] = getattr(res, "game_state_tag", "exploration")
        snapshot["hardcore_death"] = (
            ACTIVE_SESSION._mode == "Hardcore" and is_player_death_triggered(res)
        )
        rejected = getattr(res, "rejected_changes", None) or []
        snapshot["rejected_changes"] = rejected
        snapshot["inventory_changes"] = getattr(res, "inventory_changes", None) or []
        snapshot["lore_hits"] = getattr(res, "lore_hits", None) or []
        try:
            ACTIVE_SESSION._last_lore_hits = snapshot["lore_hits"]
        except Exception:
            pass
        schedule_living_memory_after_turn(getattr(res, "narrative_text", "") or "")
        return snapshot, None, None
    except GenerationCancelled as exc:
        return None, 409, str(exc) or "Generation cancelled by user."
    except Exception as exc:
        logger.exception("Session turn failed")
        return None, 500, str(exc)
    finally:
        with TURN_BUSY_LOCK:
            TURN_BUSY = False
        if ACTIVE_SESSION is not None:
            llm = getattr(ACTIVE_SESSION, "_llm", None)
            hero = getattr(ACTIVE_SESSION, "_hero_llm", None)
            if llm is not None:
                llm.cancel_event = None
            if hero is not None:
                hero.cancel_event = None


def resolve_session_verbosity() -> str:
    """Narrator verbosity for web turns: universe meta if set, else Settings.

    Mirrors the desktop tabletop: a stored ``llm_verbosity`` on the active
    universe wins; otherwise ``AppConfig.default_verbosity`` from settings.
    """
    cfg_default = get_default_verbosity()
    if ACTIVE_SESSION is None:
        return cfg_default
    try:
        with get_connection(ACTIVE_SESSION._db_path) as conn:
            row = conn.execute(
                "SELECT value FROM Universe_Meta WHERE key='llm_verbosity';"
            ).fetchone()
        stored = (row["value"] if row else "") or ""
        stored = stored.strip()
        if stored:
            from core.localization import canonical_verbosity
            return canonical_verbosity(stored, default=cfg_default)
    except Exception:
        pass
    return cfg_default


def build_session_snapshot(include_history: bool = True) -> dict:
    """Common response payload shared by every /api/session/* endpoint that
    hands the client a fresh view of the active session (start, turn, rewind,
    variant switch, edit, regenerate): stats, location, travel options,
    formatted time, and (optionally) the full chat history.
    """
    from axiom.db_helpers import load_active_entities, load_definition_stats

    stats = ACTIVE_SESSION.current_stats()
    base = load_definition_stats(ACTIVE_SESSION._db_path)
    for eid, base_stats in base.items():
        merged = dict(base_stats)
        merged.update(stats.get(eid, {}))
        stats[eid] = merged
    modifiers: list[dict] = []
    try:
        from axiom.events import resolve_stat_key
        from axiom.textfmt import fmt_num
        with get_connection(ACTIVE_SESSION._db_path) as conn:
            for r in conn.execute(
                "SELECT entity_id, stat_key, delta, minutes_remaining "
                "FROM Active_Modifiers WHERE save_id = ? "
                "ORDER BY entity_id, stat_key;",
                (ACTIVE_SESSION._save_id,),
            ):
                modifiers.append({
                    "entity_id": r["entity_id"],
                    "stat_key": r["stat_key"],
                    "delta": r["delta"],
                    "minutes_remaining": r["minutes_remaining"],
                })
        for mod in modifiers:
            eid = mod["entity_id"]
            if eid not in stats:
                continue
            key = resolve_stat_key(mod["stat_key"], stats[eid])
            try:
                current = float(stats[eid].get(key, "0"))
                stats[eid][key] = fmt_num(current + float(mod["delta"]))
            except (TypeError, ValueError):
                continue
    except Exception:
        modifiers = []
    player_entity_id = resolve_player_entity_id(ACTIVE_SESSION)
    player_stats = stats.get(player_entity_id) or stats.get("player") or {}
    player_loc = player_stats.get("Location", "")
    entities_meta = {e["entity_id"]: e for e in load_active_entities(ACTIVE_SESSION._db_path)}
    entity_list = []
    for eid, estats in stats.items():
        meta = entities_meta.get(eid, {})
        entity_list.append({
            "entity_id": eid,
            "name": meta.get("name") or eid,
            "entity_type": meta.get("entity_type") or "",
            "stats": estats,
        })
    entity_list.sort(key=lambda e: (0 if e["entity_id"] == player_entity_id else 1, e["name"]))

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
        "entities": entity_list,
        "player_entity_id": player_entity_id,
        "verbosity": resolve_session_verbosity(),
        "current_location": player_loc,
        "spatial_neighbors": neighbors,
        "time_formatted": time_formatted,
        "lore_hits": getattr(ACTIVE_SESSION, "_last_lore_hits", []) or [],
        "modifiers": modifiers,
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
                        "SELECT entity_id, name FROM Entities WHERE COALESCE(entity_role, entity_type) = 'player';"
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
