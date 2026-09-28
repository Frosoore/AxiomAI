"""tests/test_patching_system.py

Unit and integration tests for Phase 3: Le Système de Patches Outillés.
Validates:
1. @patchable decorator across BEFORE, AFTER, AROUND with ShortCircuit
2. Bytecode fallback (__code__ swapping) affecting references captured via 'from module import func'
3. Absolute reversibility via ctx.cleanup() (Rule D11)
4. Deterministic multi-mod patch ordering & priority resolution
5. Step-level freeze: PatchingDuringStepError raised during active turn step (Rule §6.2.3)
6. CLI commands (axiom mods patches & axiom mod validate)
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path
import pytest

from axiom.cli.mods_cmd import run_mod_validate, run_mods_patches
from axiom.kernel import (
    KernelRegistry,
    ModContext,
    PatchRecord,
    PatchType,
    PatchingDuringStepError,
    ShortCircuit,
    get_active_patches,
    patchable,
    register_patch,
    remove_patch,
    remove_patches_by_mod,
    step_patch_freeze,
)
from axiom.kernel.manifest import parse_manifest_string


# --- Test fixtures: Sample patchable function ---

@patchable("test.math:sample_add")
def sample_add(a: int, b: int) -> int:
    return a + b


@pytest.fixture(autouse=True)
def reset_patch_state():
    """Ensure clean patch state before and after each test."""
    from axiom.kernel.patcher import (
        _ACTIVE_PATCHES,
        _APPLIED_FALLBACKS,
        _ORIGINAL_CODES,
        _ORIGINAL_FUNCS,
        unlock_patching,
    )
    unlock_patching()
    for target in list(_APPLIED_FALLBACKS.keys()):
        mod, func_name, func = _APPLIED_FALLBACKS.pop(target)
        orig_code = _ORIGINAL_CODES.pop(target, None)
        _ORIGINAL_FUNCS.pop(target, None)
        if orig_code is not None:
            func.__code__ = orig_code
    _ACTIVE_PATCHES.clear()

    yield

    unlock_patching()
    for target in list(_APPLIED_FALLBACKS.keys()):
        mod, func_name, func = _APPLIED_FALLBACKS.pop(target)
        orig_code = _ORIGINAL_CODES.pop(target, None)
        _ORIGINAL_FUNCS.pop(target, None)
        if orig_code is not None:
            func.__code__ = orig_code
    _ACTIVE_PATCHES.clear()


def test_patchable_decorator_before_after_around_and_shortcircuit():
    """1. Test @patchable across before, after, around, and ShortCircuit."""
    reg = KernelRegistry()
    ctx = ModContext("mod.calculator", reg)

    # Base behavior without patches
    assert sample_add(10, 5) == 15

    # 1.1 BEFORE patch altering arguments
    def double_inputs(a, b):
        return ((a * 2, b * 2), {})

    ctx.patch("test.math:sample_add", PatchType.BEFORE, double_inputs, priority=100)
    assert sample_add(10, 5) == 30  # (10*2) + (5*2) = 30

    # 1.2 AFTER patch altering result
    def add_ten(result, a, b):
        return result + 10

    ctx.patch("test.math:sample_add", PatchType.AFTER, add_ten, priority=100)
    assert sample_add(10, 5) == 40  # 30 + 10 = 40

    # 1.3 AROUND patch wrapping call
    def multiply_around(next_func, a, b):
        r = next_func(a, b)
        return r * 2

    ctx.patch("test.math:sample_add", PatchType.AROUND, multiply_around, priority=100)
    # BEFORE: a=20, b=10
    # AROUND: r = next_func(20, 10) = 30; r * 2 = 60
    # AFTER: result + 10 = 60 + 10 = 70
    assert sample_add(10, 5) == 70

    # 1.4 ShortCircuit in BEFORE patch
    def bypass_computation(a, b):
        return ShortCircuit(999)

    record_short = register_patch("mod.short", "test.math:sample_add", PatchType.BEFORE, bypass_computation, priority=10)
    # Higher priority (10 < 100) runs first and short-circuits everything
    assert sample_add(10, 5) == 999

    # Remove short circuit and verify return to previous patched state
    remove_patch(record_short)
    assert sample_add(10, 5) == 70

    # Cleanup mod and verify total restoration of base function
    ctx.cleanup()
    assert sample_add(10, 5) == 15


def test_bytecode_swapping_fallback_preserves_object_identity(tmp_path: Path):
    """2. Test fallback bytecode swap on un-decorated functions, preserving 'from m import f' identity."""
    # Create a dummy module
    import types
    mod_code = """
def calculate_armor_reduction(damage: int, armor: int) -> int:
    return max(0, damage - armor)
"""
    mod_name = "test_armor_calc_module"
    fake_module = types.ModuleType(mod_name)
    exec(mod_code, fake_module.__dict__)
    sys.modules[mod_name] = fake_module

    try:
        from test_armor_calc_module import calculate_armor_reduction
        id_before = id(calculate_armor_reduction)

        # Baseline call
        assert calculate_armor_reduction(50, 20) == 30

        # Apply a patch to an un-decorated target
        target = f"{mod_name}:calculate_armor_reduction"

        def piercing_armor_patch(next_fn, damage, armor):
            # Ignore 50% of armor
            return next_fn(damage, armor // 2)

        reg = KernelRegistry()
        ctx = ModContext("mod.armor_pierce", reg)
        ctx.patch(target, PatchType.AROUND, piercing_armor_patch)

        # Function object identity must be STRICTLY preserved (Rule D8)
        assert id(calculate_armor_reduction) == id_before

        # Both the imported reference and the module attribute execute the trampoline!
        assert calculate_armor_reduction(50, 20) == 40  # 50 - 10 = 40
        assert fake_module.calculate_armor_reduction(50, 20) == 40

        # Full reversibility on cleanup
        ctx.cleanup()
        assert id(calculate_armor_reduction) == id_before
        assert calculate_armor_reduction(50, 20) == 30
        assert fake_module.calculate_armor_reduction(50, 20) == 30

    finally:
        sys.modules.pop(mod_name, None)


def test_absolute_reversibility_and_zero_residual_state():
    """3. Test that ctx.cleanup() restores functions with zero residual patches or leak."""
    reg = KernelRegistry()
    ctx1 = ModContext("mod.first", reg)
    ctx2 = ModContext("mod.second", reg)

    assert sample_add(5, 5) == 10

    ctx1.patch("test.math:sample_add", PatchType.AFTER, lambda res, a, b: res + 100)
    ctx2.patch("test.math:sample_add", PatchType.AFTER, lambda res, a, b: res * 2)

    assert sample_add(5, 5) == (10 + 100) * 2  # 220

    # Cleanup mod 1: mod 2 remains active
    ctx1.cleanup()
    assert sample_add(5, 5) == 10 * 2  # 20

    # Cleanup mod 2: pristine baseline restored
    ctx2.cleanup()
    assert sample_add(5, 5) == 10
    assert len(get_active_patches("test.math:sample_add")) == 0


def test_deterministic_multi_mod_priority_ordering():
    """4. Test that multiple competing patches execute in deterministic priority order."""
    reg = KernelRegistry()
    ctx_high = ModContext("mod.high_priority", reg)
    ctx_low = ModContext("mod.low_priority", reg)

    execution_order: list[str] = []

    def before_high(*args, **kwargs):
        execution_order.append("high_priority")
        return None

    def before_low(*args, **kwargs):
        execution_order.append("low_priority")
        return None

    # Register low priority (priority=150) before high priority (priority=50)
    ctx_low.patch("test.math:sample_add", PatchType.BEFORE, before_low, priority=150)
    ctx_high.patch("test.math:sample_add", PatchType.BEFORE, before_high, priority=50)

    sample_add(1, 2)

    # 50 must run before 150 regardless of registration sequence
    assert execution_order == ["high_priority", "low_priority"]

    ctx_high.cleanup()
    ctx_low.cleanup()


def test_step_level_freeze_raises_patching_during_step_error():
    """5. Test that attempting to patch or unpatch during step execution raises PatchingDuringStepError."""
    reg = KernelRegistry()
    ctx = ModContext("mod.dynamic", reg)

    # Within a frozen step execution
    with step_patch_freeze():
        # Attempting to register patch must fail
        with pytest.raises(PatchingDuringStepError, match="Patch stack is frozen"):
            ctx.patch("test.math:sample_add", PatchType.BEFORE, lambda a, b: None)

        # Attempting to remove patch must fail
        with pytest.raises(PatchingDuringStepError, match="Patch stack is frozen"):
            remove_patches_by_mod("mod.dynamic")

    # Outside the step freeze, patching succeeds normally
    ctx.patch("test.math:sample_add", PatchType.BEFORE, lambda a, b: None)
    assert len(get_active_patches("test.math:sample_add")) == 1
    ctx.cleanup()


def test_cli_patches_and_validate(tmp_path: Path, monkeypatch):
    """6. Test CLI 'axiom mods patches' and 'axiom mod validate'."""
    # 6.1 'axiom mods patches' output formatting
    reg = KernelRegistry()
    ctx = ModContext("comm.hardcore_plus", reg)
    ctx.patch("test.math:sample_add", PatchType.AROUND, lambda f, a, b: f(a, b), priority=50)

    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    ret = run_mods_patches(argparse.Namespace())
    assert ret == 0
    output = buf.getvalue()
    assert "test.math:sample_add" in output
    assert "around" in output
    assert "comm.hardcore_plus" in output
    assert "50" in output
    ctx.cleanup()

    # 6.2 'axiom mod validate' with valid declared patches
    valid_mod_dir = tmp_path / "valid_mod"
    valid_mod_dir.mkdir()
    (valid_mod_dir / "mod.toml").write_text(
        """[mod]
id = "comm.test_valid"
version = "1.0.0"
axiom_api = 1
name = "Valid Mod"

[contributes]
patches = [
    "axiom.kernel.patcher:get_active_patches"
]
""",
        encoding="utf-8",
    )

    buf_val = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf_val)
    ret_val = run_mod_validate(argparse.Namespace(mod_path=str(valid_mod_dir)))
    assert ret_val == 0
    assert "valid" in buf_val.getvalue().lower()

    # 6.3 'axiom mod validate' with invalid / unresolvable patch target
    invalid_mod_dir = tmp_path / "invalid_mod"
    invalid_mod_dir.mkdir()
    (invalid_mod_dir / "mod.toml").write_text(
        """[mod]
id = "comm.test_invalid"
version = "1.0.0"
axiom_api = 1
name = "Invalid Mod"

[contributes]
patches = [
    "non_existent_module:phantom_function"
]
""",
        encoding="utf-8",
    )

    buf_err = io.StringIO()
    monkeypatch.setattr(sys, "stderr", buf_err)
    ret_err = run_mod_validate(argparse.Namespace(mod_path=str(invalid_mod_dir)))
    assert ret_err == 1
    assert "cannot be resolved" in buf_err.getvalue()
