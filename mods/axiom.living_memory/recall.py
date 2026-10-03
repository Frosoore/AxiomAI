"""mods/axiom.living_memory/recall.py

What the narrator is reminded of each turn in living mode, from the most synthetic
layer to the rawest (§7.8): character profiles (mental models), beliefs
(observations, tagged with their trend) and facts. Each layer favours what concerns
the characters on scene, then fills with the most recent entries, and never looks
past the current turn (a rewound turn never resurfaces a future memory).

Moved from the kernel turn (`ArbitratorEngine._fetch_relevant_*`) with the rest of
the living memory.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable

from mods.axiom.living_memory.facts import get_facts
from mods.axiom.living_memory.mental_models import get_mental_models
from mods.axiom.living_memory.observations import get_observations

# Trends worth telling the narrator (an intensifying belief vs a fading one, TICKET-081).
_SIGNAL_TRENDS = ("strengthening", "weakening", "stale")


def _pick(
    items: Iterable[Any],
    limit: int,
    on_scene: list[str] | None,
    key: Callable[[Any], str],
    about_scene: Callable[[Any, set[str]], bool],
    render: Callable[[Any], str],
) -> list[str]:
    """Up to ``limit`` distinct entries: those about the scene first, then the most recent."""
    if limit <= 0:
        return []
    items = list(items)
    names = {n.strip().lower() for n in (on_scene or []) if n}
    seen: set[str] = set()
    out: list[str] = []

    def add_if(pred: Callable[[Any], bool]) -> None:
        for it in items:
            if len(out) >= limit:
                return
            k = key(it)
            if not k or k in seen or not pred(it):
                continue
            seen.add(k)
            out.append(render(it))

    if names:
        add_if(lambda it: about_scene(it, names))
    add_if(lambda it: True)
    return out


def relevant_facts(db_path: str, save_id: str, max_turn_id: int, on_scene: list[str], limit: int) -> list[str]:
    """Fact statements: those mentioning an on-scene character first, then the most recent."""
    return _pick(
        get_facts(db_path, save_id, max_turn_id=max_turn_id),
        limit, on_scene,
        key=lambda f: f.statement,
        about_scene=lambda f, names: any(str(e).strip().lower() in names for e in (f.entities or [])),
        render=lambda f: f.statement,
    )


def relevant_beliefs(db_path: str, save_id: str, max_turn_id: int, on_scene: list[str], limit: int) -> list[str]:
    """Belief statements (with their trend when it carries a signal): about an on-scene
    character first, then the most recently updated."""
    def render(o: Any) -> str:
        trend = o.trend(max_turn_id)
        return f"{o.statement} ({trend})" if trend in _SIGNAL_TRENDS else o.statement

    return _pick(
        get_observations(db_path, save_id, max_turn_id=max_turn_id),
        limit, on_scene,
        key=lambda o: o.statement,
        about_scene=lambda o, names: (o.subject or "").strip().lower() in names,
        render=render,
    )


def relevant_mental_models(db_path: str, save_id: str, max_turn_id: int, on_scene: list[str], limit: int) -> list[str]:
    """``Subject: summary`` profiles: on-scene characters first, then the most recently refreshed."""
    def render(m: Any) -> str:
        label = (m.subject or "").strip()
        summary = (m.summary or "").strip()
        return f"{label}: {summary}" if label else summary

    return _pick(
        get_mental_models(db_path, save_id, max_turn_id=max_turn_id),
        limit, on_scene,
        key=lambda m: (m.summary or "").strip(),
        about_scene=lambda m, names: (m.subject or "").strip().lower() in names,
        render=render,
    )


def recall_lines(ctx: Any, cfg: Any) -> list[str]:
    """The memory lines of this turn, in the order the narrator reads them
    (profiles, beliefs, facts); nothing outside living mode."""
    from axiom.config import memory_beliefs_active, memory_mental_models_active, memory_mode_is_living

    if not memory_mode_is_living(cfg):
        return []
    db_path, save_id, turn_id = ctx.db_path, ctx.save_id, ctx.turn_id
    on_scene = list(getattr(ctx, "local_character_names", []) or [])
    limit = int(getattr(cfg, "rag_chunk_count", 5) or 0)
    lines: list[str] = []
    if memory_mental_models_active(cfg):
        lines += [f"Profile: {s}" for s in relevant_mental_models(db_path, save_id, turn_id, on_scene, min(limit, 4))]
    if memory_beliefs_active(cfg):
        lines += [f"Belief: {s}" for s in relevant_beliefs(db_path, save_id, turn_id, on_scene, limit)]
    lines += [f"Known fact: {s}" for s in relevant_facts(db_path, save_id, turn_id, on_scene, limit)]
    return lines
