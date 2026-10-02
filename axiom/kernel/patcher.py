"""axiom/kernel/patcher.py

Official Trampoline & Function Patching Engine for Axiom AI (Phase 3).
Enforces Rules D8 (Profound Internal Access), D9 (Safety & Visibility),
D11 (Strict Reversibility on Cleanup), and §6.2.3 (Step-level Freeze).

Targets:
- `@patchable("name")` functions (stable trampoline, preferred);
- `module:function`, `module.function` (bytecode fallback, object identity kept);
- `module:Class.method` (bytecode fallback on the method's function, also works for
  staticmethod/classmethod and for bound methods captured before the patch);
- closures (functions with free variables) are supported by the fallback as well.
A target that cannot be resolved or patched is refused with `PatchTargetError` and
nothing is added to the patch stack.

Order: lower `priority` first, then the mod load order (user order, §8), then
registration order. A handler that raises disables its mod's patches (same policy
as hooks, §6.1) and the call goes on without it.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
import functools
import importlib
import itertools
import threading
import types
from typing import Any, Callable

from axiom.logger import logger


class PatchType(Enum):
    """Execution interception modes for function patches."""

    BEFORE = "before"   # Runs before target function; can alter args or short-circuit
    AFTER = "after"     # Runs after target function; can alter return value
    AROUND = "around"   # Wraps original function call (receives next_func, *args, **kwargs)


_SEQ = itertools.count()


@dataclass(eq=False)
class PatchRecord:
    """Individual registered patch record."""

    mod_id: str
    target_name: str
    patch_type: PatchType
    handler: Callable[..., Any]
    priority: int = 100
    seq: int = 0


class ShortCircuit:
    """Sentinel value returned by a BEFORE patch to abort execution early with a result."""

    def __init__(self, value: Any = None) -> None:
        self.value = value


class PatchingDuringStepError(Exception):
    """Raised when registering or removing patches while a turn/step is executing (§6.2.3)."""


class PatchTargetError(ValueError):
    """Raised when a patch target cannot be resolved or cannot be patched."""


# Global patch state
_PATCHABLE_TARGETS: dict[str, Callable[..., Any]] = {}
_ORIGINAL_FUNCS: dict[str, Callable[..., Any]] = {}
_ORIGINAL_CODES: dict[str, types.CodeType] = {}
# target -> (owner module/class, attribute name, patched function object)
_APPLIED_FALLBACKS: dict[str, tuple[Any, str, Callable[..., Any]]] = {}
_ACTIVE_PATCHES: dict[str, list[PatchRecord]] = {}
# Mods whose patches are suspended (faulty, or disabled during a frozen step);
# their records are removed for good when the stack unfreezes.
_SUSPENDED_MODS: set[str] = set()
_MOD_RANK: dict[str, int] = {}
_FAULT_LISTENERS: list[Callable[[str, str], None]] = []

_freeze_lock = threading.RLock()
_freeze_depth: int = 0
# Kept for backward compatibility (read-only mirror of the freeze state).
_execution_locked: bool = False


def is_patching_locked() -> bool:
    """Check if the patch stack is currently frozen."""
    return _freeze_depth > 0


def lock_patching() -> None:
    """Freeze the patch stack (reentrant: each call must be matched by unlock_patching)."""
    global _freeze_depth, _execution_locked
    with _freeze_lock:
        _freeze_depth += 1
        _execution_locked = True


def unlock_patching() -> None:
    """Unfreeze one level of the patch stack; fully unfrozen -> apply deferred removals.

    Calling it while not frozen resets the state (used by tests).
    """
    global _freeze_depth, _execution_locked
    with _freeze_lock:
        _freeze_depth = max(0, _freeze_depth - 1)
        _execution_locked = _freeze_depth > 0
        if _freeze_depth == 0:
            for mod_id in sorted(_SUSPENDED_MODS):
                _remove_records(lambda r, m=mod_id: r.mod_id == m)


@contextmanager
def step_patch_freeze():
    """Context manager freezing the patch stack during turn execution (Rule §6.2.3).

    Reentrant: a nested freeze does not unfreeze the outer one on exit (m4).
    """
    lock_patching()
    try:
        yield
    finally:
        unlock_patching()


def set_patch_mod_order(order: list[str]) -> None:
    """Record the mod load order, used to order stacked patches of equal priority (§8)."""
    _MOD_RANK.clear()
    _MOD_RANK.update({mod_id: i for i, mod_id in enumerate(order)})


def add_patch_fault_listener(listener: Callable[[str, str], None]) -> None:
    """Register a callback(mod_id, reason) notified when a patch handler raises."""
    if listener not in _FAULT_LISTENERS:
        _FAULT_LISTENERS.append(listener)


def remove_patch_fault_listener(listener: Callable[[str, str], None]) -> None:
    if listener in _FAULT_LISTENERS:
        _FAULT_LISTENERS.remove(listener)


def patchable(target_name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator marking an official internal function as a patchable target.

    Places a stable and immutable trampoline on the target function.
    Convention: name it after the function, `"<module>:<qualname>"`.
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


def make_trampoline_code(target_name: str, freevars: tuple[str, ...] = ()) -> types.CodeType:
    """Generate a code object delegating to dispatch_patch.

    `freevars` reproduces the free variables of a closure so that the code can be
    assigned to its `__code__` (CPython requires the same number of free variables).
    """
    ident = hex(abs(hash(target_name)))[2:]
    if not freevars:
        src = (
            f"def _trampoline_{ident}(*__axiom_args, **__axiom_kwargs):\n"
            f"    from axiom.kernel.patcher import dispatch_patch\n"
            f"    return dispatch_patch({target_name!r}, *__axiom_args, **__axiom_kwargs)\n"
        )
        d: dict[str, Any] = {}
        exec(src, d)
        return d[f"_trampoline_{ident}"].__code__

    assigns = "\n".join(f"    {name} = None" for name in freevars)
    refs = "\n".join(f"            {name}" for name in freevars)
    src = (
        f"def _outer_{ident}():\n"
        f"{assigns}\n"
        f"    def _trampoline_{ident}(*__axiom_args, **__axiom_kwargs):\n"
        f"        if False:\n"
        f"{refs}\n"
        f"        from axiom.kernel.patcher import dispatch_patch\n"
        f"        return dispatch_patch({target_name!r}, *__axiom_args, **__axiom_kwargs)\n"
        f"    return _trampoline_{ident}\n"
    )
    d = {}
    exec(src, d)
    code = d[f"_outer_{ident}"]().__code__
    if code.co_freevars != tuple(freevars):
        # Fall back on the exact order of the target (count is what CPython checks).
        code = code.replace(co_freevars=tuple(freevars))
    return code


def _split_target(target: str) -> tuple[str, str]:
    """Split 'module:qual.name' or 'module.func' into (module_name, qualname)."""
    if ":" in target:
        mod_name, qualname = target.split(":", 1)
        if not mod_name or not qualname:
            raise PatchTargetError(f"Invalid patch target '{target}'.")
        return mod_name, qualname
    if "." in target:
        parts = target.split(".")
        # Longest importable module prefix wins: 'pkg.mod.Class.meth' -> ('pkg.mod', 'Class.meth')
        for i in range(len(parts) - 1, 0, -1):
            mod_name = ".".join(parts[:i])
            try:
                importlib.import_module(mod_name)
            except Exception:
                continue
            return mod_name, ".".join(parts[i:])
        raise PatchTargetError(f"No importable module found for patch target '{target}'.")
    raise PatchTargetError(
        f"Invalid patch target format '{target}'. Expected 'module:func', 'module:Class.method' or 'module.func'."
    )


def resolve_target(target: str) -> tuple[Any, str, Callable[..., Any]]:
    """Resolve a target string into (owner, attribute_name, callable).

    Accepted forms: 'module:func', 'module:Class.method', 'module.func'.
    `owner` is the module or the class holding the attribute.
    """
    mod_name, qualname = _split_target(target)
    try:
        owner: Any = importlib.import_module(mod_name)
    except Exception as err:
        raise PatchTargetError(f"Cannot import module '{mod_name}' for patch target '{target}': {err}") from err

    parts = qualname.split(".")
    for part in parts[:-1]:
        if not hasattr(owner, part):
            raise PatchTargetError(f"'{mod_name}' has no attribute path '{qualname}' (target '{target}').")
        owner = getattr(owner, part)
    attr = parts[-1]
    if not hasattr(owner, attr):
        raise PatchTargetError(f"Module '{mod_name}' has no attribute '{qualname}' for target '{target}'.")
    func = getattr(owner, attr)
    if not callable(func):
        raise PatchTargetError(f"Target '{target}' ({func!r}) is not callable.")
    return owner, attr, func


def _underlying_function(owner: Any, attr: str, func: Any) -> types.FunctionType:
    """Return the Python function object whose __code__ can be swapped, or raise."""
    raw = owner.__dict__.get(attr, func) if isinstance(owner, type) else func
    if isinstance(raw, (staticmethod, classmethod)):
        raw = raw.__func__
    if isinstance(raw, types.MethodType):
        raw = raw.__func__
    if isinstance(raw, type):
        raise PatchTargetError(f"Cannot patch a class ('{attr}'); target one of its methods.")
    if not isinstance(raw, types.FunctionType):
        raise PatchTargetError(
            f"'{attr}' ({type(raw).__name__}) is not a Python function (builtin/C functions cannot be patched)."
        )
    return raw


def _install_fallback(target: str) -> None:
    owner, attr, func = resolve_target(target)
    if getattr(func, "_is_patchable", False):
        _PATCHABLE_TARGETS[target] = getattr(func, "_orig_func", func)
        return
    fn = _underlying_function(owner, attr, func)
    if getattr(fn, "_is_patchable", False):
        _PATCHABLE_TARGETS[target] = getattr(fn, "_orig_func", fn)
        return
    code = fn.__code__
    tramp = make_trampoline_code(target, code.co_freevars)
    cloned = types.FunctionType(code, fn.__globals__, fn.__name__, fn.__defaults__, fn.__closure__)
    cloned.__kwdefaults__ = getattr(fn, "__kwdefaults__", None)
    cloned.__annotations__ = getattr(fn, "__annotations__", {})
    cloned.__qualname__ = fn.__qualname__
    try:
        fn.__code__ = tramp
    except (ValueError, TypeError) as err:
        raise PatchTargetError(f"Cannot install trampoline on '{target}': {err}") from err
    logger.warning("Target '%s' is not marked @patchable. Applied bytecode trampoline fallback.", target)
    _ORIGINAL_FUNCS[target] = cloned
    _ORIGINAL_CODES[target] = code
    _APPLIED_FALLBACKS[target] = (owner, attr, fn)


def _restore_fallback(target: str) -> None:
    if target in _APPLIED_FALLBACKS:
        _owner, _attr, func = _APPLIED_FALLBACKS.pop(target)
        orig_code = _ORIGINAL_CODES.pop(target, None)
        _ORIGINAL_FUNCS.pop(target, None)
        if orig_code is not None:
            func.__code__ = orig_code
            logger.debug("Restored original bytecode for target '%s'", target)


def register_patch(
    mod_id: str,
    target: str,
    patch_type: PatchType | str,
    handler: Callable[..., Any],
    priority: int = 100,
) -> PatchRecord:
    """Register a patch for an internal target function.

    If target is not marked @patchable, applies a __code__ bytecode trampoline fallback.

    Raises:
        PatchingDuringStepError: the patch stack is frozen (a step is running).
        PatchTargetError: the target does not exist or cannot be patched (nothing is registered).
    """
    if is_patching_locked():
        raise PatchingDuringStepError(
            f"Cannot register patch for '{target}' while a turn step is executing. "
            "Rule §6.2.3: Patch stack is frozen during step execution."
        )

    if isinstance(patch_type, str):
        patch_type = PatchType(patch_type.lower())
    if not callable(handler):
        raise PatchTargetError(f"Patch handler for '{target}' is not callable.")

    if target not in _PATCHABLE_TARGETS and target not in _ORIGINAL_FUNCS:
        try:
            _install_fallback(target)
        except PatchTargetError:
            raise
        except Exception as err:
            raise PatchTargetError(f"Cannot patch '{target}': {err}") from err

    record = PatchRecord(
        mod_id=mod_id,
        target_name=target,
        patch_type=patch_type,
        handler=handler,
        priority=priority,
        seq=next(_SEQ),
    )
    _SUSPENDED_MODS.discard(mod_id)
    _ACTIVE_PATCHES.setdefault(target, []).append(record)
    logger.debug(
        "Registered patch [%s] on '%s' from mod '%s' (priority %d)",
        patch_type.value,
        target,
        mod_id,
        priority,
    )
    return record


def _remove_records(predicate: Callable[[PatchRecord], bool]) -> None:
    for target in list(_ACTIVE_PATCHES.keys()):
        _ACTIVE_PATCHES[target] = [r for r in _ACTIVE_PATCHES[target] if not predicate(r)]
        if not _ACTIVE_PATCHES[target]:
            _ACTIVE_PATCHES.pop(target, None)
            _restore_fallback(target)


def remove_patch(record: PatchRecord) -> None:
    """Unregister an individual patch record."""
    if is_patching_locked():
        raise PatchingDuringStepError(
            f"Cannot remove patch for '{record.target_name}' while a turn step is executing. "
            "Rule §6.2.3: Patch stack is frozen during step execution."
        )
    _remove_records(lambda r: r is record)


def remove_patches_by_mod(mod_id: str) -> None:
    """Unregister all patches registered by a specific mod (Rule D11)."""
    if is_patching_locked():
        raise PatchingDuringStepError(
            f"Cannot remove patches for mod '{mod_id}' while a turn step is executing. "
            "Rule §6.2.3: Patch stack is frozen during step execution."
        )
    _SUSPENDED_MODS.discard(mod_id)
    _remove_records(lambda r: r.mod_id == mod_id)


def suspend_mod_patches(mod_id: str) -> None:
    """Deactivate a mod's patches immediately, even during a frozen step.

    The records stop being applied at once and are removed when the stack unfreezes.
    """
    _SUSPENDED_MODS.add(mod_id)
    if not is_patching_locked():
        _SUSPENDED_MODS.discard(mod_id)
        _remove_records(lambda r: r.mod_id == mod_id)


def _live_records(target: str) -> list[PatchRecord]:
    return [r for r in _ACTIVE_PATCHES.get(target, []) if r.mod_id not in _SUSPENDED_MODS]


def get_active_patches(target: str | None = None) -> list[PatchRecord]:
    """Retrieve active patch records (suspended ones excluded), optionally filtered by target."""
    if target is not None:
        return _live_records(target)
    all_patches: list[PatchRecord] = []
    for t in list(_ACTIVE_PATCHES):
        all_patches.extend(_live_records(t))
    return all_patches


def _order_key(r: PatchRecord) -> tuple[int, int, int]:
    return (r.priority, _MOD_RANK.get(r.mod_id, len(_MOD_RANK)), r.seq)


# Exceptions that are never treated as a mod fault (e.g. a user cancellation).
_PASSTHROUGH: list[type[BaseException]] = []


def add_passthrough_exception(exc_type: type[BaseException]) -> None:
    """Declare an exception type that patch handlers may raise without being disabled."""
    if exc_type not in _PASSTHROUGH:
        _PASSTHROUGH.append(exc_type)


def _fault(record: PatchRecord, err: Exception) -> None:
    reason = f"Patch handler on '{record.target_name}' raised {type(err).__name__}: {err}"
    logger.error("Faulty mod '%s': %s", record.mod_id, reason, exc_info=err)
    _SUSPENDED_MODS.add(record.mod_id)
    for listener in list(_FAULT_LISTENERS):
        try:
            listener(record.mod_id, reason)
        except Exception as lerr:  # never let a listener break the call
            logger.debug("Patch fault listener failed: %s", lerr)


def dispatch_patch(target: str, *args: Any, **kwargs: Any) -> Any:
    """Central trampoline dispatcher for patchable targets."""
    if target in _PATCHABLE_TARGETS:
        orig_func = _PATCHABLE_TARGETS[target]
    elif target in _ORIGINAL_FUNCS:
        orig_func = _ORIGINAL_FUNCS[target]
    else:
        raise RuntimeError(f"Cannot dispatch patch for unknown target: '{target}'")

    records = _live_records(target)
    if not records:
        return orig_func(*args, **kwargs)

    sorted_records = sorted(records, key=_order_key)
    before_patches = [r for r in sorted_records if r.patch_type == PatchType.BEFORE]
    around_patches = [r for r in sorted_records if r.patch_type == PatchType.AROUND]
    after_patches = [r for r in sorted_records if r.patch_type == PatchType.AFTER]

    current_args = args
    current_kwargs = kwargs

    # --- Step 1: BEFORE patches ---
    for record in before_patches:
        if record.mod_id in _SUSPENDED_MODS:
            continue
        try:
            res = record.handler(*current_args, **current_kwargs)
        except Exception as err:
            if _is_passthrough(err):
                raise
            _fault(record, err)
            continue
        if isinstance(res, ShortCircuit):
            return res.value
        elif isinstance(res, tuple) and len(res) == 2 and isinstance(res[0], tuple) and isinstance(res[1], dict):
            current_args, current_kwargs = res[0], res[1]

    # --- Step 2: AROUND patches + call chain ---
    inner_errors: list[BaseException] = []

    def call_orig(*a: Any, **kw: Any) -> Any:
        try:
            return orig_func(*a, **kw)
        except BaseException as err:
            inner_errors.append(err)
            raise

    call_chain = call_orig
    for record in reversed(around_patches):
        call_chain = _make_around_chain(record, call_chain, inner_errors)

    result = call_chain(*current_args, **current_kwargs)

    # --- Step 3: AFTER patches ---
    for record in after_patches:
        if record.mod_id in _SUSPENDED_MODS:
            continue
        try:
            new_result = record.handler(result, *current_args, **current_kwargs)
        except Exception as err:
            if _is_passthrough(err):
                raise
            _fault(record, err)
            continue
        if new_result is not None:
            result = new_result

    return result


def _is_passthrough(err: BaseException, inner_errors: list[BaseException] | None = None) -> bool:
    if inner_errors and any(err is e for e in inner_errors):
        return True
    return bool(_PASSTHROUGH) and isinstance(err, tuple(_PASSTHROUGH))


def _make_around_chain(
    record: PatchRecord,
    next_func: Callable[..., Any],
    inner_errors: list[BaseException],
) -> Callable[..., Any]:
    def _wrapped(*a: Any, **kw: Any) -> Any:
        if record.mod_id in _SUSPENDED_MODS:
            return next_func(*a, **kw)
        state: dict[str, Any] = {}

        def _next(*na: Any, **nkw: Any) -> Any:
            state["result"] = next_func(*na, **nkw)
            return state["result"]

        try:
            return record.handler(_next, *a, **kw)
        except Exception as err:
            if _is_passthrough(err, inner_errors):
                raise
            _fault(record, err)
            if "result" in state:
                return state["result"]
            return next_func(*a, **kw)
    return _wrapped
