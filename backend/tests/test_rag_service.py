from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.config import Settings
from app.query_intelligence.domain import (
    ExecutedRetrievalStrategy,
    QueryCategory,
    QueryDecision,
    RetrievalProfile,
)
from app.query_intelligence.profiles import profile_config
from app.rag.prompting import INSUFFICIENT_CONTEXT_ANSWER, build_context
from app.rag.retrieval import RetrievedChunk
from app.rag.service import RagService


def settings(**overrides: object) -> Settings:
    return Settings(
        jwt_secret="unit-test-jwt-secret-with-at-least-thirty-two-characters",
        openai_api_key=None,
        openai_embedding_dimensions=2,
        **overrides,
    )


def chunk(text: str = "Employees receive twenty days of annual leave.") -> RetrievedChunk:
    return RetrievedChunk(
        document_id=uuid4(),
        chunk_id=uuid4(),
        filename="handbook.md",
        page=None,
        section="Annual Leave",
        text=text,
        score=0.84,
    )


def query_decision(
    category: QueryCategory = QueryCategory.FAQ,
    profile: RetrievalProfile = RetrievalProfile.FAST,
    used_fallback: bool = False,
) -> QueryDecision:
    return QueryDecision(category=category, profile=profile, used_fallback=used_fallback)


async def test_rag_service_builds_grounded_context_and_real_chunk_citations() -> None:
    retrieved = chunk()
    user_id = uuid4()
    decision = query_decision()
    embedding = SimpleNamespace(dense=AsyncMock(return_value=[[0.1, 0.2]]))
    retriever = SimpleNamespace(search=AsyncMock(return_value=[retrieved]), close=AsyncMock())
    generator = SimpleNamespace(generate=AsyncMock(return_value="Employees receive 20 days."))
    classifier = SimpleNamespace(classify=AsyncMock(return_value=decision))
    query_log_writer = SimpleNamespace(record=AsyncMock(return_value=uuid4()))
    service = RagService(settings(), embedding, retriever, generator, classifier, query_log_writer)

    response = await service.answer("How much annual leave is provided?", user_id, "HR")

    classifier.classify.assert_awaited_once_with("How much annual leave is provided?")
    retriever.search.assert_awaited_once_with([0.1, 0.2], "HR", 3)
    prompt_context = generator.generate.await_args.args[1]
    assert "[SOURCE 1]" in prompt_context
    assert "Filename: handbook.md" in prompt_context
    assert "Section: Annual Leave" in prompt_context
    assert retrieved.text in prompt_context
    assert response.insufficient_context is False
    assert response.sources[0].document_id == retrieved.document_id
    assert response.sources[0].chunk_id == retrieved.chunk_id
    assert response.query_intelligence.category == QueryCategory.FAQ
    assert response.query_intelligence.profile == RetrievalProfile.FAST
    assert response.query_intelligence.executed_strategy == ExecutedRetrievalStrategy.DENSE
    log_args = query_log_writer.record.await_args.args
    assert log_args[:4] == (
        user_id,
        "How much annual leave is provided?",
        decision,
        profile_config(RetrievalProfile.FAST),
    )
    assert isinstance(log_args[4], int)
    assert log_args[4] >= 0


async def test_rag_service_returns_deterministic_insufficient_context_without_llm() -> None:
    decision = query_decision(
        QueryCategory.SPECIFIC_SEARCH,
        RetrievalProfile.BALANCED,
        used_fallback=True,
    )
    embedding = SimpleNamespace(dense=AsyncMock(return_value=[[0.1, 0.2]]))
    retriever = SimpleNamespace(search=AsyncMock(return_value=[]), close=AsyncMock())
    generator = SimpleNamespace(generate=AsyncMock())
    classifier = SimpleNamespace(classify=AsyncMock(return_value=decision))
    query_log_writer = SimpleNamespace(record=AsyncMock(return_value=uuid4()))
    service = RagService(settings(), embedding, retriever, generator, classifier, query_log_writer)

    response = await service.answer("What is the moon office policy?", uuid4(), "Developer")

    assert response.answer == INSUFFICIENT_CONTEXT_ANSWER
    assert response.insufficient_context is True
    assert response.sources == []
    assert response.query_intelligence.profile == RetrievalProfile.BALANCED
    assert response.query_intelligence.candidate_top_k == 8
    assert response.query_intelligence.executed_strategy == (
        ExecutedRetrievalStrategy.DENSE_FALLBACK
    )
    assert response.query_intelligence.classification_fallback is True
    generator.generate.assert_not_awaited()


@pytest.mark.parametrize(
    ("category", "profile", "top_k", "strategy"),
    [
        (QueryCategory.FAQ, RetrievalProfile.FAST, 3, ExecutedRetrievalStrategy.DENSE),
        (
            QueryCategory.SPECIFIC_SEARCH,
            RetrievalProfile.BALANCED,
            8,
            ExecutedRetrievalStrategy.DENSE_FALLBACK,
        ),
        (
            QueryCategory.MULTI_DOC_COMPARISON,
            RetrievalProfile.ACCURATE,
            15,
            ExecutedRetrievalStrategy.DENSE_FALLBACK,
        ),
    ],
)
async def test_rag_service_applies_profile_top_k_and_reports_actual_strategy(
    category: QueryCategory,
    profile: RetrievalProfile,
    top_k: int,
    strategy: ExecutedRetrievalStrategy,
) -> None:
    embedding = SimpleNamespace(dense=AsyncMock(return_value=[[0.1, 0.2]]))
    retriever = SimpleNamespace(search=AsyncMock(return_value=[]), close=AsyncMock())
    classifier = SimpleNamespace(classify=AsyncMock(return_value=query_decision(category, profile)))
    query_log_writer = SimpleNamespace(record=AsyncMock(return_value=uuid4()))
    service = RagService(
        settings(),
        embedding,
        retriever,
        SimpleNamespace(generate=AsyncMock()),
        classifier,
        query_log_writer,
    )

    response = await service.answer("Question", uuid4(), "Executive")

    retriever.search.assert_awaited_once_with([0.1, 0.2], "Executive", top_k)
    assert response.query_intelligence.candidate_top_k == top_k
    assert response.query_intelligence.executed_strategy == strategy


@pytest.mark.parametrize(
    ("embedding_result", "retrieval_result", "generation_result", "expected_code"),
    [
        (RuntimeError("embedding unavailable"), [], "unused", "QUERY_EMBEDDING_FAILED"),
        ([[0.1, 0.2]], RuntimeError("qdrant unavailable"), "unused", "RETRIEVAL_FAILED"),
        ([[0.1, 0.2]], [chunk()], RuntimeError("openai unavailable"), "ANSWER_GENERATION_FAILED"),
    ],
)
async def test_rag_service_maps_provider_failures_to_safe_errors(
    embedding_result: object,
    retrieval_result: object,
    generation_result: object,
    expected_code: str,
) -> None:
    embedding = SimpleNamespace(
        dense=AsyncMock(
            side_effect=embedding_result if isinstance(embedding_result, Exception) else None,
            return_value=embedding_result,
        )
    )
    retriever = SimpleNamespace(
        search=AsyncMock(
            side_effect=retrieval_result if isinstance(retrieval_result, Exception) else None,
            return_value=retrieval_result,
        ),
        close=AsyncMock(),
    )
    generator = SimpleNamespace(
        generate=AsyncMock(
            side_effect=generation_result if isinstance(generation_result, Exception) else None,
            return_value=generation_result,
        )
    )
    classifier = SimpleNamespace(classify=AsyncMock(return_value=query_decision()))
    query_log_writer = SimpleNamespace(record=AsyncMock(return_value=uuid4()))
    service = RagService(settings(), embedding, retriever, generator, classifier, query_log_writer)

    with pytest.raises(HTTPException) as error:
        await service.answer("Question", uuid4(), "HR")

    assert error.value.status_code == 503
    assert error.value.detail["code"] == expected_code


async def test_rag_service_maps_query_log_failure_to_safe_error() -> None:
    service = RagService(
        settings(),
        SimpleNamespace(dense=AsyncMock(return_value=[[0.1, 0.2]])),
        SimpleNamespace(search=AsyncMock(return_value=[]), close=AsyncMock()),
        SimpleNamespace(generate=AsyncMock()),
        SimpleNamespace(classify=AsyncMock(return_value=query_decision())),
        SimpleNamespace(record=AsyncMock(side_effect=RuntimeError("database unavailable"))),
    )

    with pytest.raises(HTTPException) as error:
        await service.answer("Question", uuid4(), "HR")

    assert error.value.status_code == 503
    assert error.value.detail["code"] == "QUERY_LOG_FAILED"


def test_context_builder_preserves_boundaries_and_respects_limit() -> None:
    first = chunk("First authorized source")
    second = chunk("Second source that should not fit")
    first_context, _ = build_context([first], 10000)

    context, included = build_context([first, second], len(first_context))

    assert context == first_context
    assert included == [first]
