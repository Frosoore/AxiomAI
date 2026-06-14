"""
tests/test_vector_memory.py

Unit tests for llm_engine/vector_memory.py.

ChromaDB is used with a real PersistentClient (tmp_path isolation).
The SentenceTransformerEmbeddingFunction is mocked with a fast fake that
returns random-but-consistent unit vectors, avoiding any model downloads
and making the test suite deterministic and instant.
"""

import hashlib
import math
import random
from pathlib import Path
from unittest.mock import patch
from typing import List

import pytest

import chromadb
from chromadb import EmbeddingFunction, Documents, Embeddings

from axiom.memory import VectorMemory, _COLLECTION_NAME, _EmbeddingSingleton


# ---------------------------------------------------------------------------
# Fake embedding function — proper ChromaDB EmbeddingFunction subclass
# ---------------------------------------------------------------------------

class _FakeEmbeddingFn(EmbeddingFunction[Documents]):
    """Deterministic 32-dim unit-vector embedder for testing.

    Produces consistent vectors by hashing each input string.
    Avoids any model download; tests run instantly.
    """

    def __call__(self, input: Documents) -> Embeddings:  # noqa: A002
        embeddings: Embeddings = []
        for text in input:
            seed = int(hashlib.md5(str(text).encode()).hexdigest(), 16) % (2 ** 32)
            rng = random.Random(seed)
            vec = [rng.gauss(0, 1) for _ in range(32)]
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            embeddings.append([x / norm for x in vec])
        return embeddings


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def vm(tmp_path: Path):
    """Provide a VectorMemory instance with mocked embeddings and tmp storage.

    On injecte le faux embedder dans le singleton (et non via un patch autour du
    seul constructeur, qui est paresseux : la connexion réelle — et donc le
    chargement de torch — n'a lieu qu'au premier embed/query, hors du patch).
    Résultat : tests déterministes, rapides, et sans dépendance native torch
    (indispensable là où ses DLL ne se chargent pas, ex. Windows sans VC++).
    """
    saved = _EmbeddingSingleton._instance
    _EmbeddingSingleton._instance = _FakeEmbeddingFn()
    try:
        yield VectorMemory(persist_dir=str(tmp_path / "chroma"))
    finally:
        _EmbeddingSingleton._instance = saved


# ---------------------------------------------------------------------------
# embed_chunk
# ---------------------------------------------------------------------------

class TestEmbedChunk:
    def test_returns_string_id(self, vm: VectorMemory) -> None:
        """embed_chunk returns the new chunk's id as a 36-char UUID string."""
        doc_id = vm.embed_chunk("save1", 1, "The knight enters the dungeon.")
        assert isinstance(doc_id, str)
        assert len(doc_id) == 36  # UUID format

    def test_returns_unique_ids(self, vm: VectorMemory) -> None:
        """Distinct chunks get distinct ids."""
        id1 = vm.embed_chunk("save1", 1, "chunk one")
        id2 = vm.embed_chunk("save1", 2, "chunk two")
        assert id1 != id2

    def test_empty_text_raises_value_error(self, vm: VectorMemory) -> None:
        """Embedding an empty string raises ValueError."""
        with pytest.raises(ValueError, match="empty"):
            vm.embed_chunk("save1", 1, "")

    def test_whitespace_only_raises_value_error(self, vm: VectorMemory) -> None:
        """Embedding whitespace-only text raises ValueError."""
        with pytest.raises(ValueError):
            vm.embed_chunk("save1", 1, "   \n  ")

    def test_chunk_retrievable_after_embed(self, vm: VectorMemory) -> None:
        """A just-embedded chunk is returned by a semantic query."""
        vm.embed_chunk("save1", 1, "The dragon breathes fire.")
        results = vm.query("save1", "dragon fire", k=1)
        assert len(results) == 1
        assert "dragon" in results[0]["text"]

    def test_metadata_stored_correctly(self, vm: VectorMemory) -> None:
        """The turn_id and chunk_type passed at embed time are returned on query."""
        vm.embed_chunk("save1", 5, "Important event.", chunk_type="dialogue")
        results = vm.query("save1", "important event", k=1)
        assert results[0]["turn_id"] == 5
        assert results[0]["chunk_type"] == "dialogue"

    def test_default_chunk_type_is_narrative(self, vm: VectorMemory) -> None:
        """When chunk_type is omitted it defaults to 'narrative'."""
        vm.embed_chunk("save1", 1, "Some narrative text.")
        results = vm.query("save1", "narrative", k=1)
        assert results[0]["chunk_type"] == "narrative"


# ---------------------------------------------------------------------------
# query
# ---------------------------------------------------------------------------

class TestQuery:
    def test_returns_empty_for_unknown_save(self, vm: VectorMemory) -> None:
        """Querying a save with no chunks returns an empty list."""
        vm.embed_chunk("save1", 1, "text for save1")
        results = vm.query("save999", "text", k=5)
        assert results == []

    def test_does_not_return_other_saves_chunks(self, vm: VectorMemory) -> None:
        """A query is scoped to its save and never leaks another save's chunks."""
        vm.embed_chunk("save1", 1, "secret of save one")
        vm.embed_chunk("save2", 1, "secret of save two")
        results = vm.query("save1", "secret", k=5)
        for r in results:
            # All results must belong to save1 — verify via content
            assert "save one" in r["text"]

    def test_returns_at_most_k_results(self, vm: VectorMemory) -> None:
        """A query returns no more than k results."""
        for i in range(10):
            vm.embed_chunk("save1", i, f"chunk number {i}")
        results = vm.query("save1", "chunk", k=3)
        assert len(results) <= 3

    def test_result_contains_required_keys(self, vm: VectorMemory) -> None:
        """Each result carries text, turn_id, chunk_type and distance keys."""
        vm.embed_chunk("save1", 1, "the hero slays the beast")
        results = vm.query("save1", "hero", k=1)
        assert len(results) == 1
        r = results[0]
        assert "text" in r
        assert "turn_id" in r
        assert "chunk_type" in r
        assert "distance" in r

    def test_distance_is_float(self, vm: VectorMemory) -> None:
        """The similarity distance on each result is a float."""
        vm.embed_chunk("save1", 1, "some text")
        results = vm.query("save1", "some text", k=1)
        assert isinstance(results[0]["distance"], float)

    def test_empty_collection_returns_empty(self, vm: VectorMemory) -> None:
        """Querying before anything is embedded returns an empty list."""
        results = vm.query("save1", "anything", k=5)
        assert results == []

    def test_empty_query_text_raises(self, vm: VectorMemory) -> None:
        """An empty query string raises ValueError."""
        with pytest.raises(ValueError):
            vm.query("save1", "")

    def test_k_larger_than_available_does_not_crash(self, vm: VectorMemory) -> None:
        """Requesting more results than exist returns all of them without error."""
        vm.embed_chunk("save1", 1, "only chunk")
        results = vm.query("save1", "only chunk", k=100)
        assert len(results) == 1

    def test_query_filters_by_max_turn_id(self, vm: VectorMemory) -> None:
        """query(max_turn_id=N) excludes chunks from turns later than N."""
        # Arrange: create chunks across different turns
        vm.embed_chunk("save1", 5, "Old memory")
        vm.embed_chunk("save1", 10, "Recent memory")
        vm.embed_chunk("save1", 15, "Future-ish memory")

        # Act: query with max_turn_id = 10
        # Results should only include turns 5 and 10
        results = vm.query("save1", "memory", k=10, max_turn_id=10)

        # Assert
        assert len(results) == 2
        turn_ids = {r["turn_id"] for r in results}
        assert 5 in turn_ids
        assert 10 in turn_ids
        assert 15 not in turn_ids


# ---------------------------------------------------------------------------
# rollback
# ---------------------------------------------------------------------------

class TestRollback:
    def test_deletes_chunks_after_target_turn(self, vm: VectorMemory) -> None:
        """rollback(target) removes every chunk from turns after the target."""
        vm.embed_chunk("save1", 3, "Turn 3 event")
        vm.embed_chunk("save1", 6, "Turn 6 event")
        vm.embed_chunk("save1", 9, "Turn 9 event")

        deleted = vm.rollback("save1", target_turn_id=5)

        assert deleted == 2  # turns 6 and 9
        remaining = vm.query("save1", "event", k=10)
        assert all(r["turn_id"] <= 5 for r in remaining)

    def test_preserves_chunks_at_or_before_target(self, vm: VectorMemory) -> None:
        """rollback keeps chunks from turns at or before the target."""
        vm.embed_chunk("save1", 1, "Turn 1 story")
        vm.embed_chunk("save1", 5, "Turn 5 story")
        vm.embed_chunk("save1", 10, "Turn 10 story")

        vm.rollback("save1", target_turn_id=5)

        remaining = vm.query("save1", "story", k=10)
        turn_ids = {r["turn_id"] for r in remaining}
        assert 1 in turn_ids
        assert 5 in turn_ids
        assert 10 not in turn_ids

    def test_rollback_to_zero_deletes_all(self, vm: VectorMemory) -> None:
        """rollback(0) removes every chunk for the save."""
        for i in range(1, 6):
            vm.embed_chunk("save1", i, f"event at turn {i}")

        deleted = vm.rollback("save1", target_turn_id=0)

        assert deleted == 5
        assert vm.query("save1", "event", k=10) == []

    def test_rollback_does_not_affect_other_saves(self, vm: VectorMemory) -> None:
        """A rollback on one save leaves other saves' chunks untouched."""
        vm.embed_chunk("save1", 10, "save1 future event")
        vm.embed_chunk("save2", 10, "save2 future event")

        vm.rollback("save1", target_turn_id=5)

        save2_results = vm.query("save2", "save2 future event", k=5)
        assert len(save2_results) == 1

    def test_rollback_beyond_all_turns_deletes_nothing(self, vm: VectorMemory) -> None:
        """Rolling back past the latest turn deletes nothing (count 0)."""
        vm.embed_chunk("save1", 3, "event")
        deleted = vm.rollback("save1", target_turn_id=100)
        assert deleted == 0

    def test_rollback_empty_collection_returns_zero(self, vm: VectorMemory) -> None:
        """Rolling back an empty collection returns a deleted count of 0."""
        deleted = vm.rollback("save1", target_turn_id=5)
        assert deleted == 0

    def test_returns_correct_count(self, vm: VectorMemory) -> None:
        """rollback returns the exact number of chunks it deleted."""
        for i in range(1, 8):
            vm.embed_chunk("save1", i, f"chunk {i}")

        deleted = vm.rollback("save1", target_turn_id=4)
        assert deleted == 3  # turns 5, 6, 7


# ---------------------------------------------------------------------------
# Embedding model is loaded OFFLINE when already cached
# ---------------------------------------------------------------------------

class TestEmbeddingSingletonOffline:
    """The embedding model must load without a HF Hub network round-trip when
    it is already cached. That HEAD request stalls ~90s on hosts with broken
    IPv6 routing to huggingface.co and runs on the first turn of every session,
    so the narrative never seems to arrive (regression guard)."""

    @pytest.fixture(autouse=True)
    def _reset_singleton(self):
        _EmbeddingSingleton._instance = None
        yield
        _EmbeddingSingleton._instance = None

    def test_loads_with_local_files_only(self) -> None:
        """The cached fast path passes local_files_only=True (no network)."""
        with patch(
            "chromadb.utils.embedding_functions.SentenceTransformerEmbeddingFunction"
        ) as fake:
            fake.return_value = _FakeEmbeddingFn()
            _EmbeddingSingleton.get()

        fake.assert_called_once()
        assert fake.call_args.kwargs.get("local_files_only") is True

    def test_falls_back_to_online_when_not_cached(self) -> None:
        """If the offline load fails (model not on disk), retry online once."""
        attempts: list[bool] = []

        def _side_effect(*args, **kwargs):
            local_only = kwargs.get("local_files_only", False)
            attempts.append(local_only)
            if local_only:
                raise OSError("model not found in local cache")
            return _FakeEmbeddingFn()

        with patch(
            "chromadb.utils.embedding_functions.SentenceTransformerEmbeddingFunction",
            side_effect=_side_effect,
        ):
            result = _EmbeddingSingleton.get()

        # First attempt offline (raised), second attempt online (succeeded).
        assert attempts == [True, False]
        assert isinstance(result, _FakeEmbeddingFn)

    def test_singleton_caches_instance(self) -> None:
        """The model is built once and reused across calls."""
        with patch(
            "chromadb.utils.embedding_functions.SentenceTransformerEmbeddingFunction"
        ) as fake:
            fake.return_value = _FakeEmbeddingFn()
            first = _EmbeddingSingleton.get()
            second = _EmbeddingSingleton.get()

        assert first is second
        fake.assert_called_once()
