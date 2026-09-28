"""axiom/kernel/context.py

ModContext: the scoped execution interface provided to each mod's init(ctx).
Enforces Rule D11 (automatic total unregistration on cleanup).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from axiom.config import AppConfig
from axiom.kernel.registry import KernelRegistry, SlotRule


class ModContext:
    """Scoped interaction context passed to a mod upon activation.

    Attributes:
        mod_id: Namespaced identifier of the mod (e.g. 'comm.hunger').
        config: Scoped dictionary from AppConfig.mod_settings[mod_id].
    """

    def __init__(
        self,
        mod_id: str | Any,
        kernel_registry: KernelRegistry,
        app_config: AppConfig | None = None,
    ) -> None:
        self.mod_id = getattr(mod_id, "id", mod_id)
        self._registry = kernel_registry
        if app_config is None:
            from axiom.config import AppConfig as _AppConfig
            app_config = _AppConfig()
        self.config: dict[str, Any] = app_config.mod_settings.setdefault(self.mod_id, {})
        self._registered_hooks: list[tuple[str, Callable[..., Any]]] = []
        self._registered_slots: list[tuple[str, Any]] = []
        self._registered_services: list[str] = []
        self._registered_patches: list[Any] = []

    def register_hook(self, hook_name: str, callback: Callable[..., Any]) -> None:
        """Register a hook callback scoped to this mod (Rule D11)."""
        self._registry.add_hook(hook_name, self.mod_id, callback)
        self._registered_hooks.append((hook_name, callback))

    def contribute_slot(self, slot_name: str, contribution: Any) -> None:
        """Contribute to an official slot according to its aggregation rule."""
        self._registry.add_to_slot(slot_name, self.mod_id, contribution)
        self._registered_slots.append((slot_name, contribution))

    def declare_slot(self, slot_name: str, rule: Any = SlotRule.COLLECT) -> None:
        """Declare an official extension slot provided by this mod."""
        from axiom.kernel.registry import SlotRule as _SlotRule
        if isinstance(rule, str):
            rule = _SlotRule(rule.lower())
        self._registry.declare_slot(slot_name, rule)

    def register_service(self, service_name: str, service: Any) -> None:
        """Register a public service instance or callable provided by this mod."""
        self._registry.register_service(service_name, self.mod_id, service)
        self._registered_services.append(service_name)

    def get_service(self, service_name: str) -> Any | None:
        """Query a service provided by another mod or the kernel."""
        return self._registry.get_service(service_name)

    def patch(
        self,
        target: str,
        patch_type: Any,
        handler: Callable[..., Any],
        priority: int = 100,
    ) -> None:
        """Enregistre un patch réversible rattaché à ce mod (D11)."""
        from axiom.kernel.patcher import register_patch
        record = register_patch(self.mod_id, target, patch_type, handler, priority)
        self._registered_patches.append(record)

    def cleanup(self) -> None:
        """Automatic and complete unregistration of all hooks, slots, services, and patches (Rule D11)."""
        for hook_name, _ in self._registered_hooks:
            self._registry.remove_hook(hook_name, self.mod_id)
        for slot_name, _ in self._registered_slots:
            self._registry.remove_slot_contribution(slot_name, self.mod_id)
        for s_name in self._registered_services:
            self._registry.unregister_service(s_name, self.mod_id)

        from axiom.kernel.patcher import remove_patches_by_mod
        remove_patches_by_mod(self.mod_id)

        self._registered_hooks.clear()
        self._registered_slots.clear()
        self._registered_services.clear()
        self._registered_patches.clear()
