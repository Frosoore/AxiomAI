"""tests/test_kernel_patch_targets.py

Patch targets and patch policy (review 2026-10-03, 1-NOYAU B2, m2, m3, m4, m10;
4-DOC I1(3); 3-MODS minor "ctx.patch on a missing target accepted"):
- methods (`module:Class.method`, staticmethod, classmethod, super()) and closures;
- unknown / unpatchable targets refused loudly, nothing in the stack;
- `axiom mods patches` never lists an inactive patch;
- a handler that raises disables its mod's patches, the call goes on;
- the freeze is reentrant; equal priorities follow the mod load order.
"""

from __future__ import annotations

import argparse
import io
import sys
import types

import pytest

from axiom.kernel import (
    KernelRegistry,
    ModContext,
    PatchTargetError,
    PatchType,
    PatchingDuringStepError,
    get_active_patches,
    register_patch,
    step_patch_freeze,
)
from axiom.kernel.patcher import is_patching_locked, set_patch_mod_order, unlock_patching

MOD_SRC = '''
class Base:
    def greet(self):
        return "base"


class Hero(Base):
    bonus = 1

    def attack(self, x):
        return x + self.bonus

    def greet(self):
        return "hero+" + super().greet()

    @staticmethod
    def scale(x):
        return x * 2

    @classmethod
    def kind(cls):
        return cls.__name__


def make_counter(start):
    step = 10

    def counter(x):
        return x + start + step
    return counter


closed = make_counter(1)


def plain(x):
    return x
'''


@pytest.fixture
def tgt(monkeypatch):
    mod = types.ModuleType("tgt_patch_mod")
    exec(MOD_SRC, mod.__dict__)
    monkeypatch.setitem(sys.modules, "tgt_patch_mod", mod)
    unlock_patching()
    yield mod
    while is_patching_locked():
        unlock_patching()
    from axiom.kernel.patcher import _ACTIVE_PATCHES, _remove_records
    _remove_records(lambda r: True)
    assert not _ACTIVE_PATCHES


def test_method_targets_and_restore(tgt):
    hero = tgt.Hero()
    bound_before = hero.attack  # captured before the patch
    ctx = ModContext("m.methods", KernelRegistry())

    ctx.patch("tgt_patch_mod:Hero.attack", PatchType.AROUND, lambda nxt, self, x: nxt(self, x) * 100)
    ctx.patch("tgt_patch_mod:Hero.scale", PatchType.AFTER, lambda res, x: res + 1)
    ctx.patch("tgt_patch_mod:Hero.kind", PatchType.AFTER, lambda res, cls: res.upper())
    ctx.patch("tgt_patch_mod:Hero.greet", PatchType.AFTER, lambda res, self: res + "!")

    assert hero.attack(3) == 400
    assert bound_before(3) == 400
    assert tgt.Hero.scale(5) == 11
    assert tgt.Hero.kind() == "HERO"
    assert hero.greet() == "hero+base!"  # super() closure (__class__ cell) works
    assert {r.target_name for r in get_active_patches()} >= {"tgt_patch_mod:Hero.attack", "tgt_patch_mod:Hero.greet"}

    ctx.cleanup()
    assert hero.attack(3) == 4
    assert tgt.Hero.scale(5) == 10
    assert tgt.Hero.kind() == "Hero"
    assert hero.greet() == "hero+base"
    assert get_active_patches() == []


def test_dotted_method_target_and_closure(tgt):
    ctx = ModContext("m.closure", KernelRegistry())
    ctx.patch("tgt_patch_mod.Hero.attack", PatchType.AFTER, lambda res, self, x: -res)
    assert tgt.Hero().attack(1) == -2

    captured = tgt.closed
    ctx.patch("tgt_patch_mod:closed", PatchType.AFTER, lambda res, x: -1)
    assert captured(5) == -1
    ctx.cleanup()
    assert captured(5) == 16


@pytest.mark.parametrize("target", [
    "tgt_patch_mod:does_not_exist",
    "tgt_patch_mod:Hero.nope",
    "axiom.world:calculate_stamina",
    "no_such_module_xyz:func",
    "tgt_patch_mod:Hero",          # a class is not a function
    "tgt_patch_mod:Hero.bonus",    # not callable
    "builtins:len",                # C function
    "nodot",
])
def test_unpatchable_targets_are_refused_loudly(tgt, target):
    ctx = ModContext("m.bad", KernelRegistry())
    with pytest.raises(PatchTargetError):
        ctx.patch(target, PatchType.BEFORE, lambda *a, **k: None)
    assert get_active_patches() == []
    assert ctx._registered_patches == []


def test_mods_patches_never_lists_inactive(tgt, monkeypatch):
    from axiom.cli.mods_cmd import run_mods_patches

    ctx = ModContext("m.cli", KernelRegistry())
    with pytest.raises(PatchTargetError):
        ctx.patch("tgt_patch_mod:missing", PatchType.BEFORE, lambda *a: None)
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    monkeypatch.setattr("axiom.cli.mods_cmd.discover_installed_mods", lambda *a, **k: [])
    assert run_mods_patches(argparse.Namespace(load=False)) == 0
    assert "tgt_patch_mod:missing" not in buf.getvalue()
    assert "No active function patch" in buf.getvalue()


def test_faulty_handler_disables_mod_patches_and_call_goes_on(tgt):
    reg = KernelRegistry()
    bad = ModContext("m.faulty", reg)
    good = ModContext("m.good", reg)
    faults = []
    from axiom.kernel.patcher import add_patch_fault_listener, remove_patch_fault_listener
    listener = lambda mod_id, reason: faults.append((mod_id, reason))  # noqa: E731
    add_patch_fault_listener(listener)
    try:
        bad.patch("tgt_patch_mod:plain", PatchType.AROUND, lambda nxt, x: 1 / 0)
        good.patch("tgt_patch_mod:plain", PatchType.AFTER, lambda res, x: res + 1)
        assert tgt.plain(1) == 2  # the faulty around is skipped, the original + good patch run
        assert faults and faults[0][0] == "m.faulty"
        assert [r.mod_id for r in get_active_patches()] == ["m.good"]

        # an exception of the patched function itself is not blamed on a patch
        def boom(x):
            raise KeyError("inner")
        tgt.boomer = boom
        good.patch("tgt_patch_mod:boomer", PatchType.AROUND, lambda nxt, x: nxt(x))
        with pytest.raises(KeyError):
            tgt.boomer(1)
        assert [m for m, _ in faults] == ["m.faulty"]
    finally:
        remove_patch_fault_listener(listener)
        bad.cleanup()
        good.cleanup()


def test_freeze_is_reentrant(tgt):
    with step_patch_freeze():
        with step_patch_freeze():
            pass
        assert is_patching_locked()
        with pytest.raises(PatchingDuringStepError):
            register_patch("m.x", "tgt_patch_mod:plain", PatchType.BEFORE, lambda x: None)
    assert not is_patching_locked()


def test_cleanup_during_frozen_step_deactivates_then_removes(tgt):
    ctx = ModContext("m.frozen", KernelRegistry())
    ctx.patch("tgt_patch_mod:plain", PatchType.AFTER, lambda res, x: res * 10)
    with step_patch_freeze():
        ctx.cleanup()  # e.g. mod disabled by a fault during the step: no exception
        assert tgt.plain(2) == 2
        assert get_active_patches() == []
    assert tgt.plain(2) == 2


def test_equal_priority_follows_load_order(tgt):
    order = []
    a = ModContext("o.a", KernelRegistry())
    b = ModContext("o.b", KernelRegistry())
    a.patch("tgt_patch_mod:plain", PatchType.BEFORE, lambda x: order.append("a"))
    b.patch("tgt_patch_mod:plain", PatchType.BEFORE, lambda x: order.append("b"))
    set_patch_mod_order(["o.b", "o.a"])
    try:
        tgt.plain(1)
        assert order == ["b", "a"]
    finally:
        set_patch_mod_order([])
        a.cleanup()
        b.cleanup()


def test_engine_patchable_entry_points():
    """Verify that key engine functions are decorated with @patchable and can be patched."""
    from axiom.kernel.patcher import ShortCircuit
    from axiom.prompts import build_narrative_prompt
    from axiom.db_helpers import get_spatial_context
    from mods.axiom.time.time_prompts import build_timekeeper_prompt
    from mods.axiom.time.time_system import get_time_of_day_context
    from axiom.regenerate import regenerate_variant

    ctx = ModContext("mod.engine_patches", KernelRegistry())

    # 1. Patch get_time_of_day_context
    ctx.patch("mods.axiom.time.time_system:get_time_of_day_context", PatchType.AFTER, lambda res, total: f"{res} [MODDED]")
    assert get_time_of_day_context(0).endswith("[MODDED]")

    # 2. Patch build_timekeeper_prompt
    ctx.patch(
        "mods.axiom.time.time_prompts:build_timekeeper_prompt",
        PatchType.AFTER,
        lambda msgs, action, narrative: msgs + [{"role": "system", "content": "EXTRA_TIMEKEEPER_RULE"}],
    )
    tk_msgs = build_timekeeper_prompt("run", "he ran")
    assert any(m.get("content") == "EXTRA_TIMEKEEPER_RULE" for m in tk_msgs)

    # 3. Patch build_narrative_prompt
    ctx.patch(
        "axiom.prompts:build_narrative_prompt",
        PatchType.AFTER,
        lambda msgs, *args, **kwargs: msgs + [{"role": "system", "content": "EXTRA_NARRATIVE_RULE"}],
    )
    narrative_msgs = build_narrative_prompt(
        universe_system_prompt="sys",
        entity_stats_block="",
        rag_chunks=[],
        history=[],
        intents={"player": "look"},
    )
    assert any(m.get("content") == "EXTRA_NARRATIVE_RULE" for m in narrative_msgs)

    # 4. Patch get_spatial_context
    ctx.patch(
        "axiom.db_helpers:get_spatial_context",
        PatchType.AFTER,
        lambda res, db_path, loc_id: {**res, "custom_landmark": "Ancient Monolith"},
    )
    spatial = get_spatial_context("", "loc_1")
    assert spatial.get("custom_landmark") == "Ancient Monolith"

    # 5. Patch regenerate_variant with ShortCircuit
    ctx.patch(
        "axiom.regenerate:regenerate_variant",
        PatchType.BEFORE,
        lambda *args, **kwargs: ShortCircuit("Short-circuited variant"),
    )
    reg_res = regenerate_variant(None, "", "s1", 1, [], "", "hello")
    assert reg_res == "Short-circuited variant"

    # Clean up all patches and verify full restoration
    ctx.cleanup()
    assert not get_time_of_day_context(0).endswith("[MODDED]")
    assert not any(m.get("content") == "EXTRA_TIMEKEEPER_RULE" for m in build_timekeeper_prompt("run", "he ran"))
    assert not any(
        m.get("content") == "EXTRA_NARRATIVE_RULE"
        for m in build_narrative_prompt(
            universe_system_prompt="sys",
            entity_stats_block="",
            rag_chunks=[],
            history=[],
            intents={"player": "look"},
        )
    )
    assert "custom_landmark" not in get_spatial_context("", "loc_1")
