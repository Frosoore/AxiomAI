"""
llm_engine/vector_memory.py

Local vector-database memory for Axiom AI narrative chunks.

Every piece of narrative embedded here carries a `turn_id` metadata tag.
This enables the surgical rollback required by the Checkpoint system:
when the player rewinds to turn N, all chunks with turn_id > N are
permanently deleted so they cannot bleed into the rebuilt timeline.

Backend: ChromaDB (persistent, local)
Embedding model: sentence-transformers all-MiniLM-L6-v2 (fully offline)

Collection layout
-----------------
Collection name : "narrative_memory"
Document        : the text chunk
Metadata fields : save_id (str), turn_id (int), chunk_type (str)
ID              : UUID string, generated per chunk
"""

import json
import uuid
from typing import Any

from axiom.retrieval import fusion, lexical

# Lazy imports for heavy libraries
try:
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
except ImportError:
    SentenceTransformerEmbeddingFunction = None


_COLLECTION_NAME: str = "narrative_memory"
_EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

# --- Scoring calibration ----------------------------------------------------
# Algorithm adapted from Hindsight (MIT, search/reranking.py::apply_combined_scoring).
# Instead of letting recency *multiply down* a relevant memory (old behaviour:
# semantic × time_weight, time_weight in [0.10, 1.0] — a 200-turn-old but highly
# relevant memory was crushed to 10% of its score), recency is applied as a
# *multiplicative modulation around a neutral 0.5*:
#
#     recency_boost = 1 + RECENCY_ALPHA * (recency - 0.5)   # in [1-α/2, 1+α/2]
#     final_score   = semantic_score * recency_boost
#
# So semantic relevance stays the dominant signal and recency only nudges the
# order (±α/2). recency itself decays linearly over the turn horizon and is held
# *neutral* (0.5 → boost 1.0) for lore / turn 0 / when no current turn is known.
_RECENCY_ALPHA: float = 0.2        # max relative recency adjustment → ±10%
_RECENCY_TURN_HORIZON: int = 100   # turns over which recency decays to its floor
_RECENCY_FLOOR: float = 0.1        # recency value of the oldest memories

# How many extra candidates each retrieval arm over-fetches before fusion/trim.
_CANDIDATE_FANOUT: int = 3
_CANDIDATE_FLOOR: int = 20

# Flat additive bump for a chunk that mentions a "focus" term (the current
# location, an on-scene character). Adapted from Hindsight's additive strategy
# boost (search/recall_boost.py, "medium" level = 0.2): added to the final score
# (base in ~[0,1] × recency), so on-scene memories surface without overriding a
# strong direct relevance match.
_FOCUS_BOOST: float = 0.2


def _recency_boost(turn_id: int, chunk_type: str, current_turn_id: int | None) -> float:
    """Recency as a multiplicative modulation around a neutral 0.5.

    Returns a factor in ``[1 - α/2, 1 + α/2]``. Held neutral (1.0) for lore, the
    seed turn (0), or when no current turn is known, so old-but-relevant memories
    are nudged, never crushed (see module-level scoring note).
    """
    if current_turn_id is None or chunk_type == "lore" or turn_id == 0:
        recency = 0.5
    else:
        age = max(0, current_turn_id - turn_id)
        recency = max(_RECENCY_FLOOR, 1.0 - (age / _RECENCY_TURN_HORIZON))
    return 1.0 + _RECENCY_ALPHA * (recency - 0.5)


_runtime_warned = False


def _warn_runtime_unavailable_once(exc: BaseException) -> None:
    """Log a single, actionable warning when the embedding runtime won't load.

    Typical cause on Windows: torch's native libraries fail to load (WinError
    126) because the Microsoft Visual C++ Redistributable is not installed.
    """
    global _runtime_warned
    if _runtime_warned:
        return
    _runtime_warned = True
    try:
        from axiom.logger import logger

        logger.warning(
            "Semantic memory disabled: the embedding runtime could not load (%s). "
            "Gameplay continues without long-term narrative recall. On Windows this "
            "usually means the Microsoft Visual C++ Redistributable (x64) is missing.",
            exc,
        )
    except Exception:
        pass


def preload_embedding_runtime() -> bool:
    """Force torch's native runtime to load on the *calling* (main) thread.

    The sentence-transformers embedding model is loaded and used on worker
    threads (VectorInitWorker / NarrativeWorker). The first encode lazily pulls
    in ``torch._dynamo`` → ``triton``, which ``dlopen()``s ``libtriton.so``.
    Doing that ``dlopen`` from a secondary thread while Qt is running segfaults
    (native crash, no Python traceback). Importing it once here, on the main
    thread at startup, makes the later cross-thread use safe.

    Call this from the GUI/CLI entry point *before* any worker thread touches
    VectorMemory. Idempotent, never raises. Returns True if the runtime was
    pre-loaded, False if torch is unavailable (e.g. headless test stubs).
    """
    try:
        import torch  # noqa: F401  — heavy import, front-loaded on purpose
        import torch._dynamo  # noqa: F401  — triggers the libtriton.so dlopen here
        return True
    except Exception:
        # torch absent or its internal layout changed: the worst case is the
        # pre-fix behaviour, so we degrade silently rather than block startup.
        return False


class _EmbeddingSingleton:
    """Ensures we only load the heavy transformer model once per session."""
    _instance = None

    @classmethod
    def get(cls):
        if cls._instance is None:
            from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
            try:
                # Model already cached → load it WITHOUT a network round-trip.
                # sentence-transformers otherwise sends a HEAD request to the HF
                # Hub on every load to check for updates; on hosts with broken
                # IPv6 routing to huggingface.co that request stalls ~90s (the
                # same root cause as the Gemini IPv4FirstTransport fix), and it
                # runs on the *first turn of every session*, so the narrative
                # never seems to arrive. local_files_only skips the check.
                cls._instance = SentenceTransformerEmbeddingFunction(
                    model_name=_EMBEDDING_MODEL, local_files_only=True
                )
            except Exception:
                # First-ever launch (or a cleared cache): the model is not on
                # disk yet, so allow the one-time online download. Every later
                # session then takes the offline fast path above.
                cls._instance = SentenceTransformerEmbeddingFunction(
                    model_name=_EMBEDDING_MODEL
                )
        return cls._instance


class VectorMemory:
    """Local semantic memory store backed by ChromaDB.

    Args:
        persist_dir: Filesystem path where ChromaDB will store its data.
                     Created automatically if it does not exist.
    """

    def __init__(self, persist_dir: str, reranker: Any | None = None) -> None:
        self._persist_dir = persist_dir
        self._chroma_client = None
        self._collection = None
        # Set True if the embedding runtime can't load (e.g. torch native libs
        # missing on Windows). Semantic memory then degrades to a no-op so the
        # game stays playable instead of crashing every turn.
        self._disabled = False
        # Optional cross-encoder reranker (CrossEncoderReranker). OFF unless the
        # caller injects one; it self-disables to a no-op if its model can't load.
        self._reranker = reranker
        # BM25 index cache, keyed by the query's where-filter signature. Building a
        # BM25 index tokenises the whole corpus + computes IDF (the expensive part
        # of the lexical arm); rebuilding it identically every turn is wasteful for
        # a corpus that did not change (e.g. the lore subset, embedded once per
        # session). Value: (fingerprint, bm25, built_ids). The fingerprint is the
        # corpus's id-set — sound because every content change mints a fresh chunk
        # uuid (embed adds; update_turn_narrative deletes-then-adds), so an
        # unchanged id-set means unchanged content. ``built_ids`` is the id order
        # the index was built against (Chroma's get() does not promise a stable
        # order across calls, and BM25 scoring aligns by position). The growing
        # narrative corpus changes its id-set each turn and correctly rebuilds.
        # (TICKET-078)
        self._bm25_cache: dict[str, tuple[int, Any, list[str]]] = {}

    def _ensure_connected(self) -> None:
        """Lazy-init ChromaDB only when first used.

        If the embedding runtime is unavailable, the store is marked disabled
        rather than raising: callers then get empty results / no-ops.
        """
        if self._collection is not None or self._disabled:
            return

        try:
            import chromadb
            self._chroma_client = chromadb.PersistentClient(path=self._persist_dir)
            self._collection = self._chroma_client.get_or_create_collection(
                name=_COLLECTION_NAME,
                embedding_function=_EmbeddingSingleton.get(),
            )
        except Exception as exc:
            self._disabled = True
            _warn_runtime_unavailable_once(exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def embed_chunk(
        self,
        save_id: str,
        turn_id: int,
        text: str,
        chunk_type: str = "narrative",
        metadata_extra: dict[str, Any] | None = None,
    ) -> str:
        """Embed a text chunk and store it with turn_id metadata.

        Args:
            metadata_extra: Optional extra metadata merged into the chunk record
                (e.g. a lore entry's ``entry_id``). The core keys (save_id,
                turn_id, chunk_type) always take precedence.
        """
        if not text or not text.strip():
            raise ValueError("Cannot embed empty or whitespace-only text.")

        self._ensure_connected()
        if self._disabled:
            return ""
        doc_id = str(uuid.uuid4())
        metadata: dict[str, Any] = dict(metadata_extra or {})
        metadata.update({
            "save_id": save_id,
            "turn_id": turn_id,
            "chunk_type": chunk_type,
        })
        self._collection.add(
            documents=[text],
            metadatas=[metadata],
            ids=[doc_id],
        )
        return doc_id

    def query(
        self,
        save_id: str,
        query_text: str,
        k: int = 5,
        current_turn_id: int | None = None,
        max_turn_id: int | None = None,
        focus_terms: list[str] | None = None,
        chunk_type: str | None = None,
        exclude_chunk_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve the top-k most relevant chunks using hybrid scored search.

        Args:
            focus_terms: Optional "here-and-now" terms (current location name,
                on-scene character names). A chunk whose text mentions any of
                them gets a small additive boost so memories about the current
                scene surface more readily. No effect when omitted.
            chunk_type: Restrict the search to chunks of this type (e.g. "lore").
            exclude_chunk_type: Exclude chunks of this type (e.g. the narrative
                query passes "lore" so lore entries never eat its k budget).

        Each returned candidate carries ``entry_id`` (the chunk's source id when
        one was stored, e.g. a lore entry's id; otherwise ``None``).
        """
        if not query_text or not query_text.strip():
            raise ValueError("Query text must not be empty.")

        self._ensure_connected()
        if self._disabled:
            return []
        # Over-fetch candidates per arm before fusion/trim so a good chunk that
        # ranks mid-pack in one arm can still be rescued by the other.
        fanout = max(k * _CANDIDATE_FANOUT, _CANDIDATE_FLOOR)

        # Build filter condition (shared by both arms). Chroma needs an explicit
        # $and once there is more than one clause.
        clauses: list[dict[str, Any]] = [{"save_id": {"$eq": save_id}}]
        if max_turn_id is not None:
            clauses.append({"turn_id": {"$lte": max_turn_id}})
        if chunk_type is not None:
            clauses.append({"chunk_type": {"$eq": chunk_type}})
        if exclude_chunk_type is not None:
            clauses.append({"chunk_type": {"$ne": exclude_chunk_type}})
        where_cond: dict[str, Any] = clauses[0] if len(clauses) == 1 else {"$and": clauses}

        # Each save has its OWN collection (persist_dir is per save_id), so
        # count() is exactly this save's chunk count — a cheap metadata read.
        available = self._collection.count()
        if available == 0:
            return []

        fetch_k = min(fanout, available)

        # --- Arm 1: semantic (ChromaDB ANN) -------------------------------
        sem = self._collection.query(
            query_texts=[query_text],
            n_results=fetch_k,
            where=where_cond,
        )
        sem_ids = sem.get("ids", [[]])[0]
        sem_docs = sem.get("documents", [[]])[0]
        sem_metas = sem.get("metadatas", [[]])[0]
        sem_dists = sem.get("distances", [[]])[0]

        # Per-doc record store, keyed by Chroma's stable chunk id.
        records: dict[str, dict[str, Any]] = {}
        for did, doc, meta, dist in zip(sem_ids, sem_docs, sem_metas, sem_dists):
            records[did] = {
                "text": doc,
                "turn_id": int(meta.get("turn_id", 0)),
                "chunk_type": str(meta.get("chunk_type", "narrative")),
                "entry_id": meta.get("entry_id"),
                "distance": float(dist),
                "semantic_score": max(0.0, 1.0 - (float(dist) / 2.0)),
            }
        semantic_ranked = list(sem_ids)

        # --- Arm 2: lexical (BM25 over the save's corpus) -----------------
        # Lexical recall can surface an exact token (a name, an item) the
        # embedding arm misses. Needs the actual texts, so we fetch the corpus
        # here (degrades to semantic-only if rank_bm25 is unavailable).
        lexical_ranked: list[str] = []
        if lexical.is_available():
            corpus = self._collection.get(
                where=where_cond,
                include=["documents", "metadatas"],
            )
            corpus_ids = corpus.get("ids", []) or []
            corpus_docs = corpus.get("documents", []) or []
            corpus_metas = corpus.get("metadatas", []) or []
            # Reuse a cached BM25 index when the corpus (id-set) is unchanged;
            # otherwise (re)build and cache it. Skips tokenising + IDF for stable
            # corpora like the lore subset (TICKET-078).
            cache_key = json.dumps(where_cond, sort_keys=True)
            fingerprint = hash(frozenset(corpus_ids))
            cached = self._bm25_cache.get(cache_key)
            if cached is not None and cached[0] == fingerprint:
                _, bm25, ranked_ids = cached
            else:
                bm25 = lexical.build_bm25(corpus_docs)
                ranked_ids = corpus_ids  # the order the index was built against
                # A handful of stable query shapes in play; rewind/replay can add
                # transient max_turn_id variants, so cap to avoid slow growth.
                if len(self._bm25_cache) >= 8:
                    self._bm25_cache.clear()
                self._bm25_cache[cache_key] = (fingerprint, bm25, ranked_ids)
            lexical_ranked = lexical.rank_with_bm25(bm25, query_text, ranked_ids)[:fetch_k]
            # Backfill records for lexical-only hits the semantic arm never saw.
            meta_by_id = dict(zip(corpus_ids, corpus_metas))
            doc_by_id = dict(zip(corpus_ids, corpus_docs))
            for did in lexical_ranked:
                if did not in records:
                    meta = meta_by_id.get(did, {}) or {}
                    records[did] = {
                        "text": doc_by_id.get(did, ""),
                        "turn_id": int(meta.get("turn_id", 0)),
                        "chunk_type": str(meta.get("chunk_type", "narrative")),
                        "entry_id": meta.get("entry_id"),
                        "distance": None,
                        "semantic_score": 0.0,
                    }

        # --- Fuse + score -------------------------------------------------
        if lexical_ranked:
            # Two arms → Reciprocal Rank Fusion. The (batch-normalised) RRF score
            # is the post-fusion base: it stays smooth (a doc found by both arms
            # outscores one found by a single arm) and incomparable per-arm scales
            # never leak in. No cross-encoder yet — item 3 will replace this base.
            fused = fusion.reciprocal_rank_fusion([
                fusion.cap_per_source(semantic_ranked, fetch_k),
                fusion.cap_per_source(lexical_ranked, fetch_k),
            ])
            order = [doc_id for doc_id, _ in fused]
            max_rrf = max((score for _, score in fused), default=1.0) or 1.0
            base_by_id = {doc_id: score / max_rrf for doc_id, score in fused}
        else:
            # Single arm → keep the smooth semantic score as the base.
            order = semantic_ranked
            base_by_id = {did: records[did]["semantic_score"] for did in order}

        # Optional cross-encoder rerank: the most accurate relevance signal,
        # replacing the fused base when enabled. No-op (None) when unavailable,
        # leaving the fused/semantic base untouched.
        if self._reranker is not None and order:
            ce_scores = self._reranker.rerank(
                query_text, [records[did]["text"] for did in order]
            )
            if ce_scores is not None:
                base_by_id = {did: ce_scores[i] for i, did in enumerate(order)}

        # Pre-tokenise focus terms once: a chunk matches a term when all of the
        # term's tokens appear in it (so "Black Keep" needs both, but a single
        # name still matches), avoiding substring false positives.
        focus_token_sets: list[set[str]] = []
        for term in focus_terms or []:
            toks = set(lexical.tokenize(term))
            if toks:
                focus_token_sets.append(toks)

        candidates: list[dict[str, Any]] = []
        for doc_id in order:
            rec = records.get(doc_id)
            if rec is None:
                continue
            boost = _recency_boost(rec["turn_id"], rec["chunk_type"], current_turn_id)
            score = base_by_id[doc_id] * boost
            if focus_token_sets:
                chunk_tokens = set(lexical.tokenize(rec["text"]))
                if any(fs <= chunk_tokens for fs in focus_token_sets):
                    score += _FOCUS_BOOST
            candidates.append({
                "text": rec["text"],
                "turn_id": rec["turn_id"],
                "chunk_type": rec["chunk_type"],
                "entry_id": rec.get("entry_id"),
                "distance": rec["distance"],
                "score": score,
            })

        # Sort by final score descending and take top k
        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[:k]

    def sync_lore(self, save_id: str, entries: list[dict[str, Any]]) -> int:
        """Re-embed this save's Lore Book entries (idempotent).

        Deletes any existing lore chunks for the save, then embeds each entry
        tagged ``chunk_type="lore"`` and ``turn_id=0`` (timeless → survives any
        rewind) with its ``entry_id`` in metadata, so a retrieval hit maps back to
        the structured row for link expansion. Call once per session (and after a
        hot reload) to keep lore embeddings in sync with the definition. No-op
        when the embedding runtime is unavailable.

        Args:
            save_id: The save whose lore embeddings are (re)built.
            entries: Lore rows, each a dict with ``entry_id`` and ``text``.

        Returns:
            The number of entries embedded (0 when embeddings are disabled).
        """
        self._ensure_connected()
        if self._disabled:
            return 0
        # Drop existing lore chunks for this save, then rebuild from the current
        # definition (handles edits / hot reload without leaving stale entries).
        existing = self._collection.get(
            where={"$and": [
                {"save_id": {"$eq": save_id}},
                {"chunk_type": {"$eq": "lore"}},
            ]}
        )
        stale_ids = existing.get("ids", []) or []
        if stale_ids:
            self._collection.delete(ids=stale_ids)

        count = 0
        for entry in entries:
            text = (entry.get("text") or "").strip()
            entry_id = entry.get("entry_id")
            if not text or not entry_id:
                continue
            self.embed_chunk(
                save_id, 0, text, chunk_type="lore",
                metadata_extra={"entry_id": str(entry_id)},
            )
            count += 1
        return count

    def rollback(self, save_id: str, target_turn_id: int) -> int:
        """Delete all chunks for a save with turn_id strictly greater than target."""
        self._ensure_connected()
        if self._disabled:
            return 0
        # ChromaDB's $gt operator requires a numeric type
        result = self._collection.get(
            where={
                "$and": [
                    {"save_id": {"$eq": save_id}},
                    {"turn_id": {"$gt": target_turn_id}},
                ]
            }
        )

        ids_to_delete: list[str] = result["ids"]
        if ids_to_delete:
            self._collection.delete(ids=ids_to_delete)

        return len(ids_to_delete)

    def update_turn_narrative(
        self,
        save_id: str,
        turn_id: int,
        new_text: str,
        chunk_type: str = "narrative",
    ) -> None:
        """Delete existing chunks for this turn and embed the new text.
        """
        self._ensure_connected()
        if self._disabled:
            return
        
        result = self._collection.get(
            where={
                "$and": [
                    {"save_id": {"$eq": save_id}},
                    {"turn_id": {"$eq": turn_id}},
                    {"chunk_type": {"$eq": chunk_type}},
                ]
            }
        )
        ids_to_delete: list[str] = result["ids"]
        if ids_to_delete:
            self._collection.delete(ids=ids_to_delete)
        
        if new_text and new_text.strip():
            self.embed_chunk(save_id, turn_id, new_text, chunk_type)

