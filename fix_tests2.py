import re

with open("tests/test_arbitrator.py", "r") as f:
    content = f.read()

# Fix multi-line streaming calls that failed
content = re.sub(
    r'arb_s\.process_turn\(\s*"s1",\s*1,\s*"go",\s*"sys",\s*\[\],\s*stream_token_callback=cb\s*\)',
    r'arb_s.process_turn("s1", 1, {"player": "go"}, "sys", [], stream_token_callback=cb)',
    content
)

content = re.sub(
    r'arb\.process_turn\(\s*"s1",\s*1,\s*"action",\s*"sys",\s*\[\],\s*stream_token_callback=cb\s*\)',
    r'arb.process_turn("s1", 1, {"player": "action"}, "sys", [], stream_token_callback=cb)',
    content
)

# Fix plot armor / hero action tests
content = re.sub(
    r'arb\.process_turn\(\s*"s1",\s*1,\s*"help me",\s*"sys",\s*\[\],\s*hero_action="I attack"\s*\)',
    r'arb.process_turn("s1", 1, {"player": "help me", "hero": "I attack"}, "sys", [], hero_entity_id="hero")',
    content
)

with open("tests/test_arbitrator.py", "w") as f:
    f.write(content)

with open("tests/test_session.py", "r") as f:
    s = f.read()
# Replace across multiple lines if needed
s = re.sub(r'decision = sess\._get_hero_decision\(hero_ent,\s*\[\],\s*"Attack the dragon"\)', 'decision = sess._get_hero_decision(hero_ent, [])', s)
with open("tests/test_session.py", "w") as f:
    f.write(s)
