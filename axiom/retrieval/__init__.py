"""Retrieval utilities for Axiom's narrative memory.

Hybrid-search building blocks (rank fusion, lexical scoring) used by
``axiom.memory.VectorMemory`` to combine a semantic arm (ChromaDB) with a
lexical arm (BM25). Algorithms adapted from Hindsight (MIT,
``engine/search/``), reimplemented for our ChromaDB/SQLite/``turn_id`` stack.
"""

from .fusion import cap_per_source, reciprocal_rank_fusion
from .reranker import CrossEncoderReranker

__all__ = ["cap_per_source", "reciprocal_rank_fusion", "CrossEncoderReranker"]
