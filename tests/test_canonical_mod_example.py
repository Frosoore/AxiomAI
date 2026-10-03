"""tests/test_canonical_mod_example.py

Tests the canonical main.py mod example published in the documentation (README.md,
docs/guides/mods.md, SYNTHESE_ARCHITECTURE.md).

Verifies:
1. The exact canonical example executes without any exception.
2. Prompt section contribution is collected and parsed as expected.
3. Output field handler stages the event into TurnWriteBatch.
4. Function patch intercepts the @patchable target.
5. Strict reversibility: ctx.cleanup() restores original behavior cleanly.
"""

from __future__ import annotations

import pytest

from axiom.arbitrator import TurnContext
from axiom.prompts import build_narrative_prompt
from axiom.kernel.context import ModContext
from axiom.kernel.manifest import ModManifest, ModOrdering
from axiom.kernel.registry import KernelRegistry
from axiom.turn_batch import TurnWriteBatch


def canonical_init(ctx: ModContext) -> None:
    """The exact canonical main.py template published in documentation."""
    # 1. Contribute to turn prompt
    def inject_prompt(step_ctx):
        return ("system", 50, "Special rule: The player is thirsty.")
    ctx.contribute_slot("axiom.turn:prompt_sections", inject_prompt)

    # 2. Intercept LLM outputs
    def handle_output(data, turn_ctx):
        turn_ctx.write_batch.stage_event("thirst_update", {"value": 10})
    ctx.contribute_slot("axiom.turn:output_fields", {"thirst_level": handle_output})

    # 3. Reversible surgical patch if needed (D11)
    def patch_prompt(orig_fn, *args, **kwargs):
        messages = orig_fn(*args, **kwargs)
        messages[0]["content"] += "\n(Scorching Desert)"
        return messages
    ctx.patch("axiom.prompts:build_narrative_prompt", "around", patch_prompt)


def test_canonical_mod_example_execution():
    registry = KernelRegistry()
    registry.declare_slot("axiom.turn:prompt_sections")
    registry.declare_slot("axiom.turn:output_fields")

    manifest = ModManifest(
        id="community.thirst",
        name="Thirst Example",
        version="1.0.0",
        axiom_api=1,
        ordering=ModOrdering(),
    )
    ctx = ModContext(manifest, registry)

    def system_prompt() -> str:
        return build_narrative_prompt("SYS", "", [], [], {"player": "Hello"})[0]["content"]

    # Base behavior before mod initialization
    assert "(Scorching Desert)" not in system_prompt()

    # 1. Initialize the canonical mod
    canonical_init(ctx)

    # 2. Verify patch takes effect on @patchable target
    assert system_prompt().endswith("\n(Scorching Desert)")

    # 3. Verify prompt section contribution
    entries = registry.get_slot_contributions("axiom.turn:prompt_sections")
    assert len(entries) == 1
    func = entries[0]
    section_tuple = func(None)
    assert section_tuple == ("system", 50, "Special rule: The player is thirsty.")

    # 4. Verify output fields handler and TurnWriteBatch.stage_event
    out_entries = registry.get_slot_contributions("axiom.turn:output_fields")
    assert len(out_entries) == 1
    field_dict = out_entries[0]
    assert "thirst_level" in field_dict
    handler = field_dict["thirst_level"]

    dummy_turn_ctx = TurnContext(
        save_id="test_save",
        step_id=1,
        user_input="test",
        player_entity_id="player",
        verbosity="balanced",
    )
    handler({"thirst": 10}, dummy_turn_ctx)
    staged = dummy_turn_ctx.write_batch.events
    assert len(staged) == 1
    assert staged[0]["event_type"] == "thirst_update"
    assert staged[0]["payload"] == {"value": 10}

    # 5. Clean up mod (D11 reversibility)
    ctx.cleanup()

    # Verify patch is uninstalled
    assert "(Scorching Desert)" not in system_prompt()

    # Verify slots are cleaned
    assert len(registry.get_slot_contributions("axiom.turn:prompt_sections")) == 0
    assert len(registry.get_slot_contributions("axiom.turn:output_fields")) == 0


# ---------------------------------------------------------------------------
# The example AS PUBLISHED, installed as a real mod and played in a real turn
# (audit 2026-10-03: calling the functions by hand would pass even if the turn
# ignored the section or the output field).
# ---------------------------------------------------------------------------

import re
import textwrap
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_DOCS = [
    "README.md",
    "docs/guides/mods.md",
    "docs/guides/mods.en.md",
    "docs/guides/mods.fr.md",
    "maintenance/Mods/SYNTHESE_ARCHITECTURE.md",
    "maintenance/Mods/SYNTHESIS_ARCHITECTURE.en.md",
]


def _published_example(doc: str) -> str:
    text = (_ROOT / doc).read_text(encoding="utf-8")
    m = re.search(
        r"```python\n(from axiom\.kernel\.context import ModContext\n\ndef init\(ctx: ModContext\).*?)```",
        text, re.S,
    )
    assert m, f"canonical example not found in {doc}"
    return m.group(1)


@pytest.mark.parametrize("doc", _DOCS)
def test_published_example_works_in_a_real_turn(doc, tmp_path):
    from axiom.backends.base import LLMResponse
    from axiom.config import AppConfig
    from axiom.db_helpers import create_new_save
    from axiom.events import EventSourcer
    from axiom.kernel import bootstrap_all_mods
    from axiom.schema import create_universe_db
    from axiom.session import Session
    from tests.test_turn_pipeline_b2 import _ScriptLLM

    code = _published_example(doc)
    section_text = re.search(r'return \("system", 50, "([^"]+)"\)', code).group(1)
    field = re.search(r'\{"(\w+)": handle_output\}', code).group(1)
    event_type = re.search(r'stage_event\("(\w+)"', code).group(1)

    mod_dir = tmp_path / "mods" / "community.example"
    mod_dir.mkdir(parents=True)
    (mod_dir / "mod.toml").write_text(textwrap.dedent("""
        [mod]
        id = "community.example"
        version = "1.0.0"
        axiom_api = 1
        name = "Example"
        [dependencies]
        "axiom.turn" = ">=1.0.0"
        [contributes]
        slots = ["axiom.turn:prompt_sections", "axiom.turn:output_fields"]
        patches = ["axiom.prompts:build_narrative_prompt"]
    """), encoding="utf-8")
    (mod_dir / "main.py").write_text(code, encoding="utf-8")
    registry = bootstrap_all_mods(KernelRegistry(), AppConfig(), extra_dirs=[tmp_path / "mods"])
    try:
        db = str(tmp_path / "world.db")
        create_universe_db(db)
        save_id = create_new_save(db, player_name="Hero", difficulty="Normal")
        llm = _ScriptLLM(LLMResponse("x", {"elapsed_minutes": 5}, "stop"))
        sess = Session(db, save_id, llm=llm, time_llm=llm, kernel_registry=registry)
        llm.queue(LLMResponse("You drink.", {"elapsed_minutes": 5, field: 3}, "stop"))

        result = sess.take_turn("I look for water.")

        prompt = llm.prompt_text(0)
        assert result.faulted_mods == {}
        assert section_text in prompt                      # 1. section reached the prompt
        assert field in prompt                             # field requested in the JSON schema
        assert "(Scorching Desert)" in prompt              # 3. patch applied to the turn
        events = EventSourcer(db).get_events(save_id)
        assert any(e["event_type"] == event_type and e["turn_id"] == 1 for e in events)  # 2. committed
    finally:
        # A mod with patches only stops at next launch: undo its context by hand so
        # the patch does not leak into the next tests.
        ctx = registry.load_state.contexts.get("community.example")
        if ctx is not None:
            ctx.cleanup()
        assert "(Scorching Desert)" not in build_narrative_prompt("SYS", "", [], [], {"player": "Hi"})[0]["content"]
