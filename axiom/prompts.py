"""
llm_engine/prompt_builder.py

Pure prompt-assembly functions for Axiom AI's LLM agents.

All functions in this module are stateless and side-effect-free.  They
take structured data and return list[LLMMessage] ready for any LLMBackend.

Three prompt families are provided:

  build_narrative_prompt  — Main gameplay turn (Arbitrator)
  build_chronicler_prompt — Off-screen world simulation (Chronicler)
  build_mini_dico_prompt  — Encyclopedic lore lookup (Mini-Dico)

Tool-Call Protocol Reminder
-----------------------------
The narrative prompt instructs the LLM to embed its state-change JSON inside
a  ~~~json … ~~~  fenced block (see llm_engine/base.py).
"""

import json
import re

from axiom.backends.base import LLMMessage

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

HISTORY_TURN_CAP: int = 10
"""Maximum number of prior conversation turns injected into the narrative prompt.
Older turns are silently dropped to keep context windows manageable.
A "turn" is one user message + one assistant message, so at most
2 * HISTORY_TURN_CAP individual messages are included from history."""


def _strip_media_tags(text: str) -> str:
    """Remove Markdown and HTML image tags to keep the prompt text-only.
    
    Strips ![]() and <img /> patterns.
    """
    # Remove Markdown images: ![alt](url)
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    # Remove HTML images: <img ... />
    text = re.sub(r"<img.*?>", "", text, flags=re.IGNORECASE)
    return text.strip()

NARRATIVE_TOOL_CALL_SCHEMA: str = """\
At the end of your response, append exactly one fenced JSON block using ~~~json.
Allowed game_state_tag values: 'exploration', 'combat', 'dialogue', 'tension'.

CRITICAL RULES:
1. FACTIONS: Adjust dialogue based on entity 'Reputation' or 'Alliance'.
2. INVENTORY: Manage items via "inventory_changes" using "action": "add"|"remove".
3. CONTINUITY: Advance the scene based on the actors' intents. Do not repeat their exact words.

~~~json
{
  "state_changes": [{"entity_id": "...", "stat_key": "...", "delta": 0, "value": "..."}],
  "inventory_changes": [{"entity_id": "...", "item_id": "...", "action": "add", "quantity": 1}],
  "narrative_events": ["event_id"],
  "scene_pace": "deliberate",
  "game_state_tag": "exploration"
}
~~~
\
"""

MINI_DICO_SYSTEM_PROMPT: str = """\
You are an encyclopedic lore reference for a fictional universe.
Your role is strictly informational.

RULES you must NEVER break:
- Do NOT roleplay, act as a character, or speak in first person as an NPC.
- Do NOT advance the plot, hint at future events, or make narrative suggestions.
- Do NOT reference the current situation, the player's choices, or recent events.
- ONLY state facts that are explicitly established in the lore excerpts provided.
- If the answer is not in the provided lore, say so plainly.
- Answers must be cold, concise, and encyclopedic — no dramatic flair.\
"""

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

POPULATE_SYSTEM_PROMPT: str = """\
You are a deterministic extraction and generation engine.
Your task is to identify or generate unique characters (NPCs) or organized groups (factions).

CRITICAL RULES:
1. Respond ONLY with a ~~~json ... ~~~ fenced block.
2. DO NOT write any conversational text, summaries, or introductions.
3. If no new entities are found, return {"entities": []}.
4. entity_type must be strictly 'npc' or 'faction'.
5. Focus on identifying and describing each entity accurately.
6. STATS RESTRICTION: You MUST ONLY use stat keys provided in the 'AVAILABLE STATS' list. 
   If a stat is not in that list, IT DOES NOT EXIST. Do not invent it.
   If the list is empty, the 'stats' object MUST be empty {}.
"""

POPULATE_LORE_SYSTEM_PROMPT = """\
You are a world-building engine.
Your task is to expand the lore of a fictional universe based on existing context.

CRITICAL RULES:
1. Respond ONLY with a ~~~json ... ~~~ fenced block.
2. DO NOT write any conversational text.
3. category must be one of: 'General', 'Faction', 'Location', 'Character', 'Magic', or a logical custom category.
4. Focus on consistency with the existing global lore and themes.
5. Provide rich, evocative content for each entry.
"""

POPULATE_STATS_SYSTEM_PROMPT = """\
You are a game designer.
Your task is to define a set of core statistical attributes (Stats) for a role-playing game universe.

CRITICAL RULES:
1. Respond ONLY with a ~~~json ... ~~~ fenced block.
2. value_type must be strictly 'numeric' or 'categorical'.
3. For 'numeric', provide 'min' and 'max' in parameters.
4. For 'categorical', provide a list of 'options' in parameters.
"""

POPULATE_RULES_SYSTEM_PROMPT = """\
You are a logic engine and game balancer.
Your task is to create deterministic game rules that trigger based on entity stats.

CRITICAL RULES:
1. Respond ONLY with a ~~~json ... ~~~ fenced block.
2. Use existing stat names provided.
3. Actions should be logical consequences (e.g., if Health <= 0, then set Status to 'Dead').
"""

POPULATE_EVENTS_SYSTEM_PROMPT = """\
You are a narrative designer.
Your task is to schedule interesting world events at specific times.

CRITICAL RULES:
1. Respond ONLY with a ~~~json ... ~~~ fenced block.
2. Trigger minutes are absolute (e.g., 480 for 8:00 AM).
"""

POPULATE_META_SYSTEM_PROMPT = """\
You are a creative director.
Your task is to refine or generate the foundational metadata for a game universe.

CRITICAL RULES:
1. Respond ONLY with a ~~~json ... ~~~ fenced block.
2. Generate a compelling name, foundational lore, and a welcoming first message.
"""

HERO_SYSTEM_PROMPT = """\
You are an autonomous character acting as a companion in this story.
Your ONLY role is to decide YOUR OWN next action based on the current situation.

CRITICAL RULES:
1. You are NOT the narrator. DO NOT describe the environment, the outcome of your actions, or NPC reactions.
2. DO NOT resolve or narrate the player's action. The narrator will handle the outcome.
3. Respond ONLY with your intent (what you try to do or say) in 1-2 sentences.
4. Speak in the first person ("I draw my sword", "I tell him to stop").
"""

def build_hero_decision_prompt(
    hero_name: str,
    hero_persona: str,
    hero_stats: str,
    history: list[LLMMessage],
    rag_chunks: list[str] | None = None,
    spatial_context: dict | None = None,
    current_intents: dict[str, str] | None = None,
    player_name: str | None = None,
    player_persona: str | None = None,
) -> list[LLMMessage]:
    """Assemble the prompt for the Hero IA to decide its next action."""
    ctx_parts = [
        f"HERO NAME: {hero_name}",
        f"HERO PERSONA: {hero_persona}",
    ]
    if player_name:
        ctx_parts.append(f"COMPANION TO (PLAYER): {player_name}")
    if player_persona:
        ctx_parts.append(f"PLAYER BACKSTORY: {player_persona}")

    if "id:" in hero_stats or "[" in hero_stats:
        ctx_parts.append(f"RELEVANT ENTITIES & STATS:\n{hero_stats}")
    else:
        ctx_parts.append(f"HERO STATS:\n{hero_stats}")

    
    if spatial_context:
        sc_lines = [f"LOCATION: {spatial_context.get('breadcrumb', 'Unknown')}"]
        desc = spatial_context.get("description")
        if desc:
            sc_lines.append(f"Description: {desc}")
        neighbors = spatial_context.get("neighbors", [])
        if neighbors:
            sc_lines.append("Available connected routes:")
            for n in neighbors:
                sc_lines.append(f"- {n['name']} ({n['distance_km']} km)")
        ctx_parts.append("\n".join(sc_lines))
        
    if rag_chunks:
        rag_section = "\n".join(f"- {chunk}" for chunk in rag_chunks)
        ctx_parts.append(f"RECENT MEMORIES:\n{rag_section}")

    # Format narrative history as text to avoid role confusion
    if history:
        history_text = []
        for msg in history[-4:]:
            role_name = "Narrator" if msg["role"] == "assistant" else "Player"
            history_text.append(f"{role_name}: {msg['content']}")
        ctx_parts.append("RECENT NARRATIVE HISTORY:\n" + "\n".join(history_text))

    if current_intents:
        intents_str = "\n".join(f"[{a_id}] INTENT: {intent}" for a_id, intent in current_intents.items())
        ctx_parts.append(f"CURRENT SIMULTANEOUS ACTIONS BY OTHERS:\n{intents_str}\n\nTake these into account for your own action.")

    ctx_parts.append("DECIDE YOUR NEXT ACTION. Remember: DO NOT act as the narrator. Describe ONLY what you do.")

    user_content = "\n\n".join(ctx_parts)
    
    messages = [{"role": "system", "content": HERO_SYSTEM_PROMPT}]
    messages.append({"role": "user", "content": user_content})
    return messages

def build_populate_meta_prompt(
    current_meta: dict,
    custom_instruction: str | None = None
) -> list[LLMMessage]:
    """Assemble the prompt for the 'Populate' Metadata generator."""
    task_desc = "Refine the universe's foundational metadata (Name, Global Lore, System Prompt, First Message)."
    if custom_instruction:
        task_desc = f"GENERATE/REFINE universe metadata based on this instruction: {custom_instruction}"

    user_content = (
        f"TASK: {task_desc}\n"
        "OUTPUT REQUIREMENT: Respond ONLY with the JSON block.\n\n"
        "~~~json\n"
        "{\n"
        "  \"universe_name\": \"<CATCHY_NAME>\",\n"
        "  \"global_lore\": \"<FOUNDATIONAL_CONTEXT_FOR_AI>\",\n"
        "  \"system_prompt\": \"<AI_NARRATOR_INSTRUCTIONS>\",\n"
        "  \"first_message\": \"<INTRO_TEXT_FOR_PLAYER>\"\n"
        "}\n"
        "~~~\n\n"
        f"CURRENT METADATA:\n{json.dumps(current_meta, indent=2)}"
    )
    return [
        {"role": "system", "content": POPULATE_META_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

def build_populate_stats_prompt(
    global_lore: str,
    existing_stats: list[str],
    custom_instruction: str | None = None
) -> list[LLMMessage]:
    """Assemble the prompt for the 'Populate' Stats generator."""
    task_desc = "Define core RPG stats (e.g. Strength, Health, Reputation) suitable for this world."
    if custom_instruction:
        task_desc = f"GENERATE new stat definitions based on this instruction: {custom_instruction}"

    user_content = (
        f"WORLD LORE:\n{global_lore}\n\n"
        f"EXISTING STATS: {', '.join(existing_stats)}\n\n"
        f"TASK: {task_desc}\n"
        "~~~json\n"
        "{\n"
        "  \"stats\": [\n"
        "    {\n"
        "      \"name\": \"<STAT_NAME>\",\n"
        "      \"description\": \"<PURPOSE>\",\n"
        "      \"value_type\": \"numeric\",\n"
        "      \"parameters\": {\"min\": 0, \"max\": 100}\n"
        "    },\n"
        "    {\n"
        "      \"name\": \"<OTHER_STAT>\",\n"
        "      \"description\": \"<PURPOSE>\",\n"
        "      \"value_type\": \"categorical\",\n"
        "      \"parameters\": {\"options\": [\"Option A\", \"Option B\"]}\n"
        "    }\n"
        "  ]\n"
        "}\n"
        "~~~"
    )
    return [
        {"role": "system", "content": POPULATE_STATS_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

def build_populate_rules_prompt(
    global_lore: str,
    stat_names: list[str],
    existing_rules: list[str],
    custom_instruction: str | None = None
) -> list[LLMMessage]:
    """Assemble the prompt for the 'Populate' Rules generator."""
    task_desc = "Create logic rules (e.g. 'If Health <= 0 then Status = Dead')."
    if custom_instruction:
        task_desc = f"GENERATE rules based on this instruction: {custom_instruction}"

    user_content = (
        f"WORLD LORE:\n{global_lore}\n\n"
        f"AVAILABLE STATS: {', '.join(stat_names)}\n\n"
        f"TASK: {task_desc}\n"
        "~~~json\n"
        "{\n"
        "  \"rules\": [\n"
        "    {\n"
        "      \"rule_id\": \"<UNIQUE_ID>\",\n"
        "      \"priority\": 10,\n"
        "      \"conditions\": [\n"
        "        {\"target\": \"*\", \"stat\": \"Health\", \"comparator\": \"<=\", \"value\": \"0\"}\n"
        "      ],\n"
        "      \"actions\": [\n"
        "        {\"type\": \"stat_set\", \"stat\": \"Status\", \"value\": \"Dead\"}\n"
        "      ]\n"
        "    }\n"
        "  ]\n"
        "}\n"
        "~~~"
    )
    return [
        {"role": "system", "content": POPULATE_RULES_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

def build_populate_events_prompt(
    global_lore: str,
    existing_events: list[str],
    custom_instruction: str | None = None
) -> list[LLMMessage]:
    """Assemble the prompt for the 'Populate' Events generator."""
    task_desc = "Schedule world events (e.g. 'The Festival of Lights' at minute 1200)."
    if custom_instruction:
        task_desc = f"GENERATE events based on this instruction: {custom_instruction}"

    user_content = (
        f"WORLD LORE:\n{global_lore}\n\n"
        f"TASK: {task_desc}\n"
        "~~~json\n"
        "{\n"
        "  \"events\": [\n"
        "    {\n"
        "      \"title\": \"<EVENT_TITLE>\",\n"
        "      \"description\": \"<WHAT_HAPPENS>\",\n"
        "      \"trigger_minute\": 600\n"
        "    }\n"
        "  ]\n"
        "}\n"
        "~~~"
    )
    return [
        {"role": "system", "content": POPULATE_EVENTS_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def build_populate_prompt(
    lore_chunks: str,
    existing_entities: list[str],
    stat_defs: list[dict] = None,
    custom_instruction: str | None = None,
) -> list[LLMMessage]:
    """Assemble the prompt for the 'Populate' entity generator.

    Args:
        lore_chunks: The text context to analyze for entities.
        existing_entities: List of already defined entity names to skip.
        stat_defs: List of available Stat_Definitions.
        custom_instruction: Optional user-provided instruction for generation.

    Returns:
        list[LLMMessage] for the LLM.
    """
    skip_list = ""
    if existing_entities:
        skip_list = f"\nALREADY KNOWN ENTITIES (SKIP THESE): {', '.join(existing_entities)}"

    stats_info = "=== AVAILABLE STATS ===\n(No stats defined for this universe. Leave 'stats' empty.)"
    if stat_defs:
        lines = ["=== AVAILABLE STATS ==="]
        for s in stat_defs:
            name = s.get("name")
            vtype = s.get("value_type", "text")
            desc = s.get("description", "No description.")
            params = s.get("parameters", {})
            lines.append(f"- \"{name}\" ({vtype}) : {desc}. Constraints: {params}")
        stats_info = "\n".join(lines)

    task_desc = "Extract NEW unique NPCs or factions from the lore context below."
    if custom_instruction:
        task_desc = f"GENERATE new unique NPCs or factions based on this instruction: {custom_instruction}"

    user_content = (
        f"{stats_info}\n\n"
        f"TASK: {task_desc}\n"
        "OUTPUT REQUIREMENT: Respond ONLY with the JSON block. No preamble.\n\n"
        "CRITICAL STATS RULE:\n"
        "1. The 'stats' object MUST ONLY contain exact keys from the AVAILABLE STATS list above.\n"
        "2. If a stat does not logically apply, DO NOT include it.\n"
        "3. DO NOT invent, guess, or hallucinate stats (e.g., 'Wisdom', 'HP') if they are not listed above.\n"
        "4. Respect the value_type and Constraints.\n"
        "5. If no stats are listed or relevant, leave the 'stats' object entirely empty {}.\n\n"
        "~~~json\n"
        "{\n"
        "  \"entities\": [\n"
        "    {\n"
        "      \"name\": \"<NAME_HERE>\",\n"
        "      \"entity_type\": \"<npc_OR_faction>\",\n"
        "      \"description\": \"<CONCISE_ROLE_DESCRIPTION>\",\n"
        "      \"stats\": {\n"
        "        \"<EXACT_STAT_NAME>\": \"<LOGICAL_VALUE>\"\n"
        "      }\n"
        "    }\n"
        "  ]\n"
        "}\n"
        "~~~\n\n"
        f"CONTEXT / LORE:\n{lore_chunks}\n{skip_list}"
    )

    return [
        {"role": "system", "content": POPULATE_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

def build_populate_lore_prompt(
    global_lore: str,
    existing_entries: list[str],
    custom_instruction: str | None = None,
) -> list[LLMMessage]:
    """Assemble the prompt for the 'Populate' Lore Book generator."""
    skip_list = ""
    if existing_entries:
        skip_list = f"\nALREADY KNOWN LORE ENTRIES (SKIP THESE): {', '.join(existing_entries)}"

    task_desc = "Expand the lore by creating new entries for factions, magic systems, or locations."
    if custom_instruction:
        task_desc = f"GENERATE new lore entries based on this instruction: {custom_instruction}"

    user_content = (
        f"TASK: {task_desc}\n"
        "OUTPUT REQUIREMENT: Respond ONLY with the JSON block. No preamble.\n\n"
        "~~~json\n"
        "{\n"
        "  \"lore_entries\": [\n"
        "    {\n"
        "      \"category\": \"<General|Faction|Location|Character|Magic>\",\n"
        "      \"name\": \"<ENTRY_NAME_HERE>\",\n"
        "      \"content\": \"<RICH_DESCRIPTIVE_CONTENT>\"\n"
        "    }\n"
        "  ]\n"
        "}\n"
        "~~~\n\n"
        f"EXISTING WORLD LORE:\n{global_lore}\n{skip_list}"
    )

    return [
        {"role": "system", "content": POPULATE_LORE_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

CANONIZE_SYSTEM_PROMPT: str = """\
You are a deterministic canon-extraction engine for a role-playing universe.
You read a transcript of recent play and extract the NEW canonical elements the story
introduced (characters, factions, places, facts) so they become part of the universe
definition for future games.

CRITICAL RULES:
1. Respond ONLY with a ~~~json ... ~~~ fenced block.
2. DO NOT write any conversational text.
3. Extract ONLY elements that are clearly established by the story — no invention.
4. NEVER extract the player character itself.
5. Skip anything already present in the known entities / lore lists.
6. If nothing new is canon-worthy, return {"entities": [], "lore_entries": []}.
"""


def build_canonize_prompt(
    narrative_text: str,
    existing_entities: list[str],
    existing_lore: list[str],
    global_lore: str = "",
) -> list[LLMMessage]:
    """Prompt de canonisation (TICKET-030) : histoire récente → entités + lore canon."""
    skip_entities = ", ".join(existing_entities) if existing_entities else "(none)"
    skip_lore = ", ".join(existing_lore) if existing_lore else "(none)"

    user_content = (
        "TASK: Extract the NEW canonical elements introduced by this play transcript.\n"
        "OUTPUT REQUIREMENT: Respond ONLY with the JSON block. No preamble.\n\n"
        "~~~json\n"
        "{\n"
        "  \"entities\": [\n"
        "    {\n"
        "      \"name\": \"<NAME_HERE>\",\n"
        "      \"entity_type\": \"<npc_OR_faction>\",\n"
        "      \"description\": \"<CONCISE_CANON_DESCRIPTION>\"\n"
        "    }\n"
        "  ],\n"
        "  \"lore_entries\": [\n"
        "    {\n"
        "      \"category\": \"<General|Faction|Location|Character|Magic>\",\n"
        "      \"name\": \"<ENTRY_NAME_HERE>\",\n"
        "      \"content\": \"<WHAT_THE_STORY_ESTABLISHED>\"\n"
        "    }\n"
        "  ]\n"
        "}\n"
        "~~~\n\n"
        f"KNOWN ENTITIES (SKIP THESE): {skip_entities}\n"
        f"KNOWN LORE ENTRIES (SKIP THESE): {skip_lore}\n\n"
        f"EXISTING WORLD LORE (for consistency):\n{global_lore}\n\n"
        f"RECENT PLAY TRANSCRIPT:\n{narrative_text}"
    )

    return [
        {"role": "system", "content": CANONIZE_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


POPULATE_MAP_SYSTEM_PROMPT = (
    "You are an expert world builder. Your task is to expand the world map hierarchy and connections.\n"
    "Available scales (from largest to smallest): universe, galaxy, world, country, zone, city, district, building, room, poi.\n"
    "CRITICAL RULES:\n"
    "1. Return a JSON object with 'locations' and 'connections' lists.\n"
    "2. For each location: 'location_id' (unique string), 'name', 'scale', 'parent_id' (optional), 'description', 'x', 'y' (0 to 1000).\n"
    "3. If a name is not specified or obvious, use the SCALE name as the default name (e.g., 'City', 'Universe').\n"
    "4. For each connection: 'source_id', 'target_id', 'distance_km'.\n"
    "5. Ensure the structure is logical and matches the world lore.\n"
    "6. Use coordinates (x, y) to layout nodes at the SAME level (same parent) in a way that makes sense visually."
)

def build_populate_map_prompt(
    global_lore: str,
    existing_locations: list[dict],
    custom_instruction: str | None = None,
) -> list[LLMMessage]:
    """Assemble the prompt for the 'Populate' Map generator."""
    ctx_parts = [f"EXISTING WORLD LORE:\n{global_lore}"]
    if existing_locations:
        loc_str = "\n".join([f"- {l.get('name')} ({l.get('scale')}, ID: {l.get('location_id')})" for l in existing_locations[:50]])
        ctx_parts.append(f"EXISTING LOCATIONS:\n{loc_str}")
        
    task_desc = "Expand the world map with new locations and connections."
    if custom_instruction:
        task_desc = f"GENERATE new map elements based on this instruction: {custom_instruction}"
        
    user_content = (
        f"TASK: {task_desc}\n"
        "OUTPUT REQUIREMENT: Respond ONLY with the JSON block. No preamble.\n\n"
        "~~~json\n"
        "{\n"
        "  \"locations\": [\n"
        "    {\n"
        "      \"location_id\": \"id_string\",\n"
        "      \"name\": \"Location Name\",\n"
        "      \"scale\": \"city\",\n"
        "      \"parent_id\": \"parent_id_string\",\n"
        "      \"description\": \"Brief description\",\n"
        "      \"x\": 100, \"y\": 200\n"
        "    }\n"
        "  ],\n"
        "  \"connections\": [\n"
        "    {\"source_id\": \"id1\", \"target_id\": \"id2\", \"distance_km\": 50}\n"
        "  ]\n"
        "}\n"
        "~~~\n\n"
        + "\n\n".join(ctx_parts)
    )

    return [
        {"role": "system", "content": POPULATE_MAP_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

def _format_lore_book_block(lore_book: list[dict]) -> str:
    """Format a Lore_Book entry list into a category-grouped text block.

    Groups entries by category and formats each as::

        ### Category: Faction
        #### Name: The Red Guard
        Content here...

    Args:
        lore_book: List of entry dicts with keys: category, name, content.

    Returns:
        A formatted multi-line string, or empty string if list is empty.
    """
    if not lore_book:
        return ""

    # Group by category (preserving insertion order)
    groups: dict[str, list[dict]] = {}
    for entry in lore_book:
        cat = entry.get("category", "").strip() or "General"
        groups.setdefault(cat, []).append(entry)

    lines: list[str] = ["=== LORE BOOK ==="]
    for cat, entries in groups.items():
        lines.append(f"\n### Category: {cat}")
        for entry in entries:
            name = entry.get("name", "").strip() or "(unnamed)"
            content = entry.get("content", "").strip()
            lines.append(f"#### {name}")
            if content:
                lines.append(content)
    return "\n".join(lines)


def build_narrative_prompt(
    universe_system_prompt: str,
    entity_stats_block: str,
    rag_chunks: list[str],
    history: list[LLMMessage],
    intents: dict[str, str],
    pending_correction: str | None = None,
    global_lore: str | None = None,
    player_persona: str | None = None,
    lore_book: list[dict] | None = None,
    verbosity_level: str = "balanced",
    current_time_str: str | None = None,
    scheduled_events: list[dict] | None = None,
    spatial_context: dict | None = None,
    mode: str = "Normal",
    hero_entity_id: str | None = None,
    local_character_names: list[str] | None = None,
    basic_prompt: str | None = None,
) -> list[LLMMessage]:
    """Assemble the full message list for a narrative gameplay turn.

    Structure (in order):
      1. system  — universe prompt + optional global_lore + optional lore_book
                   block + optional player_persona + entity stats + tool-call
                   instructions + verbosity rules
      2. user/assistant pairs — capped prior history (newest HISTORY_TURN_CAP turns)
      3. system  — pending correction (only if not None)
      4. user    — the actors' intents for this tick (with optional RAG context prepended)

    Args:
        universe_system_prompt: The universe's foundational system prompt.
        entity_stats_block:     Formatted current entity stats string.
        rag_chunks:             Relevant narrative memory chunks for this turn.
        history:                Prior conversation as list[LLMMessage].
        intents:                Dict mapping actor entity_id to their intent text.
        pending_correction:     Hidden correction message for the Correction Loop.
        global_lore:            Optional global lore text from Universe_Meta.
        player_persona:         Optional player background text.
        lore_book:              Optional list of Lore_Book entry dicts; formatted
                                as a category-grouped block under global_lore.
        verbosity_level:        'short', 'balanced', or 'talkative'.
        current_time_str:       Optional formatted time string (e.g. Day 1, 08:00 (Morning)).
        scheduled_events:       Optional list of triggered world events to incorporate.
        spatial_context:        Optional dict with breadcrumb, description, and neighbors.
        mode:                   Game mode ('Normal', 'Hardcore', 'Companion').
        hero_entity_id:         The entity ID of the Hero (if applicable).
        local_character_names:  List of names of all characters present in the scene.
        basic_prompt:           Custom user instructions to append to the system prompt.

    Returns:
        list[LLMMessage] ready to pass to any LLMBackend.complete().
    """
    messages: list[LLMMessage] = []

    if basic_prompt is None:
        try:
            from axiom.config import load_config
            cfg = load_config()
            basic_prompt = getattr(cfg, "basic_prompt", "")
        except Exception:
            basic_prompt = ""

    basic_prompt = basic_prompt.strip()
    if basic_prompt:
        universe_system_prompt = f"{universe_system_prompt}\n\n{basic_prompt}"

    # 1. Primary system prompt
    parts = [universe_system_prompt]

    
    # Consolidate core narrative rules
    actor_ids = list(intents.keys()) if intents else ["player"]
    actors_str = ", ".join(actor_ids)
    player_id = next((aid for aid in intents.keys() if aid != hero_entity_id), "player") if intents else "player"
    
    rules = [
        "NARRATOR RULES:",
        "- Formatting: Use *actions* and \"dialogue\".",
        f"- Identity: You are the world's narrator and you control the NPCs.",
        f"- Protagonist: '{player_id}' is the Human Player. Always address them as 'You' and center the narrative around their actions.",
        "- Storytelling: Weave ALL the actors' intents into a cohesive, engaging narrative scene. Describe them performing their intended actions together, then describe the outcome and how the NPCs react.",
        f"- Agency Limits: You must describe {actors_str} executing their intents, but DO NOT invent NEW actions, decisions, or dialogue for them beyond what they specified.",
    ]

    if mode == "Companion" and hero_entity_id:
        rules.append(f"- Companion: '{hero_entity_id}' is the Player's AI Companion. They are a DISTINCT character. Because both actors may use the first person ('I') in their intents, you MUST translate the Player's intent to 'You' and the Companion's intent to their third-person name ('{hero_entity_id}'). DO NOT merge them into one person.")
    
    if local_character_names and len(local_character_names) >= 2:
        formatted_names = [("You" if n.lower() == "player" else n) for n in local_character_names]
        if len(formatted_names) >= 3:
            names_str = ", ".join(formatted_names[:-1]) + ", and " + formatted_names[-1]
            rules.append(f"- Group Awareness: {names_str} are all present together in the same location. When NPCs react or speak, they must address the entire group of {len(formatted_names)} characters together. DO NOT refer to them as 'you two' or ignore any members of the group.")
        else:
            names_str = " and ".join(formatted_names)
            rules.append(f"- Group Awareness: {names_str} are present together. Address them as a pair, not as a single person.")

    
    len_map = {
        "short": "CONCISE (2 sentences).",
        "balanced": "MODERATE (1-2 paragraphs).",
        "talkative": "ELABORATE and detailed."
    }
    rules.append(f"- Length: {len_map.get(verbosity_level.lower(), 'MODERATE')}")
    parts.append("\n".join(rules))

    if global_lore and global_lore.strip():
        parts.append(f"WORLD LORE:\n{global_lore.strip()}")
    if lore_book:
        lb_block = _format_lore_book_block(lore_book)
        if lb_block:
            parts.append(lb_block)
    if player_persona and player_persona.strip():
        parts.append(f"CHARACTER BACKGROUND:\n{player_persona.strip()}")
    
    time_header = f"TIME: {current_time_str}\n" if current_time_str else ""
    parts.append(f"CURRENT STATE:\n{time_header}{entity_stats_block}")

    if spatial_context:
        sc_lines = [f"LOCATION: {spatial_context.get('breadcrumb', 'Unknown')}"]
        desc = spatial_context.get("description")
        if desc:
            sc_lines.append(f"Description: {desc}")
        
        neighbors = spatial_context.get("neighbors", [])
        if neighbors:
            sc_lines.append("Available connected routes (must move to these nodes):")
            for n in neighbors:
                sc_lines.append(f"- {n['name']} (ID: {n['location_id']}, {n['distance_km']} km)")
        
        parts.append("\n".join(sc_lines))

    if scheduled_events:
        event_lines = ["WORLD EVENTS TRIGGERED:"]
        for ev in scheduled_events:
            title = ev.get("title", "Event")
            desc = ev.get("description", "")
            event_lines.append(f"- {title}: {desc}")
        event_lines.append("Incorporate these events into your response immediately.")
        parts.append("\n".join(event_lines))

    parts.append(NARRATIVE_TOOL_CALL_SCHEMA)

    system_content = "\n\n".join(parts)
    messages.append({"role": "system", "content": system_content})

    # 2. Capped history (user/assistant pairs only; extra system messages dropped)
    conversation_turns = _extract_conversation_turns(history)
    capped = conversation_turns[-HISTORY_TURN_CAP:]
    for turn_pair in capped:
        messages.extend(turn_pair)

    # 3. Pending correction (injected as system message before user input)
    if pending_correction is not None:
        messages.append({"role": "system", "content": pending_correction})

    # 4. User message with optional RAG context
    final_user_content = ""
    if rag_chunks:
        rag_section = "\n\n".join(f"[MEMORY]: {chunk}" for chunk in rag_chunks)
        final_user_content += f"{rag_section}\n\n---\n\n"

    intents_str = "\n".join(f"[{actor_id}] INTENT: {intent}" for actor_id, intent in intents.items())
    final_user_content += f"[SIMULTANEOUS ACTIONS FOR THIS TICK]\n{intents_str}"

    messages.append({"role": "user", "content": final_user_content})

    # Phase 11: Final behavior instruction (Recency Bias)
    # This system message is appended AFTER the user message to force compliance.
    num_actors = len(intents) if intents else 1
    weave_word = "BOTH" if num_actors == 2 else "ALL" if num_actors > 2 else "the"
    
    group_reminder = ""
    if local_character_names and len(local_character_names) >= 3:
        formatted_names = [("You" if n.lower() == "player" else n) for n in local_character_names]
        names_str = ", ".join(formatted_names[:-1]) + ", and " + formatted_names[-1]
        group_reminder = f" Note that {names_str} are ALL present in the scene together; NPCs must address the entire group of {len(formatted_names)} characters (DO NOT ignore any members or refer to them as 'you two')."

    verbosity_map = {
        "short": f"CRITICAL REMINDER: Response must be VERY SHORT (2 sentences). Weave {weave_word} {actors_str}'s distinct intents into the scene (translate 'I' to 'You' for the Player, and use the Companion's name). Do NOT merge them. Then describe NPC reactions.{group_reminder}",
        "balanced": f"CRITICAL REMINDER: Response must be BALANCED (1-2 paragraphs). Weave {weave_word} {actors_str}'s distinct intents into the scene (translate 'I' to 'You' for the Player, and use the Companion's name). Do NOT merge them. Then describe NPC reactions.{group_reminder}",
        "talkative": f"CRITICAL REMINDER: Response must be DETAILED and descriptive. Weave {weave_word} {actors_str}'s distinct intents into the scene (translate 'I' to 'You' for the Player, and use the Companion's name). Do NOT merge them. Then describe NPC reactions.{group_reminder}"
    }
    final_instr = verbosity_map.get(verbosity_level.lower(), verbosity_map["balanced"])
    messages.append({"role": "system", "content": final_instr})

    return messages


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


def build_mini_dico_prompt(
    question: str,
    rag_chunks: list[str],
    lore_book: list[dict] | None = None,
    global_lore: str | None = None,
) -> list[LLMMessage]:
    """Assemble the message list for a Mini-Dico lore-lookup query.

    The Mini-Dico is strictly siloed from the narrative context: it receives
    ONLY the system persona, relevant lore chunks from RAG, the structured
    Lore Book (if provided), global world lore, and the user's question.

    Args:
        question:    The player's lore question verbatim.
        rag_chunks:  Relevant lore excerpts from VectorMemory.query().
        lore_book:   Optional Lore_Book entry list; formatted and prepended to
                     the user message to give structured world-building context.
        global_lore: Optional foundational world lore from Universe_Meta.

    Returns:
        list[LLMMessage] ready to pass to any LLMBackend.complete().
    """
    sections: list[str] = []

    if global_lore and global_lore.strip():
        sections.append(f"=== GLOBAL WORLD LORE ===\n{global_lore.strip()}")

    lb_block = _format_lore_book_block(lore_book or [])
    if lb_block:
        sections.append(lb_block)

    if rag_chunks:
        lore_section = "\n\n---\n\n".join(rag_chunks)
        sections.append(f"=== LORE REFERENCE EXCERPTS ===\n{lore_section}")
    else:
        sections.append("[No lore excerpts available for this query.]")

    sections.append(f"=== QUESTION ===\n{question}")
    user_content = "\n\n".join(sections)

    return [
        {"role": "system", "content": MINI_DICO_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def format_entity_stats_block(entity_snapshots: list[dict]) -> str:
    """Format a list of entity stat snapshots into a human-readable block.

    Each snapshot should have keys: entity_id, name, entity_type, stats (dict).
    The resulting block is injected directly into the LLM's system prompt so
    it can reference current game state without hallucinating outdated values.

    Args:
        entity_snapshots: List of dicts, each with entity_id, name,
                          entity_type, and stats keys.

    Returns:
        A formatted multi-line string.  Returns "(no entities)" if the list
        is empty.
    """
    if not entity_snapshots:
        return "(no entities)"

    lines: list[str] = []
    for snap in entity_snapshots:
        entity_id: str = snap.get("entity_id", "unknown")
        name: str = snap.get("name", entity_id)
        entity_type: str = snap.get("entity_type", "unknown")
        stats: dict = snap.get("stats", {})

        lines.append(f"[{entity_type.upper()}] {name} (id: {entity_id})")
        if stats:
            for key, value in stats.items():
                lines.append(f"    {key}: {value}")
        else:
            lines.append("    (no stats)")
        lines.append("")  # blank line between entities

    return "\n".join(lines).rstrip()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_conversation_turns(
    history: list[LLMMessage],
) -> list[list[LLMMessage]]:
    """Group a flat message list into (user, assistant) turn pairs.

    System messages in the history are dropped — they are not part of the
    conversation turns injected into the prompt (the primary system message
    is constructed separately by build_narrative_prompt).

    Args:
        history: Flat list of LLMMessages from prior turns.

    Returns:
        List of [user_msg, assistant_msg] pairs.  Unpaired trailing user
        messages are included as single-element sublists.
    """
    turns: list[list[LLMMessage]] = []
    current_pair: list[LLMMessage] = []

    for msg in history:
        if msg["role"] == "system":
            continue  # prior system messages are not replayed
        
        # Phase 10: Multi-player consistency. Prepend name to content for the LLM
        # so it knows exactly who said what in a multi-turn history.
        processed_msg = dict(msg)
        
        # Phase 11: Systematic cleaning. Strip media tags from history.
        clean_content = _strip_media_tags(msg["content"])
        
        if msg.get("name") and not clean_content.startswith(f"[{msg['name']}]:"):
            processed_msg["content"] = f"[{msg['name']}]: {clean_content}"
        else:
            processed_msg["content"] = clean_content

        if msg["role"] == "user":
            if current_pair:
                turns.append(current_pair)
            current_pair = [processed_msg]
        elif msg["role"] == "assistant":
            current_pair.append(processed_msg)
            turns.append(current_pair)
            current_pair = []

    if current_pair:
        turns.append(current_pair)

    return turns


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
