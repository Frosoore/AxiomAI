"""axiom/kernel/api.py

Version of the kernel API and the single catalogue of public extension points.

`KERNEL_API` is compared with the `axiom_api` field of every manifest: a mod written
for another API version is not loaded (D12, "versions Minecraft" logic).

`PUBLIC_HOOKS` / `PUBLIC_SLOTS` list the hooks and slots that are *really* fired or
read by the engine and the official mods (established by grepping
`invoke_hook|execute_hook|get_slot|get_slot_contributions|apply_slot_chain`).
This list is the only source used by the scaffold (`axiom mod new`), the LLM mod
creator prompt and the tester (which refuses an unknown `axiom.*` name).
Mods may still create their own hooks and slots in their own namespace (D10).

Note: the `axiom.step:*`, `axiom.turn:*` and `axiom.world:*` points belong to the
official mods; this catalogue should move to (or be generated from) those mods
once they export their own constants.

Patch convention (§6.2): a function of the engine becomes a stable patch target by
decorating it with `@patchable("<module>:<qualname>")` (see `axiom.kernel.patcher`).
Any other function or method can still be targeted by `module:func` or
`module:Class.method` through the bytecode fallback.
"""

from __future__ import annotations

import re

KERNEL_API: int = 1


# hook name -> what the callback receives / when it is fired
PUBLIC_HOOKS: dict[str, str] = {
    "axiom.kernel:execute_step": "Runs a whole step (KernelStepContext). Critical: exceptions propagate.",
    "axiom.step:gather_context": "After context gathering, before the prompt is built (TurnContext).",
    "axiom.step:response_parsed": (
        "After the LLM answer is parsed and output fields routed, before arbitration (TurnContext)."
    ),
    "axiom.step:arbitrate_mutations": "While state mutations are arbitrated (TurnContext).",
    "axiom.step:after_step": "After rules and mutations are staged, before commit (TurnContext).",
    "axiom.turn:arbitrate_stats": "During stats arbitration (TurnContext).",
    "axiom.universe:compile": "Universe compilation (compile context).",
    "axiom.universe:decompile": "Universe decompilation (decompile context).",
    "axiom.universe:refresh_definition": "Universe definition refresh in dev mode.",
}

# slot name -> (rule, description)
PUBLIC_SLOTS: dict[str, tuple[str, str]] = {
    "axiom.kernel:locales": ("collect", "(lang_code, {key: text}) translation tables."),
    "axiom.kernel:help_entries": ("collect", "In-app help entries."),
    "axiom.turn:prompt_sections": (
        "collect",
        "(id, position, depth, text, order) tuple — or (position, text), (position, depth, text), "
        "a plain string, or a dict {'position', 'text', 'depth', 'order'} — or a callable(turn_ctx) "
        "returning one of these (None = nothing this turn). position: 'system', 'before_system', "
        "'user', 'in_chat' (system message `depth` messages before the end) or 'rag' (one [MEMORY] line per text line). "
        "A malformed section disables its mod with the reason.",
    ),
    "axiom.turn:output_fields": (
        "collect",
        "(field_name, handler(value, turn_ctx)) or {field_name: handler}: routes a parsed LLM output field.",
    ),
    "axiom.turn:stream_filter": ("chain", "callable(token) -> token, applied while streaming."),
    "axiom.turn:final_text_filter": ("chain", "callable(text) -> text, applied to the final narration."),
    "axiom.turn:llm_backend": ("exclusive", "LLM backend instance or factory."),
    "axiom.providers:drivers": ("collect", "LLM provider drivers."),
    "axiom.world:custom_rules": ("collect", "Extra arbitration rules."),
    "axiom.ui.qt:sidebar_widget": ("collect", "Qt sidebar widgets."),
    "axiom.ui.qt:settings_tab": ("collect", "Qt settings tabs."),
    "axiom.ui.web:side_panel": ("collect", "Web side panels."),
    "axiom.ui.web:settings_tab": ("collect", "Web settings tabs."),
    "axiom.ui.web:action_button": ("collect", "Web action buttons."),
}

# Namespaces reserved to the public catalogue: a name there must be listed above
# (or declared by the mod itself in [provides_slots]).
_RESERVED_NAMESPACES = ("axiom.",)

_NAME_REGEX = re.compile(r"^[a-zA-Z0-9_.-]+:[a-zA-Z0-9_.-]+$")


def check_extension_point(name: str, kind: str, own_slots: set[str] | frozenset[str] = frozenset()) -> str | None:
    """Return an error message if `name` is not a usable hook/slot name, else None.

    kind: "hook" or "slot". Names in a reserved namespace must exist in the public
    catalogue (or be declared by the mod itself); other namespaces are free (D10).
    """
    if not _NAME_REGEX.match(name or ""):
        return f"Invalid {kind} name '{name}'. Expected 'namespace:name'."
    if name in own_slots:
        return None
    known = PUBLIC_HOOKS if kind == "hook" else PUBLIC_SLOTS
    if name.startswith(_RESERVED_NAMESPACES) and name not in known:
        return (
            f"Unknown {kind} '{name}': it is never fired by Axiom. "
            f"Known {kind}s: {', '.join(sorted(known))}."
        )
    return None


# ---------------------------------------------------------------------------
# Version specifiers for mod dependencies
# ---------------------------------------------------------------------------

_SIMPLE_SPEC = re.compile(r"^(>=|<=|==|!=|~=|>|<|=)?\s*(\d+(?:\.\d+)*)$")


def _vtuple(v: str) -> tuple[int, ...]:
    core = re.split(r"[-+]", v.strip(), maxsplit=1)[0]
    return tuple(int(p) for p in core.split("."))


def _simple_match(version: str, op: str, target: str) -> bool:
    a, b = _vtuple(version), _vtuple(target)
    n = max(len(a), len(b))
    a, b = a + (0,) * (n - len(a)), b + (0,) * (n - len(b))
    if op in ("==", "="):
        return a == b
    if op == "!=":
        return a != b
    if op == ">=":
        return a >= b
    if op == "<=":
        return a <= b
    if op == ">":
        return a > b
    if op == "<":
        return a < b
    if op == "~=":
        prefix = _vtuple(target)[:-1]
        return a >= b and a[: len(prefix)] == prefix
    return False


def validate_version_spec(spec: str) -> None:
    """Raise ValueError if `spec` is not a valid version specifier ('*' = any)."""
    spec = (spec or "").strip()
    if spec in ("", "*"):
        return
    try:
        from packaging.specifiers import SpecifierSet
        SpecifierSet(spec)
        return
    except ImportError:
        pass
    except Exception as err:
        raise ValueError(f"Invalid version specifier '{spec}': {err}") from err
    for part in spec.split(","):
        if not _SIMPLE_SPEC.match(part.strip()):
            raise ValueError(f"Invalid version specifier '{spec}'.")


def version_satisfies(version: str, spec: str) -> bool:
    """Check `version` against a specifier such as '>=1.0.0,<2' ('*' = any)."""
    spec = (spec or "").strip()
    if spec in ("", "*"):
        return True
    try:
        from packaging.specifiers import SpecifierSet
        from packaging.version import Version
        return SpecifierSet(spec).contains(Version(version), prereleases=True)
    except ImportError:
        pass
    for part in spec.split(","):
        m = _SIMPLE_SPEC.match(part.strip())
        if not m or not _simple_match(version, m.group(1) or "==", m.group(2)):
            return False
    return True
