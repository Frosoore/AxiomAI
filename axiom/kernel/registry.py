"""axiom/kernel/registry.py

Kernel Registry for official extension points (hooks and slots).
Provides fault-tolerant execution with exception isolation and rule-based slots.

Fault policy (§6.1): when a hook callback or a chain contribution raises, its
contribution is ignored, the mod is disabled (its ModContext is cleaned up) and the
fault is reported (`get_faulted_mods()`, fault listeners); the step goes on.
Exceptions: hooks declared *critical* (e.g. `axiom.kernel:execute_step`) and calls
made through `invoke_hook_unguarded()` let the exception propagate without disabling
anything; a cancellation (`GenerationCancelled`) always propagates.

Exclusive slots keep every candidate: the winner is the first one in the mod order
(§8) and the others are visible through `get_slot_conflicts()`.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import Any

from axiom.backends.base import GenerationCancelled
from axiom.logger import logger


class SlotRule(Enum):
    """Aggregation rules for slots (extension point containers)."""

    EXCLUSIVE = "exclusive"  # One contribution wins (first in mod order); others are candidates
    CHAIN = "chain"          # Pipeline where each contribution transforms the value
    COLLECT = "collect"      # Accumulates all contributions into a list


class RegistryError(Exception):
    """Raised on registry conflicts or invalid operations."""


# Hooks whose exceptions must reach the caller (not a mod bug: e.g. LLM unreachable).
DEFAULT_CRITICAL_HOOKS: tuple[str, ...] = ("axiom.kernel:execute_step",)

_PROPAGATE: tuple[type[BaseException], ...] = (GenerationCancelled,)

try:  # a cancellation raised inside a patch handler is not a mod fault either
    from axiom.kernel.patcher import add_passthrough_exception as _add_passthrough
    _add_passthrough(GenerationCancelled)
except Exception:  # pragma: no cover
    pass


_ACTIVE_REGISTRY: KernelRegistry | None = None


def get_active_registry() -> KernelRegistry | None:
    """Return the currently active KernelRegistry, or None."""
    return _ACTIVE_REGISTRY


def set_active_registry(registry: KernelRegistry | None) -> None:
    """Set the active KernelRegistry instance."""
    global _ACTIVE_REGISTRY
    _ACTIVE_REGISTRY = registry


class KernelRegistry:
    """Central registry for hooks, slots, and extension points."""

    def __init__(self) -> None:
        # hook_name -> list of (mod_id, callback)
        self._hooks: dict[str, list[tuple[str, Callable[..., Any]]]] = {}
        # slot_name -> SlotRule
        self._slot_rules: dict[str, SlotRule] = {}
        # slot_name -> mod_id that declared it (None = kernel)
        self._slot_owners: dict[str, str | None] = {}
        # slot_name -> list of (mod_id, contribution)
        self._slot_contributions: dict[str, list[tuple[str, Any]]] = {}
        # service_name -> (mod_id, service_instance)
        self._services: dict[str, tuple[str, Any]] = {}
        # mod_id -> ModContext (latest one created for this registry)
        self._contexts: dict[str, Any] = {}
        # mod_id -> reason (mods disabled at runtime after a fault)
        self._faulted: dict[str, str] = {}
        self._fault_listeners: list[Callable[[str, str], None]] = []
        self._critical_hooks: set[str] = set(DEFAULT_CRITICAL_HOOKS)
        # mod_id -> rank in the load order (user order under constraints, §8)
        self._mod_rank: dict[str, int] = {}
        # Set by the loader (axiom.kernel.loader.ModLoadState) after a bootstrap.
        self.load_state: Any = None

        # Standardized kernel slots (§9 & ARBITRAGE.md)
        self.declare_slot("axiom.kernel:locales", SlotRule.COLLECT)
        self.declare_slot("axiom.kernel:help_entries", SlotRule.COLLECT)

        global _ACTIVE_REGISTRY
        _ACTIVE_REGISTRY = self

    # ------------------------------------------------------------------
    # Mod order, contexts and faults
    # ------------------------------------------------------------------

    def set_mod_order(self, order: list[str]) -> None:
        """Record the load order; it orders slot contributions and picks exclusive winners."""
        self._mod_rank = {mod_id: i for i, mod_id in enumerate(order)}

    def _ordered(self, entries: list[tuple[str, Any]]) -> list[tuple[str, Any]]:
        if not self._mod_rank:
            return list(entries)
        default = len(self._mod_rank)
        return sorted(entries, key=lambda e: self._mod_rank.get(e[0], default))

    def attach_context(self, ctx: Any) -> None:
        """Called by ModContext: lets the registry disable the mod properly on a fault."""
        self._contexts[ctx.mod_id] = ctx
        self._faulted.pop(ctx.mod_id, None)

    def add_fault_listener(self, listener: Callable[[str, str], None]) -> None:
        """Register a callback(mod_id, reason) called after a mod is disabled for a fault."""
        if listener not in self._fault_listeners:
            self._fault_listeners.append(listener)

    def get_faulted_mods(self) -> dict[str, str]:
        """Mods disabled at runtime after raising, with the reason."""
        return dict(self._faulted)

    def declare_critical_hook(self, hook_name: str) -> None:
        """Declare a hook whose exceptions propagate to the caller (no isolation, no disabling)."""
        self._critical_hooks.add(hook_name)

    def is_critical_hook(self, hook_name: str) -> bool:
        return hook_name in self._critical_hooks

    def purge_mod(self, mod_id: str) -> None:
        """Remove every hook, slot contribution, slot declaration and service of a mod."""
        for name in list(self._hooks):
            self.remove_hook(name, mod_id)
        for name in list(self._slot_contributions):
            self.remove_slot_contribution(name, mod_id)
        for name, owner in list(self._slot_owners.items()):
            if owner == mod_id:
                self.undeclare_slot(name, mod_id)
        for name, (owner, _svc) in list(self._services.items()):
            if owner == mod_id:
                del self._services[name]

    def disable_mod(self, mod_id: str, reason: str) -> None:
        """Disable a mod at runtime: cleanup of its context (hooks, slots, services,
        patches, jobs), then notify the fault listeners (cascade, UI, CLI)."""
        if mod_id in self._faulted:
            return
        self._faulted[mod_id] = reason
        ctx = self._contexts.get(mod_id)
        if ctx is not None:
            try:
                ctx.cleanup()
            except Exception as err:
                logger.error("Cleanup of faulty mod '%s' failed: %s", mod_id, err, exc_info=True)
        self.purge_mod(mod_id)
        logger.error("Mod '%s' has been disabled: %s", mod_id, reason)
        for listener in list(self._fault_listeners):
            try:
                listener(mod_id, reason)
            except Exception as err:
                logger.error("Fault listener failed for mod '%s': %s", mod_id, err, exc_info=True)

    def report_fault(self, mod_id: str, where: str, err: Exception) -> None:
        """Public entry for callers that run a mod contribution themselves (e.g. a turn
        pipeline calling prompt sections one by one): the mod is disabled and reported
        exactly as for a faulty hook (§6.1)."""
        self._on_fault(mod_id, where, err)

    def _on_fault(self, mod_id: str, where: str, err: Exception) -> None:
        logger.error(
            "Faulty mod '%s' raised an exception in %s: %s",
            mod_id,
            where,
            err,
            exc_info=True,
        )
        self.disable_mod(mod_id, f"Raised {type(err).__name__} in {where}: {err}")

    # ------------------------------------------------------------------
    # Hook Management
    # ------------------------------------------------------------------

    def add_hook(self, hook_name: str, mod_id: str, callback: Callable[..., Any]) -> None:
        """Register a callback for a hook from a specific mod."""
        callbacks = self._hooks.setdefault(hook_name, [])
        callbacks.append((mod_id, callback))

    def remove_hook(self, hook_name: str, mod_id: str) -> None:
        """Remove all callbacks registered for a hook by a specific mod."""
        if hook_name in self._hooks:
            self._hooks[hook_name] = [
                (mid, cb) for mid, cb in self._hooks[hook_name] if mid != mod_id
            ]

    def invoke_hook(self, hook_name: str, *args: Any, **kwargs: Any) -> list[Any]:
        """Invoke all callbacks registered for a hook with exception isolation.

        If a callback raises, its error is logged, its mod is disabled and reported,
        and the other callbacks still run (§6.1). Critical hooks propagate instead
        (see `invoke_hook_unguarded`).

        Returns:
            List of return values from successfully executed callbacks.
        """
        if hook_name in self._critical_hooks:
            return self.invoke_hook_unguarded(hook_name, *args, **kwargs)
        results: list[Any] = []
        for mod_id, callback in self._ordered(list(self._hooks.get(hook_name, []))):
            if mod_id in self._faulted or not self._still_registered(hook_name, mod_id, callback):
                continue  # disabled meanwhile (fault cascade during this very call)
            try:
                res = callback(*args, **kwargs)
                results.append(res)
            except _PROPAGATE:
                raise
            except Exception as err:
                self._on_fault(mod_id, f"hook '{hook_name}'", err)
        return results

    def _still_registered(self, hook_name: str, mod_id: str, callback: Callable[..., Any]) -> bool:
        return any(m == mod_id and cb is callback for m, cb in self._hooks.get(hook_name, []))

    # Alias matching kernel dispatch naming conventions
    def execute_hook(self, hook_name: str, *args: Any, **kwargs: Any) -> list[Any]:
        return self.invoke_hook(hook_name, *args, **kwargs)

    def invoke_hook_unguarded(self, hook_name: str, *args: Any, **kwargs: Any) -> list[Any]:
        """Invoke a hook without safety net: the first exception propagates to the
        caller unchanged and no mod is disabled. Meant for critical calls such as
        `axiom.kernel:execute_step`, whose errors (LLM unreachable...) must reach the UI."""
        results: list[Any] = []
        for mod_id, callback in self._ordered(list(self._hooks.get(hook_name, []))):
            if mod_id in self._faulted:
                continue
            results.append(callback(*args, **kwargs))
        return results

    def has_hook(self, hook_name: str) -> bool:
        """Check if any callbacks are registered for a given hook."""
        return any(mid not in self._faulted for mid, _ in self._hooks.get(hook_name, []))

    # ------------------------------------------------------------------
    # Slot Management
    # ------------------------------------------------------------------

    def declare_slot(
        self,
        slot_name: str,
        rule: SlotRule = SlotRule.COLLECT,
        mod_id: str | None = None,
    ) -> None:
        """Declare an official slot with an aggregation rule (mod_id = declaring mod)."""
        self._slot_rules[slot_name] = rule
        self._slot_owners.setdefault(slot_name, mod_id)

    def undeclare_slot(self, slot_name: str, mod_id: str) -> None:
        """Remove a slot declaration made by `mod_id` (contributions of others are kept)."""
        if self._slot_owners.get(slot_name) == mod_id:
            self._slot_owners.pop(slot_name, None)
            self._slot_rules.pop(slot_name, None)

    def get_slot_rule(self, slot_name: str) -> SlotRule:
        return self._slot_rules.get(slot_name, SlotRule.COLLECT)

    def add_to_slot(self, slot_name: str, mod_id: str, contribution: Any) -> None:
        """Contribute an object, widget, or handler to an official slot.

        On an EXCLUSIVE slot every candidate is kept; the first in mod order wins
        and the conflict is visible through `get_slot_conflicts()`.
        """
        contributions = self._slot_contributions.setdefault(slot_name, [])
        if self.get_slot_rule(slot_name) == SlotRule.EXCLUSIVE:
            others = {mid for mid, _ in contributions if mid != mod_id}
            if others:
                logger.info(
                    "Exclusive slot '%s': mod '%s' is a candidate next to %s (first in mod order wins).",
                    slot_name,
                    mod_id,
                    sorted(others),
                )
        contributions.append((mod_id, contribution))

    def remove_slot_contribution(self, slot_name: str, mod_id: str) -> None:
        """Remove contributions made to a slot by a specific mod."""
        if slot_name in self._slot_contributions:
            self._slot_contributions[slot_name] = [
                (mid, c) for mid, c in self._slot_contributions[slot_name] if mid != mod_id
            ]

    def _live_contributions(self, slot_name: str) -> list[tuple[str, Any]]:
        return self._ordered(
            [(mid, c) for mid, c in self._slot_contributions.get(slot_name, []) if mid not in self._faulted]
        )

    def get_slot(self, slot_name: str) -> Any:
        """Retrieve aggregated contributions for a slot according to its rule."""
        rule = self.get_slot_rule(slot_name)
        contributions = [c for _, c in self._live_contributions(slot_name)]

        if rule == SlotRule.EXCLUSIVE:
            return contributions[0] if contributions else None
        return list(contributions)

    def get_slot_contributions(self, slot_name: str) -> list[Any]:
        """Return raw list of contributed values for a slot (in mod order)."""
        return [c for _, c in self._live_contributions(slot_name)]

    def get_slot_entries(self, slot_name: str) -> list[tuple[str, Any]]:
        """(mod_id, contribution) pairs of a slot in mod order, for callers that need to
        attribute a faulty contribution to its mod (see `report_fault`)."""
        return list(self._live_contributions(slot_name))

    def get_slot_contributors(self, slot_name: str) -> list[str]:
        """Return the ids of the mods contributing to a slot, in mod order (first = winner)."""
        seen: list[str] = []
        for mid, _ in self._live_contributions(slot_name):
            if mid not in seen:
                seen.append(mid)
        return seen

    def get_slot_conflicts(self) -> dict[str, list[str]]:
        """EXCLUSIVE slots claimed by several mods -> [mod ids in order]; the first wins (§8, D13)."""
        conflicts: dict[str, list[str]] = {}
        for slot_name in self._slot_contributions:
            if self.get_slot_rule(slot_name) != SlotRule.EXCLUSIVE:
                continue
            mods = self.get_slot_contributors(slot_name)
            if len(mods) > 1:
                conflicts[slot_name] = mods
        return conflicts

    def apply_slot_chain(self, slot_name: str, initial_value: Any, *args: Any, **kwargs: Any) -> Any:
        """Run a pipeline of CHAIN contributions on initial_value with exception isolation."""
        val = initial_value
        for mid, func in self._live_contributions(slot_name):
            if mid in self._faulted or not callable(func):
                continue
            try:
                val = func(val, *args, **kwargs)
            except _PROPAGATE:
                raise
            except Exception as err:
                self._on_fault(mid, f"slot chain '{slot_name}'", err)
        return val

    # ------------------------------------------------------------------
    # Service Management
    # ------------------------------------------------------------------

    def register_service(self, service_name: str, mod_id: str, service: Any) -> None:
        """Register a public service instance or callable provided by a mod."""
        self._services[service_name] = (mod_id, service)

    def unregister_service(self, service_name: str, mod_id: str) -> None:
        """Unregister a service provided by a mod."""
        if service_name in self._services and self._services[service_name][0] == mod_id:
            del self._services[service_name]

    def get_service(self, service_name: str) -> Any | None:
        """Retrieve a service registered by a mod, or None if unavailable."""
        if service_name in self._services:
            return self._services[service_name][1]
        return None

    def has_service(self, service_name: str) -> bool:
        """Check if a service is registered in the kernel registry."""
        return service_name in self._services
