"""Unit tests for community.survival."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from axiom.kernel.context import ModContext
from axiom.kernel.manifest import parse_manifest_file
from axiom.kernel.registry import KernelRegistry


def test_community_survival_initialization() -> None:
    """Verify that community.survival initializes properly in an isolated ModContext."""
    mod_root = Path(__file__).resolve().parent.parent
    manifest = parse_manifest_file(mod_root / "mod.toml")

    assert manifest.id == "community.survival"
    assert manifest.axiom_api == 1
    assert "axiom.turn:prompt_sections" in manifest.contributes.slots
    assert "axiom.step:gather_context" in manifest.contributes.hooks
    assert "axiom.step:after_step" in manifest.contributes.hooks

    registry = KernelRegistry()
    ctx = ModContext(manifest, registry)

    spec = importlib.util.spec_from_file_location("mod_main", mod_root / "main.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert hasattr(module, "init") and callable(module.init)
    module.init(ctx)

    # 1. Verify slot contribution
    sections = registry.get_slot_contributions("axiom.turn:prompt_sections")
    assert len(sections) == 1
    builder = sections[0]
    section_data = builder(None)
    assert section_data["position"] == "system"
    assert "SURVIVAL GUIDELINES" in section_data["text"]

    # 2. Verify after_step hook effectivity on sustained exertion
    from axiom.turn_batch import TurnWriteBatch

    class DummyTurnCtx:
        def __init__(self, elapsed: int):
            self.save_id = "save_1"
            self.turn_id = 5
            self.new_time = 300
            self.elapsed_minutes = elapsed
            self.player_entity_id = "hero"
            self.write_batch = TurnWriteBatch()

    # Short activity: no fatigue entry
    short_ctx = DummyTurnCtx(30)
    registry.execute_hook("axiom.step:after_step", short_ctx)
    assert short_ctx.write_batch.events == []

    # Sustained activity (>= 120 mins): fatigue entry added
    long_ctx = DummyTurnCtx(150)
    registry.execute_hook("axiom.step:after_step", long_ctx)
    events = long_ctx.write_batch.events
    assert len(events) == 1
    assert events[0]["event_type"] == "mod.community.survival.fatigue"
    assert events[0]["target_entity"] == "hero"
    assert "Survival" in events[0]["payload"]["note"]

    # 3. Clean up and ensure unregistration (Rule D11)
    ctx.cleanup()
    assert len(registry.get_slot_contributions("axiom.turn:prompt_sections")) == 0
    assert not registry.has_hook("axiom.step:after_step")
