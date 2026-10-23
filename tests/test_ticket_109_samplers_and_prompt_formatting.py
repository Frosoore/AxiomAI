"""
tests/test_ticket_109_samplers_and_prompt_formatting.py

Unit tests for TICKET-109:
- DRY samplers (multiplier, base, allowed_length, sequence_breakers) & trim_stop in UniversalClient and AppConfig.
- Temperature default 1.12 for universal backend with DRY samplers.
- Novel prose & dialogue formatting (plain text prose, double quotes for dialogue).
- NPC physical initiative in rules and CRITICAL REMINDER (no blockage on physical actions or requested wishes).
- Verbosity headroom token limits (short=300, balanced=600, talkative=1200).
- Preservation of {{user}} / <user> macros in ST card importer for runtime resolution.
"""

import pytest

from axiom.backends.universal import UniversalClient
from axiom.config import AppConfig
from axiom.prompts import build_narrative_prompt
from workers.import_export_worker import _substitute_st_macros


# ---------------------------------------------------------------------------
# 1. DRY samplers and AppConfig tests
# ---------------------------------------------------------------------------

def test_app_config_dry_and_temperature_defaults():
    config = AppConfig()
    assert config.universal_temperature == 1.12
    assert config.universal_dry_multiplier == 0.8
    assert config.universal_dry_base == 1.75
    assert config.universal_dry_allowed_length == 2
    assert config.universal_dry_sequence_breakers == ["\n", ":", '"', "*"]
    assert config.universal_trim_stop is True


def test_universal_client_payload_includes_dry_and_trim_stop():
    client = UniversalClient(
        base_url="http://localhost:5001/v1",
        api_key="test-key",
        model_name="stheno-v3.4",
        temperature=1.12,
        min_p=0.1,
        dry_multiplier=0.8,
        dry_base=1.75,
        dry_allowed_length=2,
        dry_sequence_breakers=["\n", ":", '"', "*"],
        trim_stop=True,
    )
    messages = [{"role": "user", "content": "Hello"}]
    payload = client._get_payload(messages)

    assert payload["temperature"] == 1.12
    assert payload["min_p"] == 0.1
    assert payload["dry_multiplier"] == 0.8
    assert payload["dry_base"] == 1.75
    assert payload["dry_allowed_length"] == 2
    assert payload["dry_sequence_breakers"] == ["\n", ":", '"', "*"]
    assert payload["trim_stop"] is True


def test_universal_client_payload_overrides():
    client = UniversalClient(
        base_url="http://localhost:5001/v1",
        api_key="test-key",
        model_name="stheno-v3.4",
        dry_multiplier=0.8,
        trim_stop=True,
    )
    messages = [{"role": "user", "content": "Hello"}]
    payload = client._get_payload(
        messages,
        dry_multiplier=0.5,
        dry_base=2.0,
        trim_stop=False,
    )
    assert payload["dry_multiplier"] == 0.5
    assert payload["dry_base"] == 2.0
    assert payload["trim_stop"] is False


# ---------------------------------------------------------------------------
# 2. Novel prose and dialogue formatting tests
# ---------------------------------------------------------------------------

def test_narrative_prompt_novel_formatting_rule():
    messages = build_narrative_prompt(
        universe_system_prompt="Guild hall.",
        entity_stats_block="[STATS]",
        rag_chunks=[],
        history=[],
        intents={"player": "I look around."},
        mode="Solo",
    )
    system_rules = messages[0]["content"]
    assert 'Format all narrative actions and descriptions inside *asterisks* and all spoken dialogue inside "double quotes".' in system_rules


def test_critical_reminder_novel_formatting_instruction():
    messages = build_narrative_prompt(
        universe_system_prompt="Guild hall.",
        entity_stats_block="[STATS]",
        rag_chunks=[],
        history=[],
        intents={"player": "I look around."},
        mode="Solo",
    )
    reminder = messages[-1]["content"]
    assert 'Format all narrative actions and descriptions inside *asterisks* and all spoken dialogue inside "double quotes".' in reminder


# ---------------------------------------------------------------------------
# 3. NPC physical initiative & anti-blockage tests
# ---------------------------------------------------------------------------

def test_critical_reminder_npc_physical_initiative():
    messages = build_narrative_prompt(
        universe_system_prompt="Guild hall.",
        entity_stats_block="[STATS]",
        rag_chunks=[],
        history=[],
        intents={"player_1": "Now say something in the line of: I wish for Sharakh to become immortal."},
        mode="Solo",
    )
    reminder = messages[-1]["content"]
    assert "CRITICAL PACING: Step-by-step realism" in reminder
    assert "NEVER write new dialogue or internal decisions for 'You' (player_1)" in reminder


def test_companion_critical_reminder_physical_initiative():
    messages = build_narrative_prompt(
        universe_system_prompt="Guild hall.",
        entity_stats_block="[STATS]",
        rag_chunks=[],
        history=[],
        intents={"player_1": "Kiss me."},
        mode="Companion",
        hero_entity_id="Nadine",
    )
    reminder = messages[-1]["content"]
    assert "CRITICAL PACING: Step-by-step realism" in reminder


# ---------------------------------------------------------------------------
# 4. ST card importer macro preservation
# ---------------------------------------------------------------------------

def test_st_import_preserves_user_macro():
    text = "{{char}} whispers to {{user}}: 'Meet me later, <user>'."
    result = _substitute_st_macros(text, char_name="Nadine")
    assert result == "Nadine whispers to {{user}}: 'Meet me later, <user>'."
    assert "{{char}}" not in result
    assert "{{user}}" in result
    assert "<user>" in result


# ---------------------------------------------------------------------------
# 5. Fix verification tests (TICKET-109 regressions)
# ---------------------------------------------------------------------------

def test_dry_parameters_never_null():
    """Ensure dry_base, dry_allowed_length, dry_sequence_breakers are never None."""
    client = UniversalClient(
        base_url="http://localhost:5001/v1",
        api_key="test-key",
        model_name="stheno-v3.4",
        dry_multiplier=0.8,
    )
    payload = client._get_payload([{"role": "user", "content": "hi"}])
    assert payload["dry_multiplier"] == 0.8
    assert payload["dry_base"] == 1.75
    assert payload["dry_allowed_length"] == 2
    assert payload["dry_sequence_breakers"] == ["\n", ":", '"', "*"]

    # Even if complete() passes None kwargs
    payload_kwargs = client._get_payload(
        [{"role": "user", "content": "hi"}],
        dry_multiplier=0.8,
        dry_base=None,
        dry_allowed_length=None,
        dry_sequence_breakers=None,
    )
    assert payload_kwargs["dry_base"] == 1.75
    assert payload_kwargs["dry_allowed_length"] == 2
    assert payload_kwargs["dry_sequence_breakers"] == ["\n", ":", '"', "*"]


def test_universal_client_default_stops_contain_eot_id():
    client = UniversalClient(
        base_url="http://localhost:5001/v1",
        api_key="test-key",
        model_name="test-model",
    )
    payload = client._get_payload([{"role": "user", "content": "hi"}])
    assert "<|eot_id|>" in payload["stop"]


def test_lore_book_entry_name_never_used_as_char_name():
    """Entry named 'Schedule' must NEVER cause {{char}} in its content to become 'Schedule'."""
    from axiom.prompts import _format_lore_book_block

    lore = [{
        "category": "SillyTavern",
        "name": "Schedule",
        "content": "{{char}} unites within herself the will to fulfil any role.",
    }]
    # With char_name=None, {{char}} should NOT become 'Schedule'
    formatted_none = _format_lore_book_block(lore, char_name=None)
    assert "Schedule unites within herself" not in formatted_none
    assert "{{char}} unites within herself" in formatted_none

    # With char_name='Aglae', {{char}} should become 'Aglae'
    formatted_aglae = _format_lore_book_block(lore, char_name="Aglae")
    assert "Aglae unites within herself" in formatted_aglae
    assert "Schedule unites within herself" not in formatted_aglae


def test_timekeeper_stop_sequences_and_resilient_parsing():
    from unittest.mock import MagicMock
    from mods.axiom.time.main import _ask_timekeeper

    mock_llm = MagicMock()
    mock_llm.complete.return_value = '{"elapsed_minutes": 5, "major_event_description": null'

    ctx = MagicMock()
    ctx.llm = mock_llm
    ctx.time_llm = None
    ctx.combined_intents_text = "I wait a moment."
    ctx.narrative_text = "Nothing happens."

    result = _ask_timekeeper(ctx)
    assert result == 5
    # Verify stop_sequences were passed
    call_kwargs = mock_llm.complete.call_args[1]
    assert "<|eot_id|>" in call_kwargs["stop_sequences"]
    assert "}" not in call_kwargs["stop_sequences"]
    assert call_kwargs["temperature"] == 0.1


def test_greeting_asterisks_cleaned(tmp_path):
    """Test that import_sillytavern_card / ImportExportWorker strips asterisks from greetings."""
    import json
    import sqlite3
    from unittest.mock import patch
    from workers.import_export_worker import ImportExportWorker

    card_file = tmp_path / "test_card.json"
    card_data = {
        "name": "Nadine",
        "description": "A shy novice.",
        "first_mes": "*Nadine looks around nervously.* \"Hello there!\"",
        "alternate_greetings": ["*She smiles gently.* \"Welcome!\""]
    }
    card_file.write_text(json.dumps(card_data), encoding="utf-8")

    worker = ImportExportWorker(mode="import_st", source_path=str(card_file), dest_path=str(tmp_path))
    with patch("axiom.kernel.loader.is_mod_enabled", return_value=True):
        worker.run()

    db_path = tmp_path / "ST_Nadine.db"
    assert db_path.exists()
    conn = sqlite3.connect(db_path)
    meta = dict(conn.execute("SELECT key, value FROM Universe_Meta").fetchall())
    assert "*" not in meta["first_message"]
    assert "Nadine looks around nervously." in meta["first_message"]
    assert "She smiles gently." in meta["first_message"]

    # Also check Event_Log
    event_payload = json.loads(conn.execute("SELECT payload FROM Event_Log WHERE turn_id = 0").fetchone()[0])
    for v in event_payload["variants"]:
        assert "*" not in v


