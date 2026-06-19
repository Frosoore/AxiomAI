"""LLM generation of mental models for living memory mode (Hindsight §7.8).

Turns the beliefs held about one subject (a character, or the world) into a short
**mental model**: a 2-4 sentence profile of who that subject is *now*. The decision
discipline — base it only on the beliefs, no invention, no arithmetic, capture
change and relationships — is adapted from Hindsight's ``reflect/`` prompts,
reimplemented on our :class:`~axiom.backends.base.LLMBackend`.

Design rules (same as :mod:`axiom.factextract` / :mod:`axiom.consolidate`):

- **Background only**: callers run this off the turn loop; it must never block play.
- **Graceful**: any failure (LLM down, empty answer) yields ``""`` — the profile is
  simply not refreshed this pass, the game keeps running.
- **No persistence here**: returns the summary string; the deterministic UPSERT
  lives in :func:`axiom.mental_models.upsert_mental_model`.
"""

from __future__ import annotations

from axiom.backends.base import LLMBackend, LLMMessage
from axiom.observations import Observation

# Don't bother modelling a subject backed by fewer beliefs than this — a single
# belief is already its own one-liner; a model adds value once memory accumulates.
MIN_BELIEFS_FOR_MODEL = 3
# Cap the beliefs fed to one reflection so the prompt stays bounded on a subject
# that has hundreds of them (most-recent-first slice).
_MAX_BELIEFS_PER_REFLECT = 40

_DEFAULT_MISSION = (
    "Capture who this subject is now: their relationships, goals, grudges, "
    "reputation and how they have changed."
)

_SYSTEM_PROMPT = """\
You maintain living character/world profiles for a narrative game. Given the \
durable beliefs currently held about one subject, write a concise profile of who \
they are now.

Rules:
- 2 to 4 sentences, plain prose. No headers, no lists, no preamble.
- Base it ONLY on the beliefs given. Do not invent facts or do arithmetic.
- Capture relationships, goals, grudges, reputation and any change over time.
- Write in the third person, present tense. Output ONLY the profile text."""


def affected_subjects(actions) -> list[str]:
    """Subjects whose beliefs changed in a consolidation batch (order-preserving).

    Reads the ``subject`` of each create/update action (delete actions drop a
    belief and don't name a subject worth re-modelling here). De-duplicated
    case-insensitively, keeping first-seen spelling. World beliefs (``subject=""``)
    are included (the world model).
    """
    seen: set[str] = set()
    out: list[str] = []
    for a in actions or []:
        if getattr(a, "kind", "") not in ("create", "update"):
            continue
        subj = (getattr(a, "subject", "") or "").strip()
        key = subj.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(subj)
    return out


def _belief_line(o: Observation) -> str:
    return f"- {o.statement} (proof={o.proof_count})"


def _build_messages(subject: str, beliefs: list[Observation], mission: str) -> list[LLMMessage]:
    who = subject.strip() or "the world"
    lines = [_belief_line(o) for o in beliefs[:_MAX_BELIEFS_PER_REFLECT]]
    user = (
        f"Subject: {who}\n"
        f"Guidance — what to capture: {mission}\n\n"
        f"Beliefs currently held about {who}:\n" + "\n".join(lines)
    )
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def reflect(
    llm: LLMBackend,
    subject: str,
    beliefs: list[Observation],
    *,
    mission: str | None = None,
) -> str:
    """Write a mental-model summary for ``subject`` from its ``beliefs``.

    Returns ``""`` when there are too few beliefs to be worth modelling, on empty
    input, or on any backend failure (never raises) — so a living-mode background
    job can call it fire-and-forget.
    """
    usable = [o for o in beliefs if (o.statement or "").strip()]
    if len(usable) < MIN_BELIEFS_FOR_MODEL:
        return ""
    messages = _build_messages(subject, usable, mission or _DEFAULT_MISSION)
    try:
        resp = llm.complete(messages, temperature=0.3)
    except Exception:
        return ""
    return (getattr(resp, "narrative_text", "") or "").strip()
