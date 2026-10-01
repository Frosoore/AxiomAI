"""axiom/kernel/registry.py

Kernel Registry for official extension points (hooks and slots).
Provides fault-tolerant execution with exception isolation and rule-based slots.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import Any

from axiom.backends.base import GenerationCancelled
from axiom.logger import logger


class SlotRule(Enum):
    """Aggregation rules for slots (extension point containers)."""

    EXCLUSIVE = "exclusive"  # Only one contribution allowed
    CHAIN = "chain"          # Pipeline where each contribution transforms the value
    COLLECT = "collect"      # Accumulates all contributions into a list


class RegistryError(Exception):
    """Raised on registry conflicts or invalid operations."""


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
        # slot_name -> list of (mod_id, contribution)
        self._slot_contributions: dict[str, list[tuple[str, Any]]] = {}
        # service_name -> (mod_id, service_instance)
        self._services: dict[str, tuple[str, Any]] = {}

        # Standardized kernel slots (§9 & ARBITRAGE.md)
        self.declare_slot("axiom.kernel:locales", SlotRule.COLLECT)
        self.declare_slot("axiom.kernel:help_entries", SlotRule.COLLECT)

        global _ACTIVE_REGISTRY
        _ACTIVE_REGISTRY = self

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

        If a callback raises an exception, the error is logged and suppressed,
        ensuring that a faulty mod cannot crash the kernel or halt execution.

        Returns:
            List of return values from successfully executed callbacks.
        """
        results: list[Any] = []
        for mod_id, callback in list(self._hooks.get(hook_name, [])):
            try:
                res = callback(*args, **kwargs)
                results.append(res)
            except GenerationCancelled:
                raise
            except Exception as err:
                logger.error(
                    "Faulty mod '%s' raised an exception in hook '%s': %s",
                    mod_id,
                    hook_name,
                    err,
                    exc_info=True,
                )
        return results

    # Alias matching kernel dispatch naming conventions
    execute_hook = invoke_hook

    def has_hook(self, hook_name: str) -> bool:
        """Check if any callbacks are registered for a given hook."""
        return bool(self._hooks.get(hook_name))

    # ------------------------------------------------------------------
    # Slot Management
    # ------------------------------------------------------------------

    def declare_slot(self, slot_name: str, rule: SlotRule = SlotRule.COLLECT) -> None:
        """Declare an official slot with an aggregation rule."""
        self._slot_rules[slot_name] = rule

    def add_to_slot(self, slot_name: str, mod_id: str, contribution: Any) -> None:
        """Contribute an object, widget, or handler to an official slot."""
        rule = self._slot_rules.get(slot_name, SlotRule.COLLECT)
        contributions = self._slot_contributions.setdefault(slot_name, [])

        if rule == SlotRule.EXCLUSIVE and contributions:
            existing_mod = contributions[0][0]
            raise RegistryError(
                f"Slot '{slot_name}' is EXCLUSIVE and already occupied by mod '{existing_mod}'. "
                f"Mod '{mod_id}' cannot contribute."
            )

        contributions.append((mod_id, contribution))

    def remove_slot_contribution(self, slot_name: str, mod_id: str) -> None:
        """Remove contributions made to a slot by a specific mod."""
        if slot_name in self._slot_contributions:
            self._slot_contributions[slot_name] = [
                (mid, c) for mid, c in self._slot_contributions[slot_name] if mid != mod_id
            ]

    def get_slot(self, slot_name: str) -> Any:
        """Retrieve aggregated contributions for a slot according to its rule."""
        rule = self._slot_rules.get(slot_name, SlotRule.COLLECT)
        contributions = [c for _, c in self._slot_contributions.get(slot_name, [])]

        if rule == SlotRule.EXCLUSIVE:
            return contributions[0] if contributions else None
        elif rule == SlotRule.COLLECT:
            return list(contributions)
        elif rule == SlotRule.CHAIN:
            return list(contributions)
        return contributions

    def get_slot_contributions(self, slot_name: str) -> list[Any]:
        """Return raw list of contributed values for a slot."""
        return [c for _, c in self._slot_contributions.get(slot_name, [])]

    def apply_slot_chain(self, slot_name: str, initial_value: Any, *args: Any, **kwargs: Any) -> Any:
        """Run a pipeline of CHAIN contributions on initial_value with exception isolation."""
        val = initial_value
        for mid, func in list(self._slot_contributions.get(slot_name, [])):
            if callable(func):
                try:
                    val = func(val, *args, **kwargs)
                except GenerationCancelled:
                    raise
                except Exception as err:
                    logger.error(
                        "Mod '%s' raised exception in slot chain '%s': %s",
                        mid,
                        slot_name,
                        err,
                        exc_info=True,
                    )
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
