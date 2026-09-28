"""tests/test_world_turn_mods.py

Hermetic integration and acceptance tests for Phase 2:
- axiom.world (persistent world model, entities, stats, rules cascade)
- axiom.turn (turn orchestration pipeline, prompt assembly, output routing, filter chains)

Validates:
1. Declarative contracts and loading via directory and .axmod archive.
2. Proper registration of declared slots.
3. Third-party prompt section contribution to axiom.turn:prompt_sections without editing axiom.turn or kernel.
4. NoTurnPipelineInstalledError when no turn pipeline mod is active.
5. Stream filtering and final text filtering slot chains.
6. Custom output fields routing via axiom.turn:output_fields.
7. Full lifecycle turn execution with Session and ScriptedLLMBackend.
"""

from __future__ import annotations

from pathlib import Path
import pytest

import axiom.paths
from axiom.backends.base import LLMMessage, LLMResponse
from axiom.cli.mods_cmd import pack_mod
from axiom.compile import compile_universe
from axiom.kernel import (
    KernelRegistry,
    KernelStepContext,
    NoTurnPipelineInstalledError,
    SlotRule,
    load_manifest,
    load_mod,
    load_mod_from_archive,
    load_mod_from_dir,
    parse_manifest_file,
)
from axiom.savestore import create_save
from axiom.schema import get_connection
from axiom.session import Session
from axiom.testing.golden_harness import (
    ScriptedLLMBackend,
    ScriptedTurnResponse,
    SessionStateCanonicalizer,
)


class RecordingScriptedLLM(ScriptedLLMBackend):
    """ScriptedLLMBackend that records prompt messages sent to complete()."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.recorded_prompts: list[list[LLMMessage]] = []

    def complete(
        self,
        messages: list[LLMMessage],
        stream: bool = False,
        temperature: float = 0.7,
        top_p: float = 1.0,
        response_format: str | None = None,
        stop_sequences: list[str] | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        self.recorded_prompts.append(messages)
        return super().complete(
            messages,
            stream=stream,
            temperature=temperature,
            top_p=top_p,
            response_format=response_format,
            stop_sequences=stop_sequences,
            max_tokens=max_tokens,
        )


@pytest.fixture
def harness_env(tmp_path: Path):
    """Prepares an isolated game environment with compiled Myria universe and player entity."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    axiom.paths.configure(data_dir=data_dir)

    myria_src = Path(__file__).resolve().parent.parent / "universes" / "Myria"
    uni_db = compile_universe(myria_src, tmp_path / "myria.db", force=True)

    with get_connection(str(uni_db)) as conn:
        conn.execute(
            "INSERT INTO Entities (entity_id, entity_type, entity_role, name, is_active) "
            "VALUES ('player', 'player', 'player', 'Hero', 1);"
        )
        conn.execute(
            "INSERT INTO Entity_Stats (entity_id, stat_key, stat_value) VALUES "
            "('player', 'Health', '100'), "
            "('player', 'Arcane Focus', '100'), "
            "('player', 'Coin', '50'), "
            "('player', 'Location', 'gilded_compass');"
        )
        conn.commit()

    yield {
        "tmp_path": tmp_path,
        "uni_db": uni_db,
    }


def test_manifests_and_loading_directory_and_archive(tmp_path: Path):
    """A. Manifest parsing and loading for axiom.world and axiom.turn."""
    root = Path(__file__).resolve().parent.parent
    world_dir = root / "mods" / "axiom.world"
    turn_dir = root / "mods" / "axiom.turn"

    # Verify manifest parsing
    world_manifest = parse_manifest_file(world_dir / "mod.toml")
    assert world_manifest.id == "axiom.world"
    assert "axiom.step:gather_context" in world_manifest.contributes.hooks
    assert "axiom.step:arbitrate_mutations" in world_manifest.contributes.hooks
    assert "axiom.world:entity_types" in world_manifest.provides_slots
    assert "axiom.world:custom_rules" in world_manifest.provides_slots

    turn_manifest = parse_manifest_file(turn_dir / "mod.toml")
    assert turn_manifest.id == "axiom.turn"
    assert "axiom.kernel:execute_step" in turn_manifest.contributes.hooks
    assert "axiom.turn:prompt_sections" in turn_manifest.provides_slots
    assert "axiom.turn:output_fields" in turn_manifest.provides_slots
    assert "axiom.turn:stream_filter" in turn_manifest.provides_slots
    assert "axiom.turn:final_text_filter" in turn_manifest.provides_slots
    assert "axiom.turn:llm_backend" in turn_manifest.provides_slots

    # Load from directory
    reg_dir = KernelRegistry()
    world_m, _, _ = load_mod_from_dir(world_dir, reg_dir)
    turn_m, _, _ = load_mod_from_dir(turn_dir, reg_dir)
    assert world_m.id == "axiom.world"
    assert turn_m.id == "axiom.turn"
    assert reg_dir.has_hook("axiom.kernel:execute_step")
    assert reg_dir.has_hook("axiom.step:gather_context")

    # Pack to .axmod archives and load
    world_axmod = pack_mod(world_dir, tmp_path / "axiom.world.axmod")
    turn_axmod = pack_mod(turn_dir, tmp_path / "axiom.turn.axmod")

    reg_arch = KernelRegistry()
    world_arch_m, _, _ = load_mod_from_archive(world_axmod, reg_arch)
    turn_arch_m, _, _ = load_mod_from_archive(turn_axmod, reg_arch)
    assert world_arch_m.id == "axiom.world"
    assert turn_arch_m.id == "axiom.turn"
    assert reg_arch.has_hook("axiom.kernel:execute_step")
    assert reg_arch.has_hook("axiom.step:gather_context")


def test_third_party_prompt_section_contribution(harness_env):
    """B. Third-party mod contributes to axiom.turn:prompt_sections without editing axiom.turn or kernel."""
    env = harness_env
    save_info = create_save(env["uni_db"], "Hero", "Normal")
    save_id = save_info["save_id"]
    save_db = save_info["db_path"]

    llm = RecordingScriptedLLM([
        ScriptedTurnResponse(narrative_chunks=["You invoke the apprentice flame."], tool_call={}),
    ])

    registry = KernelRegistry()
    # Load official mods
    root = Path(__file__).resolve().parent.parent
    load_mod(root / "mods" / "axiom.world", registry)
    load_mod(root / "mods" / "axiom.turn", registry)

    # Register a third-party extension mod that contributes to prompt_sections slot
    from axiom.kernel.context import ModContext
    apprentice_ctx = ModContext("comm.magic_apprentice", registry)
    apprentice_ctx.contribute_slot(
        "axiom.turn:prompt_sections",
        {"position": "system", "text": "[MOD RULE: MAGIC APPRENTICE] Spells cost no mana in apprentice mode."},
    )

    session = Session(save_db, save_id, llm=llm, time_llm=llm, kernel_registry=registry)
    res = session.take_turn("Cast ember.")

    assert res.narrative_text == "You invoke the apprentice flame."
    assert len(llm.recorded_prompts) > 0
    # Check that the prompt sent to the LLM contains the third-party section
    all_prompts = " ".join(
        " ".join(msg.get("content", "") for msg in prompt)
        for prompt in llm.recorded_prompts
    )
    assert "[MOD RULE: MAGIC APPRENTICE] Spells cost no mana in apprentice mode." in all_prompts


def test_no_turn_pipeline_installed_error(harness_env):
    """C. Verify NoTurnPipelineInstalledError is raised when no turn pipeline mod is active."""
    env = harness_env
    save_info = create_save(env["uni_db"], "Hero", "Normal")
    save_id = save_info["save_id"]
    save_db = save_info["db_path"]

    empty_registry = KernelRegistry()
    llm = ScriptedLLMBackend([])
    session = Session(save_db, save_id, llm=llm, time_llm=llm, kernel_registry=empty_registry)

    with pytest.raises(NoTurnPipelineInstalledError):
        session.take_turn("Hello world")


def test_stream_filter_and_final_text_filter_slots(harness_env):
    """C. Verify stream_filter and final_text_filter slot chains."""
    env = harness_env
    save_info = create_save(env["uni_db"], "Hero", "Normal")
    save_id = save_info["save_id"]
    save_db = save_info["db_path"]

    llm = ScriptedLLMBackend([
        ScriptedTurnResponse(narrative_chunks=["hello", " ", "world"], tool_call={}),
    ])

    registry = KernelRegistry()
    root = Path(__file__).resolve().parent.parent
    load_mod(root / "mods" / "axiom.world", registry)
    load_mod(root / "mods" / "axiom.turn", registry)

    from axiom.kernel.context import ModContext
    filter_ctx = ModContext("test.filter_mod", registry)
    # Stream filter uppercases tokens
    filter_ctx.contribute_slot("axiom.turn:stream_filter", lambda token: token.upper())
    # Final text filter appends suffix
    filter_ctx.contribute_slot("axiom.turn:final_text_filter", lambda text: f"{text} [PROCESSED]")

    session = Session(save_db, save_id, llm=llm, time_llm=llm, kernel_registry=registry)

    streamed_tokens: list[str] = []
    res = session.take_turn("Explore", on_token=streamed_tokens.append)

    assert len(streamed_tokens) > 0
    assert "".join(streamed_tokens) == "HELLO WORLD"
    assert res.narrative_text == "hello world [PROCESSED]"


def test_output_fields_custom_routing(harness_env):
    """Verify custom output fields routing via axiom.turn:output_fields."""
    env = harness_env
    save_info = create_save(env["uni_db"], "Hero", "Normal")
    save_id = save_info["save_id"]
    save_db = save_info["db_path"]

    custom_field_payloads = []

    def handle_reputation_field(payload: Any, ctx: Any) -> None:
        custom_field_payloads.append(payload)
        # Apply custom delta
        ctx.applied_changes.append({
            "entity_id": "player",
            "stat_key": "Coin",
            "delta": payload.get("bounty_gold", 0),
        })

    registry = KernelRegistry()
    root = Path(__file__).resolve().parent.parent
    load_mod(root / "mods" / "axiom.world", registry)
    load_mod(root / "mods" / "axiom.turn", registry)

    from axiom.kernel.context import ModContext
    bounty_ctx = ModContext("test.bounty_mod", registry)
    bounty_ctx.contribute_slot("axiom.turn:output_fields", ("bounty_rewards", handle_reputation_field))

    llm = ScriptedLLMBackend([
        ScriptedTurnResponse(
            narrative_chunks=["You collect the guild reward."],
            tool_call={
                "bounty_rewards": {"bounty_gold": 15},
            },
        ),
    ])

    session = Session(save_db, save_id, llm=llm, time_llm=llm, kernel_registry=registry)
    res = session.take_turn("Claim bounty.")

    assert len(custom_field_payloads) == 1
    assert custom_field_payloads[0] == {"bounty_gold": 15}
    # Check that applied_changes has the custom delta
    assert any(c.get("stat_key") == "Coin" and c.get("delta") == 15 for c in res.applied_changes)


def test_world_turn_integration_state_mutations(harness_env):
    """D. End-to-end turn execution with axiom.world and axiom.turn validating mutations."""
    env = harness_env
    save_info = create_save(env["uni_db"], "Hero", "Normal")
    save_id = save_info["save_id"]
    save_db = save_info["db_path"]

    llm = ScriptedLLMBackend([
        ScriptedTurnResponse(
            narrative_chunks=["The battle tests your endurance."],
            tool_call={
                "state_changes": [
                    {"entity_id": "player", "stat_key": "Health", "delta": -25},
                    {"entity_id": "player", "stat_key": "Coin", "delta": 10},
                ],
            },
        ),
    ])

    session = Session(save_db, save_id, llm=llm, time_llm=llm)
    res = session.take_turn("Fight enemy")

    assert res.narrative_text == "The battle tests your endurance."
    assert session.turn_id == 1

    stats = session.current_stats()
    assert stats["player"]["Health"] == "75"
    assert stats["player"]["Coin"] == "60"
