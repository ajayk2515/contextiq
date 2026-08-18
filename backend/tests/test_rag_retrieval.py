from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from qdrant_client import models

from app.config import Settings
from app.ingestion.embeddings import SparseEmbedding
from app.rag.retrieval import QdrantRetriever


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
    retriever = QdrantRetriever(settings(), client)

    chunks = await retriever.search_dense([0.1, 0.2], "HR", 3)

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
    assert chunks[0].allowed_roles == ("HR",)


async def test_hybrid_retrieval_uses_filtered_named_vectors_and_native_rrf() -> None:
    document_id = uuid4()
    chunk_id = uuid4()
    client = AsyncMock()
    client.collection_exists.return_value = True
    client.query_points.return_value = SimpleNamespace(
        points=[
            SimpleNamespace(
                score=0.75,
                payload={
                    "document_id": str(document_id),
                    "chunk_id": str(chunk_id),
                    "filename": "policy.md",
                    "page": None,
                    "section": "Policy HR-RET-204",
                    "text": "Policy HR-RET-204 provides twelve weeks of leave.",
                    "allowed_roles": ["HR"],
                },
            )
        ]
    )
    retriever = QdrantRetriever(settings(), client)
    sparse = SparseEmbedding(indices=[17, 204], values=[0.8, 1.0])

    chunks = await retriever.search_hybrid([0.1, 0.2], sparse, "HR", 8)

    call = client.query_points.await_args.kwargs
    dense_prefetch, sparse_prefetch = call["prefetch"]
    assert dense_prefetch.using == "dense"
    assert dense_prefetch.query == [0.1, 0.2]
    assert dense_prefetch.limit == 8
    assert dense_prefetch.score_threshold == 0.35
    assert dense_prefetch.filter.must[0].match.value == "HR"
    assert sparse_prefetch.using == "sparse"
    assert sparse_prefetch.query == models.SparseVector(indices=[17, 204], values=[0.8, 1.0])
    assert sparse_prefetch.limit == 8
    assert sparse_prefetch.score_threshold is None
    assert sparse_prefetch.filter.must[0].match.value == "HR"
    assert call["query"] == models.FusionQuery(fusion=models.Fusion.RRF)
    assert call["query_filter"].must[0].match.value == "HR"
    assert call["limit"] == 8
    assert len(chunks) == 1
    assert chunks[0].chunk_id == chunk_id
    assert chunks[0].allowed_roles == ("HR",)


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
    retriever = QdrantRetriever(settings(), client)

    assert await retriever.search_dense([0.1, 0.2], "HR", 3) == []


async def test_dense_retrieval_returns_empty_when_collection_does_not_exist() -> None:
    client = AsyncMock()
    client.collection_exists.return_value = False
    retriever = QdrantRetriever(settings(), client)

    assert await retriever.search_dense([0.1, 0.2], "Developer", 3) == []
    assert (
        await retriever.search_hybrid(
            [0.1, 0.2], SparseEmbedding(indices=[1], values=[1.0]), "Developer", 8
        )
        == []
    )
    client.query_points.assert_not_awaited()


def test_role_filter_rejects_unsupported_server_role() -> None:
    with pytest.raises(ValueError):
        QdrantRetriever.role_filter("Admin")
