"""axiom/kernel/context.py

ModContext: the scoped execution interface provided to each mod's init(ctx).
Enforces Rule D11: everything registered through the context (hooks, slot
contributions, declared slots, services, patches, external storages, schema
migrations, background jobs) is undone by `cleanup()`.
"""

from __future__ import annotations

from collections.abc import Callable
import threading
from typing import Any

from axiom.config import AppConfig
from axiom.kernel.registry import KernelRegistry, SlotRule
from axiom.logger import logger


class ModContext:
    """Scoped interaction context passed to a mod upon activation.

    Attributes:
        mod_id: Namespaced identifier of the mod (e.g. 'comm.hunger').
        manifest: The parsed manifest when the context was created from one, else None.
        config: Scoped dictionary from AppConfig.mod_settings[mod_id].
    """

    # Seconds a background job gets to stop on cleanup before being abandoned.
    JOB_STOP_TIMEOUT: float = 2.0

    def __init__(
        self,
        mod_id: str | Any,
        kernel_registry: KernelRegistry,
        app_config: AppConfig | None = None,
    ) -> None:
        self.mod_id = getattr(mod_id, "id", mod_id)
        self.manifest = mod_id if hasattr(mod_id, "id") else None
        # Kept for backward compatibility; mods should use the public methods below.
        self._registry = kernel_registry
        if app_config is None:
            from axiom.config import AppConfig as _AppConfig
            app_config = _AppConfig()
        self.config: dict[str, Any] = app_config.mod_settings.setdefault(self.mod_id, {})
        self._registered_hooks: list[tuple[str, Callable[..., Any]]] = []
        self._registered_slots: list[tuple[str, Any]] = []
        self._declared_slots: list[str] = []
        self._registered_services: list[str] = []
        self._registered_patches: list[Any] = []
        self._registered_storages: list[Any] = []
        self._registered_migrations: list[Any] = []
        self._jobs: list[threading.Thread] = []
        self._stop_event = threading.Event()
        self.cleaned_up = False
        from axiom.kernel.kv_store import ModStore
        self.store = ModStore(self.mod_id)
        attach = getattr(kernel_registry, "attach_context", None)
        if callable(attach):
            attach(self)

    # ------------------------------------------------------------------
    # Registrations (all undone by cleanup)
    # ------------------------------------------------------------------

    def register_hook(self, hook_name: str, callback: Callable[..., Any]) -> None:
        """Register a hook callback scoped to this mod (Rule D11)."""
        self._registry.add_hook(hook_name, self.mod_id, callback)
        self._registered_hooks.append((hook_name, callback))

    def contribute_slot(self, slot_name: str, contribution: Any) -> None:
        """Contribute to an official slot according to its aggregation rule."""
        self._registry.add_to_slot(slot_name, self.mod_id, contribution)
        self._registered_slots.append((slot_name, contribution))

    def declare_slot(self, slot_name: str, rule: Any = SlotRule.COLLECT) -> None:
        """Declare an extension slot provided by this mod (removed again on cleanup)."""
        if isinstance(rule, str):
            rule = SlotRule(rule.lower())
        try:
            self._registry.declare_slot(slot_name, rule, mod_id=self.mod_id)
        except TypeError:  # registry without owner tracking
            self._registry.declare_slot(slot_name, rule)
        self._declared_slots.append(slot_name)

    def register_service(self, service_name: str, service: Any) -> None:
        """Register a public service instance or callable provided by this mod."""
        self._registry.register_service(service_name, self.mod_id, service)
        self._registered_services.append(service_name)

    def patch(
        self,
        target: str,
        patch_type: Any,
        handler: Callable[..., Any],
        priority: int = 100,
    ) -> None:
        """Register a reversible patch owned by this mod (D11).

        Raises PatchTargetError if the target does not exist or cannot be patched.
        """
        from axiom.kernel.patcher import register_patch
        record = register_patch(self.mod_id, target, patch_type, handler, priority)
        self._registered_patches.append(record)

    def register_storage(
        self,
        name: str,
        rewind_callback: Callable[..., Any] | None = None,
        fork_callback: Callable[..., Any] | None = None,
    ) -> None:
        """Register an external (non-SQL) store of this mod with the storage registry.

        ``rewind_callback(conn, save_id, target_turn)`` / ``fork_callback(conn, src,
        dst, at_turn)`` run after the engine's SQL rewind/fork is committed
        (``conn`` is None). Removed on cleanup (D11).
        """
        from axiom.storage_registry import register_custom_storage
        self._check_storage_name_free(name)
        spec = register_custom_storage(
            name, rewind_callback=rewind_callback, fork_callback=fork_callback, owner=self.mod_id
        )
        self._registered_storages.append(spec)

    def register_table_storage(self, spec: Any) -> None:
        """Register a SQL table of this mod with its own rewind/fork code (policy
        ``custom`` with a ``table``, or a ``TableStorageSpec`` built by the mod).
        The spec's owner is set to this mod; removed on cleanup (D11)."""
        import dataclasses
        from axiom.storage_registry import register_table_storage
        self._check_storage_name_free(spec.table_name)
        spec = dataclasses.replace(spec, owner=self.mod_id)
        register_table_storage(spec)
        self._registered_storages.append(spec)

    def _check_storage_name_free(self, name: str) -> None:
        from axiom.storage_registry import find_storage_spec
        existing = find_storage_spec(name)
        if existing is not None and existing.owner != self.mod_id:
            raise ValueError(
                f"Storage '{name}' is already registered by "
                f"{'mod ' + existing.owner if existing.owner else 'the kernel'}."
            )

    def register_migrations(
        self,
        target_version: int,
        migrations: dict[int, Callable[..., Any]],
    ) -> None:
        """Declare this mod's table migrations ({N: callable(conn) bringing N to N+1}).

        Applied by the engine to each save database it creates or opens, and
        tracked in that database's ``Mod_Schema_Versions``. Removed on cleanup.
        """
        from axiom.storage_registry import register_mod_migrations
        self._registered_migrations.append(
            register_mod_migrations(self.mod_id, target_version, migrations)
        )

    def spawn_job(
        self,
        target: Callable[..., Any],
        *args: Any,
        name: str | None = None,
        **kwargs: Any,
    ) -> threading.Thread:
        """Start a background thread owned by this mod (D11, §10.4).

        The job should poll `ctx.should_stop()` (or wait on `ctx.stop_event`) and return
        when it is set. On cleanup the stop event is set and the job is joined for
        `JOB_STOP_TIMEOUT` seconds; a job still running after that is abandoned (daemon).
        """
        thread = threading.Thread(
            target=target,
            args=args,
            kwargs=kwargs,
            name=name or f"mod:{self.mod_id}",
            daemon=True,
        )
        self._jobs = [j for j in self._jobs if j.is_alive()]
        self._jobs.append(thread)
        thread.start()
        return thread

    @property
    def stop_event(self) -> threading.Event:
        """Event set when the mod is being disabled: background jobs must stop."""
        return self._stop_event

    def should_stop(self) -> bool:
        return self._stop_event.is_set()

    # ------------------------------------------------------------------
    # Queries (public API: mods must not use ctx._registry)
    # ------------------------------------------------------------------

    def get_service(self, service_name: str) -> Any | None:
        """Query a service provided by another mod or the kernel."""
        return self._registry.get_service(service_name)

    def get_slot(self, slot_name: str) -> Any:
        """Aggregated value of a slot (winner for an exclusive slot, list otherwise)."""
        return self._registry.get_slot(slot_name)

    def get_slot_contributions(self, slot_name: str) -> list[Any]:
        """All contributions to a slot, in mod order."""
        return self._registry.get_slot_contributions(slot_name)

    def get_slot_entries(self, slot_name: str) -> list[tuple[str, Any]]:
        """(mod_id, contribution) pairs of a slot, in mod order."""
        return self._registry.get_slot_entries(slot_name)

    def report_fault(self, mod_id: str, where: str, err: Exception) -> None:
        """Disable and report a mod whose contribution raised when called by this mod
        (same policy as a faulty hook, §6.1)."""
        self._registry.report_fault(mod_id, where, err)

    def get_faulted_mods(self) -> dict[str, str]:
        """Mods disabled at runtime after raising, with the reason."""
        return self._registry.get_faulted_mods()

    def apply_slot_chain(self, slot_name: str, initial_value: Any, *args: Any, **kwargs: Any) -> Any:
        """Run a CHAIN slot on a value (faulty contributions are isolated)."""
        return self._registry.apply_slot_chain(slot_name, initial_value, *args, **kwargs)

    def invoke_hook(self, hook_name: str, *args: Any, **kwargs: Any) -> list[Any]:
        """Fire a hook (typically one this mod created, D10); faulty callbacks are isolated."""
        return self._registry.invoke_hook(hook_name, *args, **kwargs)

    def invoke_hook_unguarded(self, hook_name: str, *args: Any, **kwargs: Any) -> list[Any]:
        """Fire a hook without safety net: exceptions propagate to this mod."""
        return self._registry.invoke_hook_unguarded(hook_name, *args, **kwargs)

    def has_hook(self, hook_name: str) -> bool:
        return self._registry.has_hook(hook_name)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def has_patches(self) -> bool:
        return bool(self._registered_patches)

    @property
    def has_raw_code(self) -> bool:
        contributes = getattr(self.manifest, "contributes", None)
        return bool(getattr(contributes, "raw_code", False))

    @property
    def can_disable_hot(self) -> bool:
        """D-5: hooks/slots/services/jobs are undone at once; patches and declared
        raw code only at next launch."""
        contributes = getattr(self.manifest, "contributes", None)
        declared_patches = bool(getattr(contributes, "patches", None))
        return not (self.has_patches or declared_patches or self.has_raw_code)

    # ------------------------------------------------------------------
    # Cleanup (D11)
    # ------------------------------------------------------------------

    def cleanup(self) -> None:
        """Automatic and complete unregistration of everything registered through this context."""
        self._stop_event.set()

        for hook_name, _ in self._registered_hooks:
            self._registry.remove_hook(hook_name, self.mod_id)
        for slot_name, _ in self._registered_slots:
            self._registry.remove_slot_contribution(slot_name, self.mod_id)
        undeclare = getattr(self._registry, "undeclare_slot", None)
        if callable(undeclare):
            for slot_name in self._declared_slots:
                undeclare(slot_name, self.mod_id)
        for s_name in self._registered_services:
            self._registry.unregister_service(s_name, self.mod_id)
        if self._registered_storages or self._registered_migrations:
            from axiom.storage_registry import unregister_mod_migrations, unregister_storage
            for spec in self._registered_storages:
                unregister_storage(spec)
            for entry in self._registered_migrations:
                unregister_mod_migrations(entry)

        # Only this context's own patch records: another context of the same mod id
        # (e.g. the real mod while `axiom mod test` runs a copy) keeps its patches.
        from axiom.kernel.patcher import (
            PatchingDuringStepError,
            is_patching_locked,
            remove_patch,
            suspend_mod_patches,
        )
        if self._registered_patches:
            if is_patching_locked():
                # A step is running: deactivate now, remove when the stack unfreezes.
                suspend_mod_patches(self.mod_id)
            else:
                for record in self._registered_patches:
                    try:
                        remove_patch(record)
                    except PatchingDuringStepError:
                        suspend_mod_patches(self.mod_id)

        current = threading.current_thread()
        for job in self._jobs:
            if job is current or not job.is_alive():
                continue
            job.join(self.JOB_STOP_TIMEOUT)
            if job.is_alive():
                logger.warning(
                    "Background job '%s' of mod '%s' did not stop in %.1fs; abandoned.",
                    job.name,
                    self.mod_id,
                    self.JOB_STOP_TIMEOUT,
                )

        self._registered_hooks.clear()
        self._registered_slots.clear()
        self._declared_slots.clear()
        self._registered_services.clear()
        self._registered_patches.clear()
        self._registered_storages.clear()
        self._registered_migrations.clear()
        self._jobs.clear()
        self.cleaned_up = True
