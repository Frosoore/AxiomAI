"""Optional cross-encoder reranking.

The retrieval arms (semantic embeddings + BM25) score a document *independently*
of the query's other terms. A **cross-encoder** instead reads the (query,
document) pair *jointly* and judges their relevance directly — the most accurate
ranking signal available, used as the final re-sort after fusion.

It is **OFF by default** and **degrades to a no-op** when unavailable:

- needs a torch model (~90 MB, ``cross-encoder/ms-marco-MiniLM-L-6-v2``), the
  same native runtime that fails on Windows without VC++ (TICKET-070);
- the heavy import / model load is lazy and guarded, so a missing or broken
  runtime simply means "no reranking", never a crash.

Algorithm reference: Hindsight (MIT, ``engine/search/reranking.py``). Local
sentence-transformers cross-encoders return logits → squashed to [0, 1] with a
sigmoid; already-calibrated [0, 1] scores are passed through.
"""

from __future__ import annotations

import math

_DEFAULT_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

_warned = False


def _warn_once(exc: BaseException) -> None:
    global _warned
    if _warned:
        return
    _warned = True
    try:
        from axiom.logger import logger

        logger.warning(
            "Cross-encoder reranking disabled: the model could not load (%s). "
            "Search falls back to fused semantic+lexical ranking. On Windows this "
            "usually means the Microsoft Visual C++ Redistributable (x64) is missing.",
            exc,
        )
    except Exception:
        pass


def _stable_sigmoid(x: float) -> float:
    """Numerically stable logistic sigmoid → (0, 1)."""
    if x >= 0.0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


class CrossEncoderReranker:
    """Lazy wrapper around a sentence-transformers ``CrossEncoder``.

    Args:
        model_name: HuggingFace cross-encoder id (default ms-marco MiniLM).
        model: Pre-built model with a ``predict(pairs)`` method. Injecting one
            bypasses loading entirely — used by tests to stay deterministic and
            offline.
    """

    def __init__(self, model_name: str = _DEFAULT_MODEL, model: object | None = None) -> None:
        self._model_name = model_name
        self._model = model
        self._disabled = False

    def _ensure_loaded(self) -> None:
        if self._model is not None or self._disabled:
            return
        try:
            from sentence_transformers import CrossEncoder
        except Exception as exc:  # torch / sentence-transformers unavailable
            self._disabled = True
            _warn_once(exc)
            return
        # Prefer the offline fast path (cached model, no HF Hub HEAD request that
        # stalls ~90s on hosts with broken IPv6 — same root cause as the
        # embedding singleton). Fall back to a one-time online download.
        try:
            try:
                self._model = CrossEncoder(self._model_name, local_files_only=True)
            except TypeError:
                # Older sentence-transformers without the kwarg.
                self._model = CrossEncoder(self._model_name)
        except Exception:
            try:
                self._model = CrossEncoder(self._model_name)
            except Exception as exc:
                self._disabled = True
                _warn_once(exc)

    def rerank(self, query_text: str, documents: list[str]) -> list[float] | None:
        """Score each document's relevance to the query, in [0, 1].

        Returns scores aligned 1:1 with ``documents``, or ``None`` when the
        reranker is unavailable / fails (the caller then keeps the fused order).
        """
        self._ensure_loaded()
        if self._disabled or self._model is None or not documents:
            return None

        pairs = [[query_text, doc] for doc in documents]
        try:
            raw = self._model.predict(pairs)
        except Exception as exc:
            self._disabled = True
            _warn_once(exc)
            return None

        scores = [float(s) for s in raw]
        if not scores:
            return None

        # Calibrated rerankers already emit [0, 1] — keep their absolute
        # confidence. Local models emit logits — sigmoid maps them to (0, 1).
        already_unit = min(scores) >= 0.0 and max(scores) <= 1.0
        out: list[float] = []
        for s in scores:
            v = 0.0 if math.isnan(s) else (s if already_unit else _stable_sigmoid(s))
            out.append(v)
        return out
