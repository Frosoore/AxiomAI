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

import uuid
from typing import Any

# Lazy imports for heavy libraries
try:
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
except ImportError:
    SentenceTransformerEmbeddingFunction = None


_COLLECTION_NAME: str = "narrative_memory"
_EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

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

    def __init__(self, persist_dir: str) -> None:
        self._persist_dir = persist_dir
        self._chroma_client = None
        self._collection = None
        # Set True if the embedding runtime can't load (e.g. torch native libs
        # missing on Windows). Semantic memory then degrades to a no-op so the
        # game stays playable instead of crashing every turn.
        self._disabled = False

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
    ) -> str:
        """Embed a text chunk and store it with turn_id metadata."""
        if not text or not text.strip():
            raise ValueError("Cannot embed empty or whitespace-only text.")

        self._ensure_connected()
        if self._disabled:
            return ""
        doc_id = str(uuid.uuid4())
        self._collection.add(
            documents=[text],
            metadatas=[{
                "save_id": save_id,
                "turn_id": turn_id,
                "chunk_type": chunk_type,
            }],
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
    ) -> list[dict[str, Any]]:
        """Retrieve the top-k most relevant chunks using Time-Weighted search."""
        if not query_text or not query_text.strip():
            raise ValueError("Query text must not be empty.")

        self._ensure_connected()
        if self._disabled:
            return []
        # Fetch more candidates than k to allow for re-ranking
        candidate_count = max(k * 3, 20)
        
        # Build filter condition
        where_cond: dict[str, Any] = {"save_id": save_id}
        if max_turn_id is not None:
            where_cond = {
                "$and": [
                    {"save_id": {"$eq": save_id}},
                    {"turn_id": {"$lte": max_turn_id}}
                ]
            }

        # How many docs exist for this save. Each save has its OWN collection
        # (persist_dir is per save_id), so count() is exactly this save's chunk
        # count — a cheap metadata read, instead of get() which used to
        # materialise every chunk's document + metadata just to size the query.
        available = self._collection.count()
        if available == 0:
            return []

        fetch_k = min(candidate_count, available)

        results = self._collection.query(
            query_texts=[query_text],
            n_results=fetch_k,
            where=where_cond,
        )

        candidates: list[dict[str, Any]] = []
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for doc, meta, dist in zip(documents, metadatas, distances):
            turn_id = int(meta.get("turn_id", 0))
            chunk_type = str(meta.get("chunk_type", "narrative"))
            
            # 1. Semantic Score (0.0 to 1.0, 1.0 is perfect match)
            # ChromaDB cosine distance: 0.0 is perfect, 2.0 is opposite
            semantic_score = max(0.0, 1.0 - (float(dist) / 2.0))
            
            # 2. Recency Weight (0.1 to 1.0)
            if current_turn_id is None or chunk_type == "lore" or turn_id == 0:
                time_weight = 1.0
            else:
                # Linear decay: Lose 1% weight per turn of age, cap at 10%
                age = max(0, current_turn_id - turn_id)
                time_weight = max(0.1, 1.0 - (age * 0.01))
            
            final_score = semantic_score * time_weight
            
            candidates.append({
                "text": doc,
                "turn_id": turn_id,
                "chunk_type": chunk_type,
                "distance": float(dist),
                "score": final_score
            })

        # Sort by final score descending and take top k
        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[:k]

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

