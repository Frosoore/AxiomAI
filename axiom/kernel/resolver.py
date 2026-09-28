"""axiom/kernel/resolver.py

Topological sort and constraint resolver for mod load order.
Constructs a Directed Acyclic Graph (DAG) with cycle detection,
missing dependency pruning, and stable user-preference ordering.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from axiom.kernel.manifest import ModManifest


class ResolutionError(Exception):
    """Base exception for mod resolution failures."""


class CyclicDependencyError(ResolutionError):
    """Raised when a circular dependency or ordering constraint is detected."""

    def __init__(self, cycle: list[str]) -> None:
        self.cycle = list(cycle)
        cycle_str = " -> ".join(self.cycle)
        super().__init__(f"Cyclic dependency detected: {cycle_str}")


class ConflictError(ResolutionError):
    """Raised when mutually conflicting mods are active."""


@dataclass
class ResolutionReport:
    """Detailed outcome of the dependency and load order resolution."""

    load_order: list[str] = field(default_factory=list)
    disabled_mods: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def resolve_load_order(
    manifests: Mapping[str, ModManifest],
    user_order: list[str] | None = None,
) -> ResolutionReport:
    """Resolve load order for the given set of candidate manifests.

    Args:
        manifests: Mapping from mod_id to ModManifest for all candidate mods.
        user_order: Optional ordered list of mod_ids reflecting user priority.

    Returns:
        ResolutionReport with computed load_order and any disabled mods with reasons.

    Raises:
        CyclicDependencyError: If a cycle exists among valid candidate mods.
        ConflictError: If two active mods declare a direct conflict.
    """
    report = ResolutionReport()
    active_manifests: dict[str, ModManifest] = dict(manifests)

    # Map of virtual provides -> providing mod_id
    provides_map: dict[str, str] = {}
    for mod_id, m in active_manifests.items():
        provides_map[mod_id] = mod_id
        for virtual_id in m.ordering.provides:
            provides_map[virtual_id] = mod_id

    # 1. Iterative pruning of mods with missing mandatory dependencies
    changed = True
    while changed:
        changed = False
        to_prune: list[tuple[str, str]] = []
        for mod_id, m in active_manifests.items():
            for dep_name, dep in m.dependencies.items():
                if dep.optional:
                    continue
                # Mandatory dependency must be present or provided
                if dep_name not in provides_map:
                    to_prune.append((mod_id, f"Missing required dependency: '{dep_name}'"))
                    break

        for mod_id, reason in to_prune:
            report.disabled_mods[mod_id] = reason
            del active_manifests[mod_id]
            # Remove provides
            provides_map = {k: v for k, v in provides_map.items() if v != mod_id}
            changed = True

    # 2. Conflict detection
    for mod_id, m in active_manifests.items():
        for conflict_id in m.ordering.conflicts:
            if conflict_id in provides_map:
                conflicting_mod = provides_map[conflict_id]
                raise ConflictError(
                    f"Mod '{mod_id}' conflicts with active mod '{conflicting_mod}'."
                )

    if not active_manifests:
        return report

    # 3. Build DAG edges (u -> v means u must load before v)
    # Successors: u -> set of nodes that must come after u
    # In-degrees: count of prerequisites for each node
    nodes = set(active_manifests.keys())
    adj: dict[str, set[str]] = {n: set() for n in nodes}
    in_degree: dict[str, int] = {n: 0 for n in nodes}

    def add_edge(before_node: str, after_node: str) -> None:
        if before_node in nodes and after_node in nodes and before_node != after_node:
            if after_node not in adj[before_node]:
                adj[before_node].add(after_node)
                in_degree[after_node] += 1

    for mod_id, m in active_manifests.items():
        # Dependencies: if mod_id depends on dep, dep must load before mod_id
        for dep_name in m.dependencies:
            provider = provides_map.get(dep_name)
            if provider and provider in nodes:
                add_edge(provider, mod_id)

        # Ordering: after
        for after_id in m.ordering.after:
            provider = provides_map.get(after_id)
            if provider and provider in nodes:
                add_edge(provider, mod_id)

        # Ordering: before
        for before_id in m.ordering.before:
            provider = provides_map.get(before_id)
            if provider and provider in nodes:
                add_edge(mod_id, provider)

    # 4. Cycle detection (DFS with graph coloring)
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in nodes}
    parent = {n: None for n in nodes}

    def find_cycle(start_node: str) -> list[str] | None:
        stack = [(start_node, iter(sorted(adj[start_node])))]
        color[start_node] = GRAY
        path = [start_node]

        while stack:
            u, children = stack[-1]
            try:
                v = next(children)
                if color[v] == GRAY:
                    # Cycle detected: v is already in current DFS path
                    cycle_start = path.index(v)
                    return path[cycle_start:] + [v]
                elif color[v] == WHITE:
                    color[v] = GRAY
                    parent[v] = u
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
                raise CyclicDependencyError(cycle)

    # 5. Stable topological sort weighted by user order (Skyrim load order analogy)
    # Order mapping: smaller rank = higher user preference
    pref_list = user_order or []
    pref_rank = {mod_id: i for i, mod_id in enumerate(pref_list)}
    default_rank = len(pref_list)

    # Available nodes with in_degree == 0
    available = [n for n in nodes if in_degree[n] == 0]
    # Sort available by user preference rank, then alphabetically for determinism
    available.sort(key=lambda n: (pref_rank.get(n, default_rank), n))

    order: list[str] = []
    while available:
        curr = available.pop(0)
        order.append(curr)

        for nxt in adj[curr]:
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                available.append(nxt)

        available.sort(key=lambda n: (pref_rank.get(n, default_rank), n))

    report.load_order = order
    return report
