import re

def process_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # Pattern for process_turn with player_entity_id at the end
    # Example: arb.process_turn("s1", 1, "I wait.", "sys", [], player_entity_id="player1")
    # -> arb.process_turn("s1", 1, {"player1": "I wait."}, "sys", [])
    
    # We will do a generic replacement for process_turn that extracts the message
    
    # First, handle calls with player_entity_id
    content = re.sub(
        r'arb(?:\w*)\.process_turn\(\s*"s1",\s*(\d+),\s*"([^"]*)",\s*"sys"(?:,\s*\[\])?,\s*player_entity_id="([^"]*)"\s*\)',
        r'arb\g<0>.process_turn("s1", \1, {"\3": "\2"}, "sys", [])',
        content
    )
    
    content = re.sub(
        r'arb(?:\w*)\.process_turn\(\s*"s1",\s*(\d+),\s*"([^"]*)",\s*"Universe prompt"(?:,\s*\[\])?,\s*player_entity_id="([^"]*)"\s*\)',
        r'arb\g<0>.process_turn("s1", \1, {"\3": "\2"}, "Universe prompt", [])',
        content
    )

    # Then handle calls without player_entity_id (defaults to "player")
    content = re.sub(
        r'arb(?:\w*)\.process_turn\(\s*"s1",\s*(\d+),\s*"([^"]*)",\s*"sys"(?:,\s*\[\])?\s*\)',
        r'arb.process_turn("s1", \1, {"player": "\2"}, "sys", [])',
        content
    )
    
    content = re.sub(
        r'arb(?:\w*)\.process_turn\(\s*"s1",\s*(\d+),\s*"([^"]*)",\s*"Universe prompt"(?:,\s*\[\])?\s*\)',
        r'arb.process_turn("s1", \1, {"player": "\2"}, "Universe prompt", [])',
        content
    )

    # Handle the multi-line calls
    content = re.sub(
        r'arb(?:\w*)\.process_turn\(\s*"s1",\s*1,\s*"action",\s*"sys",\s*\[\],\s*stream_token_callback=cb\s*\)',
        r'arb.process_turn("s1", 1, {"player": "action"}, "sys", [], stream_token_callback=cb)',
        content
    )
    
    content = re.sub(
        r'arb_s\.process_turn\(\s*"s1",\s*1,\s*"go",\s*"sys",\s*\[\],\s*stream_token_callback=cb\s*\)',
        r'arb_s.process_turn("s1", 1, {"player": "go"}, "sys", [], stream_token_callback=cb)',
        content
    )

    # Handle Companion mode tests specifically
    content = re.sub(
        r'arb\.process_turn\(\s*"s1",\s*1,\s*"help me",\s*"sys",\s*\[\],\s*hero_action="I attack"\s*\)',
        r'arb.process_turn("s1", 1, {"player": "help me", "hero": "I attack"}, "sys", [], hero_entity_id="hero")',
        content
    )

    content = re.sub(
        r'arb\.process_turn\(\s*"s1",\s*2,\s*"wait",\s*"sys",\s*\[\],\s*hero_action="I wait",\s*mode="Companion"\s*\)',
        r'arb.process_turn("s1", 2, {"player": "wait", "hero": "I wait"}, "sys", [], mode="Companion", hero_entity_id="hero")',
        content
    )

    with open(filepath, 'w') as f:
        f.write(content)

process_file("tests/test_arbitrator.py")
