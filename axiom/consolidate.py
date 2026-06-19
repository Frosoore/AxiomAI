"""LLM belief consolidation for living memory mode (Phase 3).

Turns a batch of freshly-extracted :class:`~axiom.facts.Fact` objects, together
with the beliefs already held, into a list of **consolidation actions**
(CREATE / UPDATE / DELETE :class:`~axiom.observations.Observation`). The decision
rules — prefer UPDATE over duplicate CREATE, one facet per belief, be
conservative about DELETE, never do arithmetic, preserve what changed — are
adapted from Hindsight's ``consolidation/prompts.py``, reimplemented on our
:class:`~axiom.backends.base.LLMBackend`.

Design rules (same discipline as ``axiom.factextract``):

- **Background only**: callers run this off the turn loop; it must never block.
- **Graceful**: any failure (LLM down, bad JSON) yields ``[]`` — no belief
  changes this pass, the game keeps running.
- **No persistence here**: returns action objects; the deterministic application
  to the DB lives in ``axiom.observations.apply_consolidation``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from axiom.backends.base import LLMBackend, LLMMessage
from axiom.facts import Fact
from axiom.observations import Observation

_ACTIONS = ("create", "update", "delete")
_DEFAULT_MISSION = (
    "Remember what matters for an evolving story: who did what to whom, lasting "
    "changes of state, relationships, grudges, debts, promises and reputations."
)

# Upper bound on how many existing beliefs are shown to the consolidator in one
# pass. Beliefs accumulate over a campaign; sending *all* of them every pass
# bloats the prompt (cost) and drowns the model in off-topic beliefs. We scope to
# those about the characters in the batch, then top up with the most recent.
_MAX_EXISTING_DEFAULT = 24


def _scope_existing(
    new_facts: list[Fact], existing: list[Observation], max_existing: int
) -> list[Observation]:
    """Pick the beliefs worth showing the consolidator for this batch.

    Keeps beliefs whose ``subject`` is a character cited by the new facts (the
    ones most likely to need updating), then fills the remaining budget with the
    most recently updated beliefs. ``existing`` is assumed most-recent-first
    (``get_observations`` order). No-op when already within budget.
    """
    if max_existing <= 0 or len(existing) <= max_existing:
        return existing
    subjects: set[str] = set()
    for f in new_facts:
        for e in (f.entities or []):
            if e:
                subjects.add(e.strip().lower())
        if f.who:
            subjects.add(f.who.strip().lower())

    chosen: list[Observation] = []
    chosen_ids: set = set()
    # Pass 1: beliefs about a character in play.
    for o in existing:
        if len(chosen) >= max_existing:
            break
        if o.subject and o.subject.strip().lower() in subjects:
            chosen.append(o)
            chosen_ids.add(id(o))
    # Pass 2: top up with the most recent (input order) until the budget is full.
    for o in existing:
        if len(chosen) >= max_existing:
            break
        if id(o) not in chosen_ids:
            chosen.append(o)
            chosen_ids.add(id(o))
    return chosen

_SYSTEM_PROMPT = """\
You maintain a character/world memory of durable BELIEFS for a narrative game. \
You are given the beliefs currently held and a batch of new facts, and you decide \
how the beliefs should change.

Output a list of actions. Each action is one of:
- "create": a genuinely new belief not already covered. Give "subject" (the \
person/place it is about, or "" for the world), "statement" (one clear sentence), \
and "source_fact_ids" (the facts that support it).
- "update": an existing belief that the new facts reinforce or change. Give its \
"observation_id", the revised "statement", and the new "source_fact_ids".
- "delete": an existing belief the new facts clearly contradict or make obsolete \
(e.g. the subject died, the bond was broken). Give its "observation_id".

Rules:
- Prefer UPDATE over creating a near-duplicate. One belief = one facet.
- Be conservative with DELETE: only on a clear contradiction or state change.
- Do NOT do arithmetic or invent numbers. Do not invent facts.
- A belief must be supported by the facts; never restate raw mood/atmosphere.

Reply with ONLY a JSON object of the form:
{"actions": [ {"action": "create", "subject": "...", "statement": "...", \
"source_fact_ids": [1, 2]}, {"action": "update", "observation_id": 5, \
"statement": "...", "source_fact_ids": [3]}, {"action": "delete", \
"observation_id": 7} ]}
If nothing should change, reply {"actions": []}."""


@dataclass
class ConsolidationAction:
    """One belief change proposed by the consolidator LLM."""

    kind: str  # one of _ACTIONS
    statement: str = ""
    subject: str = ""
    observation_id: int | None = None
    source_fact_ids: list[int] = field(default_factory=list)


def _fact_line(f: Fact) -> str:
    fid = f.fact_id if f.fact_id is not None else "?"
    return f"[fact {fid}] {f.statement}"


def _obs_line(o: Observation) -> str:
    subj = f" (about {o.subject})" if o.subject else ""
    return f"[belief {o.observation_id}]{subj} {o.statement} (proof={o.proof_count})"


def _styles_section(
    missions: dict[str, str] | None,
    existing: list[Observation],
    new_facts: list[Fact],
) -> list[str]:
    """Per-character memory styles (B-3) limited to the characters in play.

    Only lists missions for subjects that appear in this batch's beliefs or
    facts, so the prompt stays focused and bounded.
    """
    if not missions:
        return []
    relevant_names: set[str] = set()
    for o in existing:
        if o.subject:
            relevant_names.add(o.subject)
    for f in new_facts:
        for e in (f.entities or []):
            if e:
                relevant_names.add(e)
        if f.who:
            relevant_names.add(f.who)
    # Case-insensitive match against configured missions, keeping the mission's
    # configured name spelling.
    lower = {n.lower(): n for n in relevant_names}
    lines: list[str] = []
    for name, mission in missions.items():
        if name.lower() in lower:
            lines.append(f"- {name}: {mission}")
    if not lines:
        return []
    return ["Character memory styles (what each tends to remember):", *lines, ""]


def _build_messages(
    new_facts: list[Fact],
    existing: list[Observation],
    mission: str,
    missions: dict[str, str] | None = None,
) -> list[LLMMessage]:
    parts: list[str] = [f"Mission — what to remember: {mission}", ""]
    parts.extend(_styles_section(missions, existing, new_facts))
    if existing:
        parts.append("Beliefs currently held:")
        parts.extend(_obs_line(o) for o in existing)
    else:
        parts.append("Beliefs currently held: (none yet)")
    parts.append("")
    parts.append("New facts this batch:")
    parts.extend(_fact_line(f) for f in new_facts)
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(parts)},
    ]


def _payload_to_items(resp) -> list[dict]:
    """Pull the action dicts out of an LLMResponse, tolerating shapes."""
    candidates: list[object] = []
    tool_call = getattr(resp, "tool_call", None)
    if tool_call is not None:
        candidates.append(tool_call)
    text = getattr(resp, "narrative_text", None)
    if isinstance(text, str) and text.strip():
        try:
            candidates.append(json.loads(text.strip()))
        except (ValueError, TypeError):
            pass
    for cand in candidates:
        if isinstance(cand, dict) and isinstance(cand.get("actions"), list):
            return [it for it in cand["actions"] if isinstance(it, dict)]
        if isinstance(cand, list):
            return [it for it in cand if isinstance(it, dict)]
    return []


def _coerce_int_list(raw) -> list[int]:
    out: list[int] = []
    if isinstance(raw, list):
        for v in raw:
            try:
                out.append(int(v))
            except (TypeError, ValueError):
                continue
    return out


def _coerce_actions(items: list[dict], valid_fact_ids: set[int]) -> list[ConsolidationAction]:
    out: list[ConsolidationAction] = []
    for item in items:
        kind = str(item.get("action", "") or "").strip().lower()
        if kind not in _ACTIONS:
            continue
        obs_id = item.get("observation_id")
        try:
            obs_id = int(obs_id) if obs_id is not None else None
        except (TypeError, ValueError):
            obs_id = None
        if kind in ("update", "delete") and obs_id is None:
            continue  # cannot act on an unspecified belief
        statement = str(item.get("statement", "") or "").strip()
        if kind in ("create", "update") and not statement:
            continue
        # Keep only fact ids the LLM was actually shown (no hallucinated sources).
        fact_ids = [fid for fid in _coerce_int_list(item.get("source_fact_ids"))
                    if fid in valid_fact_ids]
        if kind == "create" and not fact_ids:
            continue  # a new belief must cite at least one real fact
        out.append(ConsolidationAction(
            kind=kind,
            statement=statement,
            subject=str(item.get("subject", "") or "").strip(),
            observation_id=obs_id,
            source_fact_ids=fact_ids,
        ))
    return out


def consolidate(
    llm: LLMBackend,
    new_facts: list[Fact],
    existing: list[Observation],
    *,
    mission: str | None = None,
    missions: dict[str, str] | None = None,
    max_existing: int = _MAX_EXISTING_DEFAULT,
) -> list[ConsolidationAction]:
    """Ask ``llm`` how the beliefs should change given ``new_facts``.

    Args:
        mission: The universe-wide default mission (what this world remembers).
        missions: Per-character memory styles ``{entity_name: mission}`` (B-3) —
            only those whose character appears in this batch are shown.
        max_existing: Cap on existing beliefs shown to the LLM (TICKET-077);
            scoped to the batch's characters + most recent. ``<= 0`` disables.

    Returns ``[]`` for empty input or on any backend/parse failure (never raises),
    so a living-mode background job can call it fire-and-forget.
    """
    facts = [f for f in new_facts if f.fact_id is not None and (f.statement or "").strip()]
    if not facts:
        return []
    scoped = _scope_existing(facts, existing, max_existing)
    messages = _build_messages(facts, scoped, mission or _DEFAULT_MISSION, missions)
    try:
        resp = llm.complete(messages, response_format="json", temperature=0.2)
    except Exception:
        return []
    valid_ids = {int(f.fact_id) for f in facts}
    # An update/delete may only target a belief that actually exists.
    known_obs = {o.observation_id for o in existing if o.observation_id is not None}
    actions = _coerce_actions(_payload_to_items(resp), valid_ids)
    return [
        a for a in actions
        if a.kind == "create" or a.observation_id in known_obs
    ]
