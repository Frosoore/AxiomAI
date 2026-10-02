"""axiom/kernel/resolver.py

Topological sort and constraint resolver for mod load order.
Constructs a Directed Acyclic Graph (DAG) with cycle detection,
missing dependency pruning, and stable user-preference ordering.

The resolver never fails as a whole: a mod with an incompatible API, an unsatisfied
dependency, a declared conflict or a dependency cycle is set aside with a reason in
`ResolutionReport.disabled_mods` (and its dependents with it), and the rest loads (§4.1, D13).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from axiom.kernel.api import KERNEL_API, version_satisfies
from axiom.kernel.manifest import ModManifest


class ResolutionError(Exception):
    """Base exception for mod resolution failures."""


class CyclicDependencyError(ResolutionError):
    """Describes a circular dependency or ordering constraint (kept for API compatibility)."""

    def __init__(self, cycle: list[str]) -> None:
        self.cycle = list(cycle)
        cycle_str = " -> ".join(self.cycle)
        super().__init__(f"Cyclic dependency detected: {cycle_str}")


class ConflictError(ResolutionError):
    """Describes mutually conflicting mods (kept for API compatibility)."""


@dataclass
class ResolutionReport:
    """Detailed outcome of the dependency and load order resolution."""

    load_order: list[str] = field(default_factory=list)
    # mod_id -> human readable reason why the mod is not loaded
    disabled_mods: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    # (loser, winner, explanation) for every declared conflict that was arbitrated
    conflicts: list[tuple[str, str, str]] = field(default_factory=list)
    # cycles that were found (each one is a list of mod ids)
    cycles: list[list[str]] = field(default_factory=list)


def _rank_key(user_order: list[str] | None):
    pref_rank = {mod_id: i for i, mod_id in enumerate(user_order or [])}
    default_rank = len(pref_rank)
    return lambda n: (pref_rank.get(n, default_rank), n)


def resolve_load_order(
    manifests: Mapping[str, ModManifest],
    user_order: list[str] | None = None,
    unavailable: Mapping[str, str] | None = None,
    kernel_api: int = KERNEL_API,
) -> ResolutionReport:
    """Resolve load order for the given set of candidate manifests.

    Args:
        manifests: Mapping from mod_id to ModManifest for all candidate mods.
        user_order: Optional ordered list of mod_ids reflecting user priority (§8).
            It orders the result under the dependency/before/after constraints and
            decides which mod wins a declared conflict.
        unavailable: Optional mapping of mods known but not candidates (disabled by
            the user, missing Python package...) -> reason, used to explain why a
            dependent is set aside.
        kernel_api: API version of the running kernel.

    Returns:
        ResolutionReport with the load order and every set-aside mod with its reason.
    """
    report = ResolutionReport()
    unavailable = dict(unavailable or {})
    rank = _rank_key(user_order)
    active: dict[str, ModManifest] = {}

    # 0. Kernel API version (D12)
    for mod_id, m in manifests.items():
        if m.axiom_api != kernel_api:
            report.disabled_mods[mod_id] = (
                f"Incompatible kernel API: mod requires axiom_api={m.axiom_api}, kernel provides {kernel_api}."
            )
        else:
            active[mod_id] = m

    def providers_of(name: str) -> list[str]:
        return sorted(
            (mid for mid, m in active.items() if mid == name or name in m.ordering.provides),
            key=rank,
        )

    def why_unavailable(name: str) -> str | None:
        if name in report.disabled_mods:
            return report.disabled_mods[name]
        if name in unavailable:
            return unavailable[name]
        return None

    def prune_dependencies() -> None:
        changed = True
        while changed:
            changed = False
            for mod_id in sorted(active):
                m = active[mod_id]
                reason = None
                for dep_name, dep in m.dependencies.items():
                    if dep.optional:
                        continue
                    providers = providers_of(dep_name)
                    if not providers:
                        cause = why_unavailable(dep_name)
                        if cause:
                            reason = f"Required dependency '{dep_name}' is not loaded: {cause}"
                        else:
                            reason = f"Missing required dependency: '{dep_name}'"
                        break
                    if dep_name in active and not version_satisfies(active[dep_name].version, dep.version_spec):
                        reason = (
                            f"Dependency '{dep_name}' version {active[dep_name].version} "
                            f"does not satisfy '{dep.version_spec}'"
                        )
                        break
                if reason:
                    report.disabled_mods[mod_id] = reason
                    del active[mod_id]
                    changed = True

    # 1. Missing / incompatible mandatory dependencies (with cascade)
    prune_dependencies()

    # 2. Declared conflicts: the mod ranked first in the user order wins (§8)
    changed = True
    while changed:
        changed = False
        for mod_id in sorted(active, key=rank):
            if mod_id not in active:
                continue
            for conflict_id in active[mod_id].ordering.conflicts:
                others = [p for p in providers_of(conflict_id) if p != mod_id]
                if not others:
                    continue
                other = others[0]
                winner, loser = sorted([mod_id, other], key=rank)
                explanation = f"'{mod_id}' declares a conflict with '{conflict_id}'"
                report.disabled_mods[loser] = (
                    f"Conflicts with '{winner}' ({explanation}); '{winner}' comes first in the mod order."
                )
                report.conflicts.append((loser, winner, explanation))
                del active[loser]
                changed = True
                break
            if changed:
                break
        if changed:
            prune_dependencies()

    # 3. Cycles: every mod of a cycle is set aside, then dependents cascade
    while active:
        order, cycle = _toposort(active, providers_of, rank)
        if cycle is None:
            report.load_order = order
            break
        report.cycles.append(cycle)
        cycle_str = " -> ".join(cycle)
        for mod_id in set(cycle):
            if mod_id in active:
                report.disabled_mods[mod_id] = f"Cyclic dependency detected: {cycle_str}"
                del active[mod_id]
        prune_dependencies()

    return report


def _toposort(active, providers_of, rank) -> tuple[list[str], list[str] | None]:
    """Return (order, None) or ([], cycle)."""
    nodes = set(active)
    adj: dict[str, set[str]] = {n: set() for n in nodes}
    in_degree: dict[str, int] = {n: 0 for n in nodes}

    def add_edge(before_node: str, after_node: str) -> None:
        if before_node in nodes and after_node in nodes and before_node != after_node:
            if after_node not in adj[before_node]:
                adj[before_node].add(after_node)
                in_degree[after_node] += 1

    for mod_id, m in active.items():
        for dep_name in m.dependencies:
            for provider in providers_of(dep_name):
                add_edge(provider, mod_id)
        for after_id in m.ordering.after:
            for provider in providers_of(after_id):
                add_edge(provider, mod_id)
        for before_id in m.ordering.before:
            for provider in providers_of(before_id):
                add_edge(mod_id, provider)

    # Cycle detection (DFS with graph coloring)
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in nodes}

    def find_cycle(start_node: str) -> list[str] | None:
        stack = [(start_node, iter(sorted(adj[start_node])))]
        color[start_node] = GRAY
        path = [start_node]
        while stack:
            u, children = stack[-1]
            try:
                v = next(children)
                if color[v] == GRAY:
                    cycle_start = path.index(v)
                    return path[cycle_start:] + [v]
                elif color[v] == WHITE:
                    color[v] = GRAY
                    path.append(v)
                    stack.append((v, iter(sorted(adj[v]))))
            except StopIteration:
                color[u] = BLACK
                path.pop()
                stack.pop()
        return None

    for node in sorted(nodes):
        if color[node] == WHITE:
            cycle = find_cycle(node)
            if cycle:
                return [], cycle

    # Stable topological sort weighted by user order (Skyrim load order analogy)
    available = sorted((n for n in nodes if in_degree[n] == 0), key=rank)
    order: list[str] = []
    while available:
        curr = available.pop(0)
        order.append(curr)
        for nxt in adj[curr]:
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                available.append(nxt)
        available.sort(key=rank)
    return order, None


def compute_exclusive_conflicts(
    manifests: Mapping[str, ModManifest],
    load_order: list[str],
) -> list[tuple[str, list[str]]]:
    """Statically compute exclusive slots claimed by several loaded mods (§8, D13).

    Returns a list of (slot_name, [candidates in load order]); the first candidate wins.
    Computed from the manifests ([provides_slots] rules and [contributes].slots), without
    running any mod code.
    """
    from axiom.kernel.api import PUBLIC_SLOTS

    rules = {name: rule for name, (rule, _doc) in PUBLIC_SLOTS.items()}
    for mod_id in load_order:
        for slot, rule in manifests[mod_id].provides_slots.items():
            rules[slot] = rule
    claims: dict[str, list[str]] = {}
    for mod_id in load_order:
        for slot in manifests[mod_id].contributes.slots:
            if rules.get(slot) == "exclusive":
                claims.setdefault(slot, []).append(mod_id)
    return [(slot, mods) for slot, mods in sorted(claims.items()) if len(mods) > 1]
