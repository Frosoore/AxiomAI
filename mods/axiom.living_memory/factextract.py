"""LLM fact extraction for living memory mode.

Turns a slice of narrative prose into a list of atomic, structured
:class:`~axiom.facts.Fact` objects via an :class:`~axiom.backends.base.LLMBackend`.
The who/what/when/where/why schema and the "atomic, verifiable, no speculation"
discipline are adapted from Hindsight's ``retain/fact_extraction.py`` prompt,
reimplemented for our backend (causal links deliberately left out — see Phase 2
DOC). Causal relations / consolidation come later.

Design rules:

- **Background only**: callers run this off the turn loop; it must never block play.
- **Graceful**: any failure (LLM down, bad JSON, cancellation) yields ``[]`` — the
  game keeps running, the turn simply produced no facts.
- **No persistence here**: returns ``Fact`` objects; the worker stores them via
  ``axiom.facts.insert_facts`` (tagged with the turn id).
"""

from __future__ import annotations

import json

from axiom.backends.base import LLMBackend, LLMMessage
try:
    from .facts import FACT_TYPES, Fact
except (ImportError, ValueError):
    from mods.axiom.living_memory.facts import FACT_TYPES, Fact

_MAX_FACTS_DEFAULT = 8

_SYSTEM_PROMPT = """\
You are a fact-extraction engine for a narrative game. From the passage you are \
given, extract the atomic, verifiable facts a memory system should remember.

Rules:
- One fact = one self-contained idea. Split compound statements.
- Only what the passage states or clearly implies. No speculation, no invention.
- Do not perform arithmetic or invent numbers.
- Prefer concrete, durable facts (who did what, where, why; states that changed).
- Skip pure mood/atmosphere with no informational content.
- Do NOT write analysis, chain-of-thought, or preamble. Output JSON only.

For each fact provide:
- "type": one of "world" (about the world/NPCs), "experience" (something the \
player lived through), "assistant" (something only narrated/hinted).
- "who", "what", "when", "where", "why": short strings ("" when not applicable).
- "entities": list of named people/places/things involved (proper nouns).
- "statement": the fact as one clear sentence (this is the canonical form).

Reply with ONLY a JSON object of the form:
{"facts": [ {"type": "...", "who": "...", "what": "...", "when": "...", \
"where": "...", "why": "...", "entities": ["..."], "statement": "..."} ]}
If the passage contains no rememberable fact, reply {"facts": []}."""


def _build_messages(
    narrative_text: str,
    known_entities: list[str] | None,
    when_hint: str | None,
    max_facts: int,
) -> list[LLMMessage]:
    hints: list[str] = [f"Extract at most {max_facts} facts."]
    if when_hint:
        hints.append(f'Current in-game time: "{when_hint}" (use it for "when").')
    if known_entities:
        names = ", ".join(dict.fromkeys(e for e in known_entities if e))
        if names:
            hints.append(f"Known entity names (prefer these spellings): {names}.")
    user = "\n".join(hints) + "\n\nPassage:\n" + narrative_text.strip()
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _try_parse_json_blob(text: str) -> object | None:
    """Parse a JSON object/array from model text, including fenced / truncated."""
    if not text or not str(text).strip():
        return None
    s = str(text).strip()
    # Strip common markdown fences.
    if s.startswith("```"):
        lines = s.split("\n")
        # drop first fence line and optional trailing fence
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    try:
        return json.loads(s)
    except (ValueError, TypeError):
        pass
    # Truncated object: keep complete {...} fact dicts inside a facts array.
    if '"facts"' in s or s.lstrip().startswith("{"):
        start = s.find("{")
        if start >= 0:
            chunk = s[start:]
            # Close a truncated {"facts":[ {...}, {... incomplete
            if '"facts"' in chunk and "[" in chunk:
                # Keep only fully closed {...} objects inside the array.
                arr_start = chunk.find("[")
                body = chunk[arr_start + 1 :]
                items: list[dict] = []
                depth = 0
                obj_start = None
                for i, ch in enumerate(body):
                    if ch == "{":
                        if depth == 0:
                            obj_start = i
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0 and obj_start is not None:
                            frag = body[obj_start : i + 1]
                            try:
                                obj = json.loads(frag)
                                if isinstance(obj, dict):
                                    items.append(obj)
                            except (ValueError, TypeError):
                                pass
                            obj_start = None
                if items:
                    return {"facts": items}
            # Truncated single object — not recoverable as facts list.
    return None


def _payload_to_items(resp) -> list[dict]:
    """Pull the list of fact dicts out of an LLMResponse, tolerating shapes.

    Backends may surface the JSON as a parsed ``tool_call`` (dict/list) or only
    as ``narrative_text``. Accept ``{"facts": [...]}``, a bare ``[...]``, and a
    JSON string in the prose; anything else → ``[]``.
    """
    candidates: list[object] = []
    tool_call = getattr(resp, "tool_call", None)
    if tool_call is not None:
        candidates.append(tool_call)
    text = getattr(resp, "narrative_text", None)
    if isinstance(text, str) and text.strip():
        parsed = _try_parse_json_blob(text)
        if parsed is not None:
            candidates.append(parsed)

    for cand in candidates:
        if isinstance(cand, dict) and isinstance(cand.get("facts"), list):
            return [it for it in cand["facts"] if isinstance(it, dict)]
        if isinstance(cand, list):
            return [it for it in cand if isinstance(it, dict)]
    return []


def _coerce_facts(items: list[dict], max_facts: int) -> list[Fact]:
    out: list[Fact] = []
    for item in items:
        statement = str(item.get("statement", "") or "").strip()
        if not statement:
            continue
        ftype = str(item.get("type", "world") or "world").strip().lower()
        if ftype not in FACT_TYPES:
            ftype = "world"
        raw_entities = item.get("entities", [])
        if isinstance(raw_entities, list):
            entities = [str(e).strip() for e in raw_entities if str(e).strip()]
        else:
            entities = []
        out.append(Fact(
            statement=statement,
            fact_type=ftype,
            who=str(item.get("who", "") or "").strip(),
            what=str(item.get("what", "") or "").strip(),
            when=str(item.get("when", "") or "").strip(),
            where=str(item.get("where", "") or "").strip(),
            why=str(item.get("why", "") or "").strip(),
            entities=entities,
        ))
        if len(out) >= max_facts:
            break
    return out


def extract_facts(
    llm: LLMBackend,
    narrative_text: str,
    *,
    known_entities: list[str] | None = None,
    when_hint: str | None = None,
    max_facts: int = _MAX_FACTS_DEFAULT,
    max_tokens: int | None = 4096,
) -> list[Fact]:
    """Extract structured facts from ``narrative_text`` using ``llm``.

    Returns ``[]`` for empty input or on any backend/parse failure (never raises),
    so a living-mode background job can call it fire-and-forget.

    ``max_tokens`` defaults high enough for reasoning models (CoT + JSON body).
    """
    if not narrative_text or not narrative_text.strip():
        return []
    messages = _build_messages(narrative_text, known_entities, when_hint, max_facts)
    try:
        resp = llm.complete(
            messages,
            response_format="json",
            temperature=0.2,
            max_tokens=max_tokens,
        )
    except Exception:
        # LLM unreachable / cancelled / provider error → no facts this turn.
        try:
            from axiom.logger import logger
            logger.warning("Fact extraction LLM call failed.", exc_info=True)
        except Exception:
            pass
        return []
    items = _payload_to_items(resp)
    facts = _coerce_facts(items, max_facts)
    if not facts:
        try:
            from axiom.logger import logger
            finish = getattr(resp, "finish_reason", "")
            sample = (getattr(resp, "narrative_text", None) or "")[:160]
            logger.warning(
                "Fact extraction returned 0 facts (finish=%s, sample=%r).",
                finish,
                sample,
            )
        except Exception:
            pass
    return facts
