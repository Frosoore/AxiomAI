import re

with open("tests/test_arbitrator.py", "r") as f:
    c = f.read()

# 1. Replace player_entity_id
c = re.sub(
    r'(arb.*?\.process_turn\(\s*"s1",\s*\d+,\s*)"([^"]+)",\s*"([^"]+)",\s*\[\],\s*player_entity_id="([^"]+)"',
    r'\1{"\4": "\2"}, "\3", []',
    c
)

# 2. Replace basic calls
c = re.sub(
    r'(arb.*?\.process_turn\(\s*"s1",\s*\d+,\s*)"([^"]+)",\s*"([^"]+)",\s*\[\]\s*\)',
    r'\1{"player": "\2"}, "\3", [])',
    c
)

# 3. Handle multi-line streaming calls
c = c.replace(
    'arb.process_turn(\n            "s1", 1, "action", "sys", [],\n            stream_token_callback=cb\n        )',
    'arb.process_turn(\n            "s1", 1, {"player": "action"}, "sys", [],\n            stream_token_callback=cb\n        )'
)
c = c.replace(
    'arb_s.process_turn(\n            "s1", 1, "go", "sys", [],\n            stream_token_callback=cb\n        )',
    'arb_s.process_turn(\n            "s1", 1, {"player": "go"}, "sys", [],\n            stream_token_callback=cb\n        )'
)

# 4. Handle Companion calls
c = c.replace(
    'arb.process_turn(\n            "s1", 1, "help me", "sys", [],\n            hero_action="I attack"\n        )',
    'arb.process_turn(\n            "s1", 1, {"player": "help me", "hero": "I attack"}, "sys", [],\n            hero_entity_id="hero"\n        )'
)

c = c.replace(
    'arb.process_turn(\n            "s1", 2, "wait", "sys", [],\n            hero_action="I wait",\n            mode="Companion"\n        )',
    'arb.process_turn(\n            "s1", 2, {"player": "wait", "hero": "I wait"}, "sys", [],\n            hero_entity_id="hero",\n            mode="Companion"\n        )'
)

c = c.replace(
    'arb.process_turn(\n            "s1", 1, "companion action", "sys", [],\n            hero_action="Hero charges forward!",\n            mode="Companion",\n            hero_entity_id="hero1"\n        )',
    'arb.process_turn(\n            "s1", 1, {"player": "companion action", "hero1": "Hero charges forward!"}, "sys", [],\n            mode="Companion",\n            hero_entity_id="hero1"\n        )'
)

# 5. Handle any remaining player_entity_id that wasn't caught
c = re.sub(
    r'(arb.*?\.process_turn\(\s*"s1",\s*\d+,\s*)"([^"]+)",\s*([^,]+),\s*\[\],\s*player_entity_id="([^"]+)"\)',
    r'\1{"\4": "\2"}, \3, [])',
    c
)

with open("tests/test_arbitrator.py", "w") as f:
    f.write(c)

with open("tests/test_session.py", "r") as f:
    s = f.read()
s = s.replace('decision = sess._get_hero_decision(hero_ent, [], "Attack the dragon")', 'decision = sess._get_hero_decision(hero_ent, [])')
with open("tests/test_session.py", "w") as f:
    f.write(s)
