from unittest.mock import AsyncMock
from uuid import uuid4

from qdrant_client import models

from app.config import Settings
from app.ingestion.embeddings import SparseEmbedding
from app.ingestion.parser import ParsedChunk
from app.ingestion.vector_index import DocumentVectorIndex, IndexedChunk


def settings() -> Settings:
    return Settings(
        jwt_secret="unit-test-jwt-secret-with-at-least-thirty-two-characters",
        openai_embedding_dimensions=2,
    )


async def test_qdrant_points_contain_dense_sparse_and_rbac_payload() -> None:
    client = AsyncMock()
    client.collection_exists.return_value = False
    document_id = uuid4()
    chunk_id = uuid4()
    index = DocumentVectorIndex(settings(), client)

    await index.replace_document(
        document_id=document_id,
        filename="policy.md",
        allowed_roles=["HR", "Executive"],
        chunks=[
            IndexedChunk(
                id=chunk_id,
                parsed=ParsedChunk(
                    text="Annual leave policy",
                    section="Leave",
                    page=2,
                    chunk_hash="a" * 64,
                ),
            )
        ],
        dense_vectors=[[0.1, 0.2]],
        sparse_vectors=[SparseEmbedding(indices=[1, 2], values=[0.4, 0.8])],
    )

    client.create_collection.assert_awaited_once()
    call = client.upsert.await_args.kwargs
    point = call["points"][0]
    assert point.vector["dense"] == [0.1, 0.2]
    assert isinstance(point.vector["sparse"], models.SparseVector)
    assert point.payload == {
        "document_id": str(document_id),
        "chunk_id": str(chunk_id),
        "filename": "policy.md",
        "page": 2,
        "section": "Leave",
        "chunk_index": 0,
        "text": "Annual leave policy",
        "chunk_hash": "a" * 64,
        "allowed_roles": ["HR", "Executive"],
    }


async def test_document_cleanup_uses_document_id_filter() -> None:
    client = AsyncMock()
    client.collection_exists.return_value = True
    document_id = uuid4()
    index = DocumentVectorIndex(settings(), client)

    await index.delete_document(document_id)

    selector = client.delete.await_args.kwargs["points_selector"]
    condition = selector.must[0]
    assert condition.key == "document_id"
    assert condition.match.value == str(document_id)
