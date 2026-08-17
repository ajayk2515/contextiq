from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.config import Settings
from app.rag.retrieval import DenseRetriever


def settings() -> Settings:
    return Settings(
        jwt_secret="unit-test-jwt-secret-with-at-least-thirty-two-characters",
        openai_api_key=None,
        openai_embedding_dimensions=2,
        rag_score_threshold=0.35,
    )


async def test_dense_retrieval_applies_role_filter_inside_qdrant_query() -> None:
    document_id = uuid4()
    chunk_id = uuid4()
    client = AsyncMock()
    client.collection_exists.return_value = True
    client.query_points.return_value = SimpleNamespace(
        points=[
            SimpleNamespace(
                score=0.82,
                payload={
                    "document_id": str(document_id),
                    "chunk_id": str(chunk_id),
                    "filename": "handbook.md",
                    "page": None,
                    "section": "Leave",
                    "text": "Employees receive twenty days of annual leave.",
                    "allowed_roles": ["HR"],
                },
            )
        ]
    )
    retriever = DenseRetriever(settings(), client)

    chunks = await retriever.search([0.1, 0.2], "HR", 3)

    call = client.query_points.await_args.kwargs
    condition = call["query_filter"].must[0]
    assert call["using"] == "dense"
    assert call["query"] == [0.1, 0.2]
    assert call["limit"] == 3
    assert call["score_threshold"] == 0.35
    assert condition.key == "allowed_roles[]"
    assert condition.match.value == "HR"
    assert len(chunks) == 1
    assert chunks[0].document_id == document_id
    assert chunks[0].chunk_id == chunk_id


async def test_dense_retrieval_fails_closed_for_malformed_permission_payloads() -> None:
    base_payload = {
        "document_id": str(uuid4()),
        "chunk_id": str(uuid4()),
        "filename": "restricted.md",
        "page": None,
        "section": None,
        "text": "Restricted content",
    }
    client = AsyncMock()
    client.collection_exists.return_value = True
    client.query_points.return_value = SimpleNamespace(
        points=[
            SimpleNamespace(score=0.9, payload=base_payload),
            SimpleNamespace(score=0.9, payload={**base_payload, "allowed_roles": []}),
            SimpleNamespace(score=0.9, payload={**base_payload, "allowed_roles": "HR"}),
            SimpleNamespace(score=0.9, payload={**base_payload, "allowed_roles": ["HR", 7]}),
            SimpleNamespace(score=0.9, payload={**base_payload, "allowed_roles": ["Admin"]}),
        ]
    )
    retriever = DenseRetriever(settings(), client)

    assert await retriever.search([0.1, 0.2], "HR", 3) == []


async def test_dense_retrieval_returns_empty_when_collection_does_not_exist() -> None:
    client = AsyncMock()
    client.collection_exists.return_value = False
    retriever = DenseRetriever(settings(), client)

    assert await retriever.search([0.1, 0.2], "Developer", 3) == []
    client.query_points.assert_not_awaited()


def test_role_filter_rejects_unsupported_server_role() -> None:
    with pytest.raises(ValueError):
        DenseRetriever.role_filter("Admin")
