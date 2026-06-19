"""Rank fusion for hybrid search.

Algorithm adapted from Hindsight (MIT, ``engine/search/fusion.py``), kept
dependency-free and deterministic. We fuse *ranked lists of document ids* (one
per retrieval arm — semantic, lexical, …) into a single ranking using
Reciprocal Rank Fusion (RRF).

RRF is rank-based, not score-based, on purpose: each arm produces scores on its
own incomparable scale (cosine distance vs BM25), so combining raw scores would
let one arm's scale dominate. RRF only looks at *where* a document ranks within
each arm, which makes the arms commensurable.
"""

from __future__ import annotations

_DEFAULT_RRF_K: int = 60


def cap_per_source(ranked_ids: list[str], cap: int) -> list[str]:
    """Truncate a single arm's ranked ids to its top ``cap``.

    Applied per arm *before* fusion so one over-expanding backend cannot crowd
    out the others. ``cap <= 0`` disables the cap. The caller is responsible for
    ordering ``ranked_ids`` best-first; this only slices.
    """
    if cap <= 0 or len(ranked_ids) <= cap:
        return ranked_ids
    return ranked_ids[:cap]


def reciprocal_rank_fusion(
    ranked_lists: list[list[str]], k: int = _DEFAULT_RRF_K
) -> list[tuple[str, float]]:
    """Merge several ranked id lists into one via Reciprocal Rank Fusion.

    RRF formula: ``score(d) = sum over arms of 1 / (k + rank(d))`` where ``rank``
    is 1-based within each arm. A document absent from an arm contributes nothing
    for that arm.

    Args:
        ranked_lists: One list of document ids per arm, each ordered best-first.
        k: RRF damping constant (default 60). Larger ``k`` flattens the
            contribution of top ranks, smaller ``k`` sharpens it.

    Returns:
        ``(doc_id, rrf_score)`` pairs sorted by score descending. Ties are broken
        deterministically by first appearance order across the input lists, so
        the result is stable for identical inputs.
    """
    scores: dict[str, float] = {}
    first_seen: dict[str, int] = {}
    order = 0
    for ranked in ranked_lists:
        for rank, doc_id in enumerate(ranked, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
            if doc_id not in first_seen:
                first_seen[doc_id] = order
                order += 1

    return sorted(
        scores.items(),
        key=lambda item: (-item[1], first_seen[item[0]]),
    )
