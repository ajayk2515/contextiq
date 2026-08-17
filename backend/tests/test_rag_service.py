from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.config import Settings
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


async def test_rag_service_builds_grounded_context_and_real_chunk_citations() -> None:
    retrieved = chunk()
    embedding = SimpleNamespace(dense=AsyncMock(return_value=[[0.1, 0.2]]))
    retriever = SimpleNamespace(search=AsyncMock(return_value=[retrieved]), close=AsyncMock())
    generator = SimpleNamespace(generate=AsyncMock(return_value="Employees receive 20 days."))
    service = RagService(settings(), embedding, retriever, generator)

    response = await service.answer("How much annual leave is provided?", "HR")

    retriever.search.assert_awaited_once_with([0.1, 0.2], "HR")
    prompt_context = generator.generate.await_args.args[1]
    assert "[SOURCE 1]" in prompt_context
    assert "Filename: handbook.md" in prompt_context
    assert "Section: Annual Leave" in prompt_context
    assert retrieved.text in prompt_context
    assert response.insufficient_context is False
    assert response.sources[0].document_id == retrieved.document_id
    assert response.sources[0].chunk_id == retrieved.chunk_id


async def test_rag_service_returns_deterministic_insufficient_context_without_llm() -> None:
    embedding = SimpleNamespace(dense=AsyncMock(return_value=[[0.1, 0.2]]))
    retriever = SimpleNamespace(search=AsyncMock(return_value=[]), close=AsyncMock())
    generator = SimpleNamespace(generate=AsyncMock())
    service = RagService(settings(), embedding, retriever, generator)

    response = await service.answer("What is the moon office policy?", "Developer")

    assert response.answer == INSUFFICIENT_CONTEXT_ANSWER
    assert response.insufficient_context is True
    assert response.sources == []
    generator.generate.assert_not_awaited()


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
    service = RagService(settings(), embedding, retriever, generator)

    with pytest.raises(HTTPException) as error:
        await service.answer("Question", "HR")

    assert error.value.status_code == 503
    assert error.value.detail["code"] == expected_code


def test_context_builder_preserves_boundaries_and_respects_limit() -> None:
    first = chunk("First authorized source")
    second = chunk("Second source that should not fit")
    first_context, _ = build_context([first], 10000)

    context, included = build_context([first, second], len(first_context))

    assert context == first_context
    assert included == [first]
