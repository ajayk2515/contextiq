from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.config import Settings
from app.rag.reranking import RerankerService, _cross_encoder_model
from app.rag.retrieval import RetrievedChunk


def settings() -> Settings:
    return Settings(
        jwt_secret="unit-test-jwt-secret-with-at-least-thirty-two-characters",
        openai_api_key=None,
        reranker_model="Xenova/ms-marco-MiniLM-L-6-v2",
    )


def chunk(index: int) -> RetrievedChunk:
    return RetrievedChunk(
        document_id=uuid4(),
        chunk_id=uuid4(),
        filename=f"candidate-{index}.md",
        page=index,
        section=f"Candidate {index}",
        text=f"Candidate passage {index}",
        allowed_roles=("Developer",),
        score=1 / (index + 1),
        rank_before=index,
        rrf_score=1 / (index + 1),
    )


def test_cross_encoder_model_is_cpu_only_lazy_and_cached() -> None:
    _cross_encoder_model.cache_clear()
    model = MagicMock()
    try:
        with patch(
            "fastembed.rerank.cross_encoder.TextCrossEncoder", return_value=model
        ) as constructor:
            first = _cross_encoder_model("Xenova/ms-marco-MiniLM-L-6-v2")
            second = _cross_encoder_model("Xenova/ms-marco-MiniLM-L-6-v2")

        assert first is model
        assert second is model
        constructor.assert_called_once_with(
            model_name="Xenova/ms-marco-MiniLM-L-6-v2",
            providers=["CPUExecutionProvider"],
            lazy_load=True,
        )
    finally:
        _cross_encoder_model.cache_clear()


async def test_reranker_orders_by_model_score_and_preserves_ranking_metadata() -> None:
    candidates = [chunk(index) for index in range(1, 7)]
    model = MagicMock()
    model.rerank.return_value = [0.2, 0.95, -0.4, 0.7, 0.5, 0.1]
    reranker = RerankerService(settings(), model)

    result = await reranker.rerank("Compare parental benefits", candidates, 5)

    assert [item.filename for item in result] == [
        "candidate-2.md",
        "candidate-4.md",
        "candidate-5.md",
        "candidate-1.md",
        "candidate-6.md",
    ]
    assert [item.rank_before for item in result] == [2, 4, 5, 1, 6]
    assert [item.rank_after for item in result] == [1, 2, 3, 4, 5]
    assert [item.reranker_score for item in result] == [0.95, 0.7, 0.5, 0.2, 0.1]
    assert result[0].rrf_score == candidates[1].rrf_score
    assert result[0].chunk_id == candidates[1].chunk_id
    model.rerank.assert_called_once_with(
        "Compare parental benefits",
        [candidate.text for candidate in candidates],
        batch_size=6,
    )


async def test_reranker_rejects_incomplete_model_scores() -> None:
    model = MagicMock()
    model.rerank.return_value = [0.5]

    with pytest.raises(RuntimeError, match="unexpected number"):
        await RerankerService(settings(), model).rerank("Question", [chunk(1), chunk(2)], 5)


async def test_reranker_skips_model_for_empty_candidates() -> None:
    model = MagicMock()

    assert await RerankerService(settings(), model).rerank("Question", [], 5) == []
    model.rerank.assert_not_called()
