"""axiom.populate — LLM universe authoring.

The seven Creator Studio "Populate" generators, engine-side: each one reads
the universe context from the `.db`, queries the extraction LLM and inserts
the new content **idempotently** (already-known ids/names are skipped).
After every write, the text source of a folder universe is resynchronised
(the text stays the source of truth).

Zero Qt dependency. The LLM is injectable (`llm=`) for tests and
composition; by default it is built from the user config with the extraction
model. Progress messages go through `on_status` (optional callback) — the Qt
tasks plug it into their signals.

`populate_entities` specificity (TICKET-031): the context is processed in
chunks and each chunk is **committed immediately** — an LLM failure
mid-batch (429 quota exhausted despite the backend retries) keeps the work
already done, and re-running resumes where it stopped.
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from typing import Any, Callable

from axiom.backends.base import GenerationCancelled, LLMBackend, LLMConnectionError
from axiom.logger import logger
from axiom.schema import get_connection

StatusCallback = Callable[[str], None]


def _noop_status(_msg: str) -> None:
    pass


def _hook_llm(llm: LLMBackend, on_status: StatusCallback,
              cancel: "threading.Event | None") -> LLMBackend:
    """Branche les hooks TICKET-033 (progression + annulation) sur le backend."""
    llm.on_status = on_status if on_status is not _noop_status else None
    llm.cancel_event = cancel
    return llm


def _default_llm() -> LLMBackend:
    from axiom.config import build_llm_from_config, load_config, resolve_extraction_model

    cfg = load_config()
    return build_llm_from_config(cfg, model_override=resolve_extraction_model(cfg))


def _global_lore(db_path: str) -> str:
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT value FROM Universe_Meta WHERE key = 'global_lore';").fetchone()
    return row[0] if row else ""


def _sync_source(db_path: str) -> None:
    """TICKET-027 : univers-dossier → l'arbo texte reste la vérité."""
    from axiom.library import sync_source_if_any

    sync_source_if_any(db_path)


def _safe_id(raw: str) -> str:
    out = re.sub(r"[^a-z0-9]", "_", raw.lower())
    return re.sub(r"_+", "_", out).strip("_")


def entity_id_for(name: str) -> str:
    """Stable id derived from an entity name.

    A 100% non-Latin name (Cyrillic, CJK…) would yield an empty `_safe_id` —
    the entity would then be silently skipped. **Deterministic** fallback (hash
    of the name): the Populate idempotency (re-run = resume, known ids skipped)
    requires ids that are stable from one run to the next.
    """
    sid = _safe_id(name)
    if sid:
        return sid
    import hashlib

    return "ent_" + hashlib.sha1(name.strip().lower().encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Générateurs
# ---------------------------------------------------------------------------

def populate_meta(
    db_path: str,
    mode: str = "auto",
    custom_text: str | None = None,
    llm: LLMBackend | None = None,
    on_status: StatusCallback = _noop_status,
    cancel: "threading.Event | None" = None,
) -> bool:
    """Refine the metadata (name, global lore, system prompt, first message)."""
    from axiom.prompts import build_populate_meta_prompt

    on_status("Initializing AI backend...")
    if llm is None:
        try:
            llm = _default_llm()
        except Exception as exc:  # parité historique : échec de config non fatal
            logger.error(f"[POPULATE_META] Failed to build LLM backend: {exc}")
            return False
    llm = _hook_llm(llm, on_status, cancel)

    with get_connection(db_path) as conn:
        current_meta = dict(conn.execute("SELECT key, value FROM Universe_Meta;").fetchall())

    on_status("Refining universe metadata...")
    prompt = build_populate_meta_prompt(
        current_meta, custom_instruction=custom_text if mode == "custom" else None)
    resp = llm.complete(prompt, response_format="json")
    data = resp.tool_call if isinstance(resp.tool_call, dict) else {}
    if not data:
        return False

    with get_connection(db_path) as conn:
        for key in ("universe_name", "global_lore", "system_prompt", "first_message"):
            if key in data:
                conn.execute(
                    "INSERT OR REPLACE INTO Universe_Meta (key, value) VALUES (?, ?);",
                    (key, data[key]))
        conn.commit()
    _sync_source(db_path)
    on_status("Metadata refinement complete.")
    return True


def populate_stats(
    db_path: str,
    mode: str = "auto",
    custom_text: str | None = None,
    llm: LLMBackend | None = None,
    on_status: StatusCallback = _noop_status,
    cancel: "threading.Event | None" = None,
) -> int:
    """Generate stat definitions. Returns the number inserted."""
    from axiom.prompts import build_populate_stats_prompt

    llm = _hook_llm(llm or _default_llm(), on_status, cancel)
    with get_connection(db_path) as conn:
        existing_stats = [r[0] for r in conn.execute("SELECT name FROM Stat_Definitions;")]
    global_lore = _global_lore(db_path)

    on_status("Generating stat definitions...")
    prompt = build_populate_stats_prompt(
        global_lore, existing_stats,
        custom_instruction=custom_text if mode == "custom" else None)
    resp = llm.complete(prompt, response_format="json")
    data = resp.tool_call

    # Heuristic: support both wrapped and raw lists
    batch = data if isinstance(data, list) else (
        data.get("stats", []) if isinstance(data, dict) else [])
    if not batch:
        return 0

    inserted = 0
    with get_connection(db_path) as conn:
        # Deux noms différents peuvent produire le même id via _safe_id
        # (« Force! » / « Force? ») : stat_id est PRIMARY KEY, on désambiguïse.
        existing_ids = {r[0] for r in conn.execute("SELECT stat_id FROM Stat_Definitions;")}
        for s in batch:
            name = s.get("name")
            if not name or name in existing_stats:
                continue
            stat_id = _safe_id(name) or uuid.uuid4().hex[:8]
            if stat_id in existing_ids:
                stat_id = f"{stat_id}_{uuid.uuid4().hex[:6]}"
            existing_ids.add(stat_id)
            conn.execute(
                "INSERT INTO Stat_Definitions (stat_id, name, description, value_type, parameters) "
                "VALUES (?, ?, ?, ?, ?);",
                (stat_id, name, s.get("description", ""), s.get("value_type", "numeric"),
                 json.dumps(s.get("parameters", {}))))
            existing_stats.append(name)
            inserted += 1
        conn.commit()
    _sync_source(db_path)
    on_status(f"Stats generation complete: {inserted} added.")
    return inserted


def populate_rules(
    db_path: str,
    mode: str = "auto",
    custom_text: str | None = None,
    llm: LLMBackend | None = None,
    on_status: StatusCallback = _noop_status,
    cancel: "threading.Event | None" = None,
) -> int:
    """Generate game rules. Returns the number inserted."""
    from axiom.prompts import build_populate_rules_prompt

    llm = _hook_llm(llm or _default_llm(), on_status, cancel)
    with get_connection(db_path) as conn:
        stat_names = [r[0] for r in conn.execute("SELECT name FROM Stat_Definitions;")]
        existing_rules = [r[0] for r in conn.execute("SELECT rule_id FROM Rules;")]
    global_lore = _global_lore(db_path)

    on_status("Generating game rules...")
    prompt = build_populate_rules_prompt(
        global_lore, stat_names, existing_rules,
        custom_instruction=custom_text if mode == "custom" else None)
    resp = llm.complete(prompt, response_format="json")
    data = resp.tool_call

    batch = data if isinstance(data, list) else (
        data.get("rules", []) if isinstance(data, dict) else [])
    if not batch:
        return 0

    inserted = 0
    with get_connection(db_path) as conn:
        for r in batch:
            rule_id = r.get("rule_id") or uuid.uuid4().hex[:8]
            if rule_id in existing_rules:
                continue
            conn.execute(
                "INSERT INTO Rules (rule_id, priority, conditions, actions, target_entity) "
                "VALUES (?, ?, ?, ?, ?);",
                (rule_id, r.get("priority", 0), json.dumps(r.get("conditions", {})),
                 json.dumps(r.get("actions", [])), r.get("target_entity", "*")))
            existing_rules.append(rule_id)
            inserted += 1
        conn.commit()
    _sync_source(db_path)
    return inserted


def populate_events(
    db_path: str,
    mode: str = "auto",
    custom_text: str | None = None,
    llm: LLMBackend | None = None,
    on_status: StatusCallback = _noop_status,
    cancel: "threading.Event | None" = None,
) -> int:
    """Schedule world events. Returns the number inserted."""
    from axiom.prompts import build_populate_events_prompt

    llm = _hook_llm(llm or _default_llm(), on_status, cancel)
    with get_connection(db_path) as conn:
        existing_events = [r[0] for r in conn.execute("SELECT title FROM Scheduled_Events;")]
    global_lore = _global_lore(db_path)

    on_status("Scheduling world events...")
    prompt = build_populate_events_prompt(
        global_lore, existing_events,
        custom_instruction=custom_text if mode == "custom" else None)
    resp = llm.complete(prompt, response_format="json")
    data = resp.tool_call

    batch = data if isinstance(data, list) else (
        data.get("events", []) if isinstance(data, dict) else [])
    if not batch:
        return 0

    inserted = 0
    with get_connection(db_path) as conn:
        # event_id est PRIMARY KEY : si le LLM repropose un titre existant
        # (la liste passée au prompt n'est qu'indicative), on saute la ligne
        # au lieu de crasher en IntegrityError (idempotence, TICKET-035).
        existing_ids = {r[0] for r in conn.execute("SELECT event_id FROM Scheduled_Events;")}
        for ev in batch:
            event_id = ev.get("event_id") or _safe_id(ev.get("title", "event")) or uuid.uuid4().hex[:8]
            if event_id in existing_ids:
                continue
            conn.execute(
                "INSERT INTO Scheduled_Events (event_id, title, description, trigger_minute) "
                "VALUES (?, ?, ?, ?);",
                (event_id, ev.get("title", "Event"), ev.get("description", ""),
                 ev.get("trigger_minute", 0)))
            existing_ids.add(event_id)
            inserted += 1
        conn.commit()
    _sync_source(db_path)
    return inserted


def populate_entities(
    db_path: str,
    mode: str = "auto",
    custom_text: str | None = None,
    llm: LLMBackend | None = None,
    on_status: StatusCallback = _noop_status,
    cancel: "threading.Event | None" = None,
) -> int:
    """Generate NPCs/factions from the context (or a free-form instruction).

    The context is split into chunks (global lore + each lore entry); each
    chunk is inserted and **committed immediately** (TICKET-031): an LLM
    failure mid-batch keeps the work already done, re-running resumes
    (existing ids are skipped). Returns the number inserted.
    """
    from axiom.prompts import build_populate_prompt

    on_status("Initializing AI backend...")
    llm = _hook_llm(llm or _default_llm(), on_status, cancel)

    # 1. Gather context
    on_status("Gathering context...")
    with get_connection(db_path) as conn:
        meta = dict(conn.execute("SELECT key, value FROM Universe_Meta;").fetchall())
        lore_rows = conn.execute("SELECT name, content, category FROM Lore_Book;").fetchall()
        stat_defs = []
        for r in conn.execute(
                "SELECT name, description, value_type, parameters FROM Stat_Definitions;"):
            try:
                params = json.loads(r[3]) if r[3] else {}
            except (json.JSONDecodeError, TypeError):
                params = {}
            stat_defs.append({"name": r[0], "description": r[1],
                              "value_type": r[2], "parameters": params})
        ent_rows = conn.execute("SELECT entity_id, name FROM Entities;").fetchall()
        existing_ids = {str(r[0]).lower() for r in ent_rows}
        existing_names = [str(r[1]) for r in ent_rows if r[1]]

    # 2. Prepare chunks
    chunks: list[str] = []
    if mode == "custom" and custom_text:
        chunks.append(custom_text)
    else:
        global_lore = meta.get("global_lore", "").strip()
        if global_lore:
            chunks.append(f"=== GLOBAL WORLD LORE ===\n{global_lore}")
        for name, content, cat in lore_rows:
            cat = cat or "General"
            chunks.append(f"=== CATEGORY: {cat} ===\n### Name: {name}\n{content}")
    if not chunks:
        chunks = ["(No context found)"]

    # 3. Process each chunk — insertion COMMITÉE par chunk (TICKET-031).
    valid_stat_names = {s["name"].lower(): s["name"] for s in stat_defs}
    inserted_count = 0

    for i, chunk in enumerate(chunks):
        # TICKET-033 : frontière d'annulation coopérative — les chunks déjà
        # commités restent (même philosophie de reprise que le quota épuisé).
        if cancel is not None and cancel.is_set():
            _sync_source(db_path)
            raise GenerationCancelled(
                f"Populate cancelled ({inserted_count} entity(ies) kept, "
                f"chunk {i + 1}/{len(chunks)})."
            )
        on_status(f"Processing chunk {i + 1}/{len(chunks)}...")
        prompt = build_populate_prompt(
            chunk, existing_names, stat_defs,
            custom_instruction=custom_text if mode == "custom" else None)
        try:
            resp = llm.complete(prompt, response_format="json")
        except LLMConnectionError as exc:
            if inserted_count:
                _sync_source(db_path)
                raise LLMConnectionError(
                    f"{exc}\n\n[{inserted_count} entity(ies) already inserted before stopping "
                    f"(chunk {i + 1}/{len(chunks)}). Re-running Populate will resume here: "
                    "existing entities are skipped.]"
                ) from exc
            raise

        # Resilient JSON parsing
        data = resp.tool_call
        batch: Any = []
        if isinstance(data, list):
            batch = data
        elif isinstance(data, dict):
            batch = data["entities"] if "entities" in data else [data]
        if not isinstance(batch, list):
            continue

        with get_connection(db_path) as conn:
            for ent in batch:
                name = str(ent.get("name", "")).strip()
                if not name:
                    continue
                eid = entity_id_for(name)
                if eid in existing_ids:
                    continue
                etype = str(ent.get("entity_type", "npc")).lower()
                if etype not in ("npc", "faction"):
                    etype = "npc"
                conn.execute(
                    "INSERT INTO Entities (entity_id, name, entity_type, description, is_active) "
                    "VALUES (?, ?, ?, ?, 1);",
                    (eid, name, etype, str(ent.get("description", "")).strip()))
                existing_ids.add(eid)
                existing_names.append(name)

                stats_dict = ent.get("stats", {})
                if isinstance(stats_dict, dict):
                    for skey, sval in stats_dict.items():
                        real_name = valid_stat_names.get(skey.lower())
                        if real_name:
                            conn.execute(
                                "INSERT INTO Entity_Stats (entity_id, stat_key, stat_value) "
                                "VALUES (?, ?, ?);",
                                (eid, real_name, str(sval)))
                inserted_count += 1
            conn.commit()

    _sync_source(db_path)
    return inserted_count


def populate_lore(
    db_path: str,
    mode: str = "auto",
    custom_text: str | None = None,
    llm: LLMBackend | None = None,
    on_status: StatusCallback = _noop_status,
    cancel: "threading.Event | None" = None,
) -> int:
    """Extend the Lore Book. Returns the number of inserted entries."""
    from axiom.prompts import build_populate_lore_prompt

    on_status("Initializing AI backend...")
    llm = _hook_llm(llm or _default_llm(), on_status, cancel)
    with get_connection(db_path) as conn:
        existing_entries = [r[0] for r in conn.execute("SELECT name FROM Lore_Book;")]
    global_lore = _global_lore(db_path)

    on_status("Generating lore expansion...")
    prompt = build_populate_lore_prompt(
        global_lore, existing_entries,
        custom_instruction=custom_text if mode == "custom" else None)
    resp = llm.complete(prompt, response_format="json")
    data = resp.tool_call

    batch: Any = []
    if isinstance(data, list):
        batch = data
    elif isinstance(data, dict):
        batch = data.get("lore_entries", [data] if "name" in data else [])
    if not batch:
        on_status("Lore expansion complete: No new entries added.")
        return 0

    inserted = 0
    with get_connection(db_path) as conn:
        for entry in batch:
            name = entry.get("name")
            if not name or name in existing_entries:
                continue
            conn.execute(
                "INSERT INTO Lore_Book (entry_id, category, name, content) VALUES (?, ?, ?, ?);",
                (uuid.uuid4().hex, entry.get("category", "General"), name,
                 entry.get("content", "")))
            existing_entries.append(name)
            inserted += 1
        conn.commit()
    _sync_source(db_path)
    on_status(f"Lore expansion complete: {inserted} entries added.")
    return inserted


def populate_map(
    db_path: str,
    mode: str = "auto",
    custom_text: str | None = None,
    llm: LLMBackend | None = None,
    on_status: StatusCallback = _noop_status,
    cancel: "threading.Event | None" = None,
) -> dict:
    """Extend the map (Locations + Connections). Returns {"added_locs", "added_conns"}."""
    from axiom.prompts import build_populate_map_prompt

    on_status("Initializing AI backend...")
    llm = _hook_llm(llm or _default_llm(), on_status, cancel)
    with get_connection(db_path) as conn:
        existing_locs = [dict(r) for r in conn.execute(
            "SELECT location_id, name, scale FROM Locations;")]
    global_lore = _global_lore(db_path)

    on_status("Generating world map expansion...")
    prompt = build_populate_map_prompt(
        global_lore, existing_locs,
        custom_instruction=custom_text if mode == "custom" else None)
    resp = llm.complete(prompt, response_format="json")
    data = resp.tool_call

    # Extremely robust parsing: search for the first dictionary if a list is returned
    if isinstance(data, list):
        data = next((item for item in data if isinstance(item, dict)), None)
    if not isinstance(data, dict):
        logger.error(f"[POPULATE_MAP] Invalid response format (expected dict): {data}")
        return {"added_locs": 0, "added_conns": 0}

    new_locs = data.get("locations", [])
    new_conns = data.get("connections", [])
    added_locs = 0
    added_conns = 0

    with get_connection(db_path) as conn:
        existing_ids = {str(r[0]) for r in conn.execute("SELECT location_id FROM Locations;")}

        for loc in new_locs:
            lid = loc.get("location_id")
            if not lid or lid in existing_ids:
                continue
            name = str(loc.get("name", "")).strip()
            scale = str(loc.get("scale", "zone")).lower()
            if not name:
                name = scale.capitalize()
            pid = loc.get("parent_id")
            if isinstance(pid, str) and pid.lower() in ("none", "null", ""):
                pid = None
            conn.execute(
                "INSERT INTO Locations (location_id, name, scale, parent_id, description, x, y) "
                "VALUES (?, ?, ?, ?, ?, ?, ?);",
                (lid, name, scale, pid, loc.get("description", ""),
                 loc.get("x", 0), loc.get("y", 0)))
            existing_ids.add(lid)
            added_locs += 1

        for c in new_conns:
            src, tgt = c.get("source_id"), c.get("target_id")
            if not src or not tgt:
                continue
            if src not in existing_ids or tgt not in existing_ids:
                continue  # connexion vers un nœud inexistant (sécurité)
            try:
                dist = int(c.get("distance_km", 10))
            except (TypeError, ValueError):
                continue
            # Bi-directional insert
            conn.execute(
                "INSERT OR IGNORE INTO Location_Connections (source_id, target_id, distance_km) "
                "VALUES (?, ?, ?);", (src, tgt, dist))
            conn.execute(
                "INSERT OR IGNORE INTO Location_Connections (source_id, target_id, distance_km) "
                "VALUES (?, ?, ?);", (tgt, src, dist))
            added_conns += 1
        conn.commit()

    on_status(f"Map generation complete: {added_locs} locations, {added_conns} connections added.")
    _sync_source(db_path)
    return {"added_locs": added_locs, "added_conns": added_conns}


# Cibles nommées (Populate tab, PreviewPopulateTask, CLI).
POPULATE_TARGETS: dict[str, Callable[..., Any]] = {
    "meta": populate_meta,
    "stats": populate_stats,
    "entities": populate_entities,
    "rules": populate_rules,
    "events": populate_events,
    "lore": populate_lore,
    "map": populate_map,
}
