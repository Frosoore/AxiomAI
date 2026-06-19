"""tests/test_retrieval_fusion.py

Unit tests for axiom/retrieval/ — rank fusion (RRF) and the BM25 lexical arm.
Pure-Python, deterministic, no ChromaDB / no model download.
"""

from axiom.retrieval import fusion, lexical
from axiom.retrieval.reranker import CrossEncoderReranker, _stable_sigmoid


class TestReciprocalRankFusion:
    def test_empty_input_returns_empty(self) -> None:
        assert fusion.reciprocal_rank_fusion([]) == []
        assert fusion.reciprocal_rank_fusion([[], []]) == []

    def test_single_list_preserves_order(self) -> None:
        fused = fusion.reciprocal_rank_fusion([["a", "b", "c"]])
        assert [doc_id for doc_id, _ in fused] == ["a", "b", "c"]

    def test_doc_in_both_arms_outranks_single_arm_doc(self) -> None:
        """A document present in both arms accumulates score from both and beats
        a document that tops only one arm."""
        semantic = ["shared", "sem_only"]
        lexical_arm = ["shared", "lex_only"]
        fused = fusion.reciprocal_rank_fusion([semantic, lexical_arm])
        order = [doc_id for doc_id, _ in fused]
        assert order[0] == "shared"
        assert set(order) == {"shared", "sem_only", "lex_only"}

    def test_scores_match_rrf_formula(self) -> None:
        fused = dict(fusion.reciprocal_rank_fusion([["a", "b"], ["b"]], k=60))
        # a: only semantic rank 1 → 1/61. b: rank 2 then rank 1 → 1/62 + 1/61.
        assert fused["a"] == 1 / 61
        assert fused["b"] == 1 / 62 + 1 / 61
        assert fused["b"] > fused["a"]

    def test_deterministic_tie_break_by_first_appearance(self) -> None:
        # Two docs with identical RRF score (each #1 in one arm); first-seen wins.
        fused = fusion.reciprocal_rank_fusion([["x"], ["y"]])
        assert [doc_id for doc_id, _ in fused] == ["x", "y"]


class TestCapPerSource:
    def test_caps_long_arm(self) -> None:
        assert fusion.cap_per_source(["a", "b", "c", "d"], 2) == ["a", "b"]

    def test_no_cap_when_disabled_or_short(self) -> None:
        assert fusion.cap_per_source(["a", "b"], 0) == ["a", "b"]
        assert fusion.cap_per_source(["a", "b"], 5) == ["a", "b"]


class TestLexicalArm:
    def test_available(self) -> None:
        assert lexical.is_available() is True  # rank_bm25 is a declared dependency

    def test_tokenize_is_lowercase_and_unicode(self) -> None:
        assert lexical.tokenize("Kaël, the Half-Elf!") == ["kaël", "the", "half", "elf"]

    def test_exact_name_match_ranks_first(self) -> None:
        ids = ["c1", "c2", "c3"]
        texts = [
            "The merchant sells bread and cheese in the market.",
            "Zylbrax the sorcerer raised the dead at midnight.",
            "A quiet river runs past the sleeping village.",
        ]
        ranked = lexical.rank_by_bm25("Zylbrax", ids, texts)
        assert ranked[0] == "c2"

    def test_no_overlap_returns_empty(self) -> None:
        ranked = lexical.rank_by_bm25(
            "spaceship", ["c1"], ["a medieval castle on a hill"]
        )
        assert ranked == []

    def test_empty_query_tokens_returns_empty(self) -> None:
        assert lexical.rank_by_bm25("!!! ___", ["c1"], ["some text"]) == []


class _FakeCrossEncoder:
    """Returns a fixed logit per document (by substring match), deterministic."""

    def __init__(self, logit_by_keyword: dict[str, float]):
        self._map = logit_by_keyword

    def predict(self, pairs):
        out = []
        for _query, doc in pairs:
            score = -5.0
            for kw, logit in self._map.items():
                if kw in doc:
                    score = logit
            out.append(score)
        return out


class TestCrossEncoderReranker:
    def test_stable_sigmoid_bounds(self) -> None:
        assert _stable_sigmoid(0.0) == 0.5
        assert 0.0 < _stable_sigmoid(-50.0) < 0.01
        assert 0.99 < _stable_sigmoid(50.0) <= 1.0

    def test_disabled_when_model_unavailable(self) -> None:
        """No injected model and no torch model on disk → no-op (None), no crash."""
        r = CrossEncoderReranker(model_name="does-not-exist/none")
        # Force the loader to give up without a real download attempt.
        r._disabled = True
        assert r.rerank("query", ["a", "b"]) is None

    def test_injected_model_scores_in_unit_range(self) -> None:
        r = CrossEncoderReranker(model=_FakeCrossEncoder({"dragon": 4.0, "bread": -3.0}))
        scores = r.rerank("dragon", ["a dragon roars", "fresh bread"])
        assert scores is not None
        assert all(0.0 <= s <= 1.0 for s in scores)
        assert scores[0] > scores[1]  # dragon doc more relevant

    def test_empty_documents_returns_none(self) -> None:
        r = CrossEncoderReranker(model=_FakeCrossEncoder({}))
        assert r.rerank("q", []) is None

    def test_nan_logit_sanitized_to_zero(self) -> None:
        r = CrossEncoderReranker(model=_FakeCrossEncoder({"x": float("nan")}))
        scores = r.rerank("q", ["x marks it"])
        assert scores == [0.0]
