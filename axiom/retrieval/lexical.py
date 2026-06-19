"""Lexical (BM25) retrieval arm.

The semantic arm (sentence-transformer embeddings) is great at meaning but can
miss an *exact* token the player typed — a proper noun ("Kael"), an item name,
a coined word — because such tokens carry little distributed meaning. BM25 is
the classic lexical complement: it rewards rare exact-term overlap. We fuse the
two arms with Reciprocal Rank Fusion (see ``fusion.py``).

Graceful degradation: if ``rank_bm25`` is unavailable the lexical arm is simply
absent and search falls back to the semantic arm alone (no crash), mirroring the
``VectorMemory._disabled`` philosophy for the embedding runtime.

Algorithm reference: Hindsight (MIT) runs BM25 in Postgres (``tsvector``); that
SQL is not portable, so we reimplement the *idea* with the pure-Python
``rank_bm25`` library over the in-memory corpus of a save's chunks.
"""

from __future__ import annotations

import re

try:  # heavy/optional dependency — degrade gracefully if missing
    from rank_bm25 import BM25Okapi
except Exception:  # pragma: no cover - exercised only when the lib is absent
    BM25Okapi = None  # type: ignore[assignment]


_TOKEN_RE = re.compile(r"[^\W_]+", flags=re.UNICODE)


def is_available() -> bool:
    """True when the BM25 backend can be used."""
    return BM25Okapi is not None


def tokenize(text: str) -> list[str]:
    """Deterministic, Unicode-aware word tokenizer (lowercased).

    Splits on anything that is not a word character, so punctuation and
    underscores act as separators. Keeps accented letters and non-Latin scripts
    (the game ships 10 languages), so a name like ``"Kaël"`` stays one token.
    """
    return _TOKEN_RE.findall(text.lower())


def build_bm25(corpus_texts: list[str]):
    """Build a BM25 index over ``corpus_texts`` (or ``None`` if unavailable).

    Split out from :func:`rank_by_bm25` so callers can *cache* the index when the
    corpus is unchanged (building it tokenises the whole corpus and computes IDF
    — the expensive part), then score many queries against it cheaply.
    """
    if BM25Okapi is None or not corpus_texts:
        return None
    tokenized_corpus = [tokenize(text) for text in corpus_texts]
    # BM25Okapi requires every document to have at least one token; substitute a
    # neutral placeholder for empty docs so indices stay aligned with corpus_ids.
    tokenized_corpus = [toks if toks else [""] for toks in tokenized_corpus]
    return BM25Okapi(tokenized_corpus)


def rank_with_bm25(bm25, query_text: str, corpus_ids: list[str]) -> list[str]:
    """Rank ``corpus_ids`` against a pre-built ``bm25`` index, best first.

    ``corpus_ids`` must be aligned 1:1 with the texts the index was built from.
    Returns an empty list when the index is ``None`` or the query has no usable
    tokens; drops zero-score docs (no lexical signal). Ties keep input order.
    """
    if bm25 is None or not corpus_ids:
        return []
    query_tokens = tokenize(query_text)
    if not query_tokens:
        return []
    scores = bm25.get_scores(query_tokens)
    ranked = sorted(
        zip(corpus_ids, scores),
        key=lambda pair: pair[1],
        reverse=True,
    )
    return [doc_id for doc_id, score in ranked if score > 0.0]


def rank_by_bm25(query_text: str, corpus_ids: list[str], corpus_texts: list[str]) -> list[str]:
    """Rank ``corpus_ids`` by BM25 relevance to ``query_text``, best first.

    Convenience wrapper that builds a one-shot index then scores. Hot paths that
    reuse a stable corpus should cache :func:`build_bm25` and call
    :func:`rank_with_bm25` instead.

    Args:
        query_text: The raw query string.
        corpus_ids: Stable ids, aligned 1:1 with ``corpus_texts``.
        corpus_texts: The chunk texts to score against the query.

    Returns:
        ``corpus_ids`` reordered by descending BM25 score, dropping documents
        whose score is zero (no query-term overlap → no lexical signal). Returns
        an empty list when BM25 is unavailable or the query has no usable tokens.
        Ties keep the input order (deterministic).
    """
    if not corpus_ids:
        return []
    return rank_with_bm25(build_bm25(corpus_texts), query_text, corpus_ids)
