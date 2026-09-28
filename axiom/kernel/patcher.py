"""axiom/kernel/patcher.py

Official Trampoline & Function Patching Engine for Axiom AI (Phase 3).
Enforces Rules D8 (Profound Internal Access), D9 (Safety & Visibility),
D11 (Strict Reversibility on Cleanup), and §6.2.3 (Step-level Freeze).
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
import functools
import types
from typing import Any, Callable

from axiom.logger import logger


class PatchType(Enum):
    """Execution interception modes for function patches."""

    BEFORE = "before"   # Runs before target function; can alter args or short-circuit
    AFTER = "after"     # Runs after target function; can alter return value
    AROUND = "around"   # Wraps original function call (receives next_func, *args, **kwargs)


@dataclass
class PatchRecord:
    """Individual registered patch record."""

    mod_id: str
    target_name: str
    patch_type: PatchType
    handler: Callable[..., Any]
    priority: int = 100


class ShortCircuit:
    """Sentinel value returned by a BEFORE patch to abort execution early with a result."""

    def __init__(self, value: Any = None) -> None:
        self.value = value


class PatchingDuringStepError(Exception):
    """Raised when registering or removing patches while a turn/step is executing (§6.2.3)."""


# Global patch state
_PATCHABLE_TARGETS: dict[str, Callable[..., Any]] = {}
_ORIGINAL_FUNCS: dict[str, Callable[..., Any]] = {}
_ORIGINAL_CODES: dict[str, types.CodeType] = {}
_APPLIED_FALLBACKS: dict[str, tuple[Any, str, Callable[..., Any]]] = {}
_ACTIVE_PATCHES: dict[str, list[PatchRecord]] = {}
_execution_locked: bool = False


def is_patching_locked() -> bool:
    """Check if the patch stack is currently frozen."""
    return _execution_locked


def lock_patching() -> None:
    """Freeze the patch stack."""
    global _execution_locked
    _execution_locked = True


def unlock_patching() -> None:
    """Unfreeze the patch stack."""
    global _execution_locked
    _execution_locked = False


@contextmanager
def step_patch_freeze():
    """Context manager freezing the patch stack during turn execution (Rule §6.2.3)."""
    global _execution_locked
    _execution_locked = True
    try:
        yield
    finally:
        _execution_locked = False


def patchable(target_name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator marking an official internal function as a patchable target.

    Places a stable and immutable trampoline on the target function.
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        _PATCHABLE_TARGETS[target_name] = func

        @functools.wraps(func)
        def trampoline(*args: Any, **kwargs: Any) -> Any:
            return dispatch_patch(target_name, *args, **kwargs)

        trampoline._is_patchable = True  # type: ignore[attr-defined]
        trampoline._patchable_target = target_name  # type: ignore[attr-defined]
        trampoline._orig_func = func  # type: ignore[attr-defined]
        return trampoline

    return decorator


def make_trampoline_code(target_name: str) -> types.CodeType:
    """Generate a zero-freevar code object delegating to dispatch_patch."""
    ident = hex(abs(hash(target_name)))[2:]
    src = f"""
def _trampoline_{ident}(*args, **kwargs):
    from axiom.kernel.patcher import dispatch_patch
    return dispatch_patch({repr(target_name)}, *args, **kwargs)
"""
    d: dict[str, Any] = {}
    exec(src, d)
    func = next(v for k, v in d.items() if k.startswith("_trampoline_"))
    return func.__code__


def resolve_target(target: str) -> tuple[Any, str, Callable[..., Any]]:
    """Resolve a target string ('module:func' or 'module.func') into (module, func_name, callable)."""
    if ":" in target:
        mod_name, func_name = target.split(":", 1)
    elif "." in target:
        mod_name, func_name = target.rsplit(".", 1)
    else:
        raise ValueError(f"Invalid patch target format '{target}'. Expected 'module:func' or 'module.func'.")

    import importlib
    mod = importlib.import_module(mod_name)
    if not hasattr(mod, func_name):
        raise AttributeError(f"Module '{mod_name}' has no attribute '{func_name}' for target '{target}'.")
    func = getattr(mod, func_name)
    if not callable(func):
        raise TypeError(f"Target '{target}' ({func}) is not callable.")
    return mod, func_name, func


def register_patch(
    mod_id: str,
    target: str,
    patch_type: PatchType | str,
    handler: Callable[..., Any],
    priority: int = 100,
) -> PatchRecord:
    """Register a patch for an internal target function.

    If target is not marked @patchable, applies a __code__ bytecode trampoline fallback.
    """
    global _execution_locked
    if _execution_locked:
        raise PatchingDuringStepError(
            f"Cannot register patch for '{target}' while a turn step is executing. "
            "Rule §6.2.3: Patch stack is frozen during step execution."
        )

    if isinstance(patch_type, str):
        patch_type = PatchType(patch_type.lower())

    record = PatchRecord(
        mod_id=mod_id,
        target_name=target,
        patch_type=patch_type,
        handler=handler,
        priority=priority,
    )

    # If target function is not already prepared with trampoline
    if target not in _PATCHABLE_TARGETS and target not in _ORIGINAL_FUNCS:
        try:
            mod, func_name, func = resolve_target(target)
            if getattr(func, "_is_patchable", False):
                _PATCHABLE_TARGETS[target] = getattr(func, "_orig_func", func)
            else:
                logger.warning(
                    "Target '%s' is not marked @patchable. Applied bytecode trampoline fallback.",
                    target,
                )
                cloned = types.FunctionType(
                    func.__code__,
                    func.__globals__,
                    func.__name__,
                    func.__defaults__,
                    func.__closure__,
                )
                cloned.__kwdefaults__ = getattr(func, "__kwdefaults__", None)
                cloned.__annotations__ = getattr(func, "__annotations__", {})
                _ORIGINAL_FUNCS[target] = cloned
                _ORIGINAL_CODES[target] = func.__code__
                _APPLIED_FALLBACKS[target] = (mod, func_name, func)
                func.__code__ = make_trampoline_code(target)
        except Exception as err:
            logger.error("Failed to resolve or install trampoline fallback for target '%s': %s", target, err)

    records = _ACTIVE_PATCHES.setdefault(target, [])
    records.append(record)
    logger.debug(
        "Registered patch [%s] on '%s' from mod '%s' (priority %d)",
        patch_type.value,
        target,
        mod_id,
        priority,
    )
    return record


def remove_patch(record: PatchRecord) -> None:
    """Unregister an individual patch record."""
    global _execution_locked
    if _execution_locked:
        raise PatchingDuringStepError(
            f"Cannot remove patch for '{record.target_name}' while a turn step is executing. "
            "Rule §6.2.3: Patch stack is frozen during step execution."
        )

    target = record.target_name
    if target in _ACTIVE_PATCHES:
        _ACTIVE_PATCHES[target] = [r for r in _ACTIVE_PATCHES[target] if r != record]
        if not _ACTIVE_PATCHES[target]:
            _ACTIVE_PATCHES.pop(target, None)
            if target in _APPLIED_FALLBACKS:
                mod, func_name, func = _APPLIED_FALLBACKS.pop(target)
                orig_code = _ORIGINAL_CODES.pop(target, None)
                _ORIGINAL_FUNCS.pop(target, None)
                if orig_code is not None:
                    func.__code__ = orig_code
                    logger.debug("Restored original bytecode for target '%s'", target)


def remove_patches_by_mod(mod_id: str) -> None:
    """Unregister all patches registered by a specific mod (Rule D11)."""
    global _execution_locked
    if _execution_locked:
        raise PatchingDuringStepError(
            f"Cannot remove patches for mod '{mod_id}' while a turn step is executing. "
            "Rule §6.2.3: Patch stack is frozen during step execution."
        )

    targets_to_check = list(_ACTIVE_PATCHES.keys())
    for target in targets_to_check:
        _ACTIVE_PATCHES[target] = [r for r in _ACTIVE_PATCHES[target] if r.mod_id != mod_id]
        if not _ACTIVE_PATCHES[target]:
            _ACTIVE_PATCHES.pop(target, None)
            if target in _APPLIED_FALLBACKS:
                mod, func_name, func = _APPLIED_FALLBACKS.pop(target)
                orig_code = _ORIGINAL_CODES.pop(target, None)
                _ORIGINAL_FUNCS.pop(target, None)
                if orig_code is not None:
                    func.__code__ = orig_code
                    logger.debug("Restored original bytecode for target '%s'", target)


def get_active_patches(target: str | None = None) -> list[PatchRecord]:
    """Retrieve active patch records, optionally filtered by target."""
    if target is not None:
        return list(_ACTIVE_PATCHES.get(target, []))
    all_patches: list[PatchRecord] = []
    for records in _ACTIVE_PATCHES.values():
        all_patches.extend(records)
    return all_patches


def dispatch_patch(target: str, *args: Any, **kwargs: Any) -> Any:
    """Central trampoline dispatcher for patchable targets."""
    # 1. Resolve original function
    if target in _PATCHABLE_TARGETS:
        orig_func = _PATCHABLE_TARGETS[target]
    elif target in _ORIGINAL_FUNCS:
        orig_func = _ORIGINAL_FUNCS[target]
    else:
        try:
            _, _, orig_func = resolve_target(target)
        except Exception:
            raise RuntimeError(f"Cannot dispatch patch for unknown target: '{target}'")

    records = _ACTIVE_PATCHES.get(target, [])
    if not records:
        return orig_func(*args, **kwargs)

    # Sort deterministically: lower priority first, stable preservation of insertion order
    sorted_records = sorted(records, key=lambda r: r.priority)

    before_patches = [r for r in sorted_records if r.patch_type == PatchType.BEFORE]
    around_patches = [r for r in sorted_records if r.patch_type == PatchType.AROUND]
    after_patches = [r for r in sorted_records if r.patch_type == PatchType.AFTER]

    current_args = args
    current_kwargs = kwargs

    # --- Step 1: BEFORE patches ---
    for record in before_patches:
        res = record.handler(*current_args, **current_kwargs)
        if isinstance(res, ShortCircuit):
            return res.value
        elif isinstance(res, tuple) and len(res) == 2 and isinstance(res[0], tuple) and isinstance(res[1], dict):
            current_args, current_kwargs = res[0], res[1]

    # --- Step 2: AROUND patches + call chain ---
    call_chain = orig_func
    for record in reversed(around_patches):
        handler = record.handler
        next_fn = call_chain
        call_chain = _make_around_chain(handler, next_fn)

    result = call_chain(*current_args, **current_kwargs)

    # --- Step 3: AFTER patches ---
    for record in after_patches:
        new_result = record.handler(result, *current_args, **current_kwargs)
        if new_result is not None:
            result = new_result

    return result


def _make_around_chain(handler: Callable[..., Any], next_func: Callable[..., Any]) -> Callable[..., Any]:
    def _wrapped(*a: Any, **kw: Any) -> Any:
        return handler(next_func, *a, **kw)
    return _wrapped
