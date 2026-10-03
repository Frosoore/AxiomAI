"""mods/axiom.time/time_prompts.py

Prompts of the time system: the Chronicler (off-screen world simulation) and the
Timekeeper (how much in-game time a turn took, when the narrator did not say).
Moved out of the kernel's `axiom/prompts.py` with the rest of the time system.
"""

from __future__ import annotations

import json

from axiom.backends.base import LLMMessage
from axiom.kernel.patcher import patchable

CHRONICLER_SYSTEM_PROMPT_BASE: str = """\
You are the Chronicler — a macro-simulation engine for a living fictional world.
Your task is to simulate the independent actions of off-screen entities
(factions, VIP NPCs, cities, world forces) while the player is absent.

OUTPUT FORMAT:
Respond ONLY with a ~~~json … ~~~ fenced block containing state changes and world news.
Do NOT write any narrative prose. Do NOT explain your decisions.

~~~json
{
  "state_changes": [
    {
      "entity_id": "<string>",
      "stat_key":  "<string>",
      "delta":     <number>,
      "value":     "<string or number>"
    }
  ],
  "world_news": [
    "<string: a short headline describing a major off-screen event, e.g. 'The Iron Faction has declared war on the Southern Isles'>",
    "<string: another event...>"
  ]
}
~~~

CONSISTENCY RULES:
- Changes must be logical given each entity's current stats.
- Do not invent new entities.  Only update entities provided in the world state.
- You may leave the state_changes list empty if nothing significant occurs.\
"""

_TENSION_LOW_GUIDANCE: str = (
    "WORLD TENSION IS LOW ({tension:.2f}/1.0). "
    "Heavily favour mundane, incremental events: trade, political negotiations, "
    "minor skirmishes, economic shifts.  Avoid dramatic events."
)

_TENSION_HIGH_GUIDANCE: str = (
    "WORLD TENSION IS HIGH ({tension:.2f}/1.0). "
    "Dramatic events are permitted: assassinations, declarations of war, "
    "supernatural occurrences, cataclysms, sudden power shifts."
)

_TENSION_THRESHOLD: float = 0.5


def build_chronicler_prompt(
    off_screen_entities: list[dict],
    world_tension_level: float,
) -> list[LLMMessage]:
    """Assemble the message list for a Chronicler world-simulation run.

    Structure:
      1. system — base Chronicler prompt + tension guidance
      2. user   — serialised JSON of all off-screen entity states

    Args:
        off_screen_entities: List of entity snapshots, each a dict with at
                             minimum: entity_id, name, entity_type, stats (dict).
        world_tension_level: Float in [0.0, 1.0].  Controls whether the
                             Chronicler is guided toward mundane or dramatic events.

    Returns:
        list[LLMMessage] ready to pass to any LLMBackend.complete().
    """
    tension = max(0.0, min(1.0, world_tension_level))

    if tension >= _TENSION_THRESHOLD:
        guidance = _TENSION_HIGH_GUIDANCE.format(tension=tension)
    else:
        guidance = _TENSION_LOW_GUIDANCE.format(tension=tension)

    system_content = f"{CHRONICLER_SYSTEM_PROMPT_BASE}\n\n{guidance}"

    world_state_json = json.dumps(
        {"world_state": off_screen_entities},
        indent=2,
        ensure_ascii=False,
    )
    user_content = (
        "Simulate the world's independent evolution based on the following state:\n\n"
        f"{world_state_json}"
    )

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]


@patchable("mods.axiom.time.time_prompts:build_timekeeper_prompt")
def build_timekeeper_prompt(player_action: str, narrative_text: str) -> list[LLMMessage]:
    """Assemble the prompt for the 'Timekeeper' chronological parser.

    Args:
        player_action: The text of the user's action.
        narrative_text: The LLM's narrative response to analyze.

    Returns:
        list[LLMMessage] for the LLM.
    """
    system_prompt = (
        "You are a deterministic chronological parser. Your sole task is to analyze the provided narrative text "
        "and deduce the amount of in-game time that has passed, and identify if a major event occurred.\n"
        "RULES:\n"
        "1. Respond ONLY with a valid JSON block, no markdown formatting, no preamble.\n"
        "2. JSON schema: {\"elapsed_minutes\": <int>, \"major_event_description\": \"<string or null>\"}\n"
        "3. 1 hour = 60 minutes. 1 day = 1440 minutes.\n"
        "4. If the text describes a brief conversation or quick action, estimate 1 to 5 minutes.\n"
        "5. If the text describes an immediate combat action with no time jump, return 0 or 1.\n"
        "6. Only provide a 'major_event_description' if something highly significant to the plot happens "
        "(e.g., 'Arrived at Hemlock', 'Defeated the Goblin King'). Otherwise, return null."
    )
    user_content = (
        f"PLAYER ACTION:\n{player_action}\n\n"
        f"NARRATIVE TEXT:\n{narrative_text}"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
