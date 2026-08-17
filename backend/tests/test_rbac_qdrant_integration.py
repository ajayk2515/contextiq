from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

from qdrant_client import AsyncQdrantClient, models

from app.config import Settings
from app.ingestion.embeddings import SparseEmbedding
from app.ingestion.parser import ParsedChunk
from app.ingestion.vector_index import DocumentVectorIndex, IndexedChunk
from app.rag.retrieval import DenseRetriever
from app.rag.service import RagService


def settings(collection: str) -> Settings:
    return Settings(
        jwt_secret="unit-test-jwt-secret-with-at-least-thirty-two-characters",
        openai_api_key=None,
        openai_embedding_dimensions=2,
        qdrant_documents_collection=collection,
        rag_top_k=10,
        rag_score_threshold=-1,
    )


def point(
    point_id: UUID,
    filename: str,
    allowed_roles: object,
    vector: list[float] | None = None,
    text: str | None = None,
) -> models.PointStruct:
    document_id = uuid4()
    payload = {
        "document_id": str(document_id),
        "chunk_id": str(point_id),
        "filename": filename,
        "page": None,
        "section": "Security Test",
        "text": text or filename,
        "allowed_roles": allowed_roles,
    }
    return models.PointStruct(
        id=str(point_id),
        vector={"dense": vector or [1.0, 0.0]},
        payload=payload,
    )


async def create_collection(client: AsyncQdrantClient, collection: str) -> None:
    await client.create_collection(
        collection_name=collection,
        vectors_config={
            "dense": models.VectorParams(size=2, distance=models.Distance.COSINE),
        },
        sparse_vectors_config={"sparse": models.SparseVectorParams()},
    )


async def test_qdrant_role_filter_enforces_single_multi_and_cross_role_access() -> None:
    collection = "rbac_role_matrix"
    client = AsyncQdrantClient(location=":memory:")
    try:
        await create_collection(client, collection)
        await client.upsert(
            collection_name=collection,
            points=[
                point(uuid4(), "hr.md", ["HR"]),
                point(uuid4(), "finance.md", ["Finance"]),
                point(uuid4(), "developer.md", ["Developer"]),
                point(uuid4(), "executive.md", ["Executive"]),
                point(uuid4(), "shared.md", ["HR", "Executive"]),
            ],
            wait=True,
        )
        retriever = DenseRetriever(settings(collection), client)
        expected = {
            "HR": {"hr.md", "shared.md"},
            "Finance": {"finance.md"},
            "Developer": {"developer.md"},
            "Executive": {"executive.md", "shared.md"},
        }

        for role, filenames in expected.items():
            chunks = await retriever.search([1.0, 0.0], role)
            assert {chunk.filename for chunk in chunks} == filenames
    finally:
        await client.close()


async def test_same_topic_restricted_chunk_cannot_enter_context_or_citations() -> None:
    collection = "rbac_same_topic"
    client = AsyncQdrantClient(location=":memory:")
    developer_id = uuid4()
    hr_id = uuid4()
    try:
        await create_collection(client, collection)
        await client.upsert(
            collection_name=collection,
            points=[
                point(
                    developer_id,
                    "developer-retention.md",
                    ["Developer"],
                    vector=[0.8, 0.2],
                    text="The standard retention bonus is 5%.",
                ),
                point(
                    hr_id,
                    "hr-retention.md",
                    ["HR"],
                    vector=[1.0, 0.0],
                    text="The confidential HR retention bonus is 17%.",
                ),
            ],
            wait=True,
        )
        configured = settings(collection)
        retriever = DenseRetriever(configured, client)

        developer_chunks = await retriever.search([1.0, 0.0], "Developer")
        hr_chunks = await retriever.search([1.0, 0.0], "HR")

        assert [chunk.chunk_id for chunk in developer_chunks] == [developer_id]
        assert [chunk.chunk_id for chunk in hr_chunks] == [hr_id]

        embedding = SimpleNamespace(dense=AsyncMock(return_value=[[1.0, 0.0]]))
        generator = SimpleNamespace(
            generate=AsyncMock(return_value="The standard retention bonus is 5%.")
        )
        service = RagService(configured, embedding, retriever, generator)
        response = await service.answer("What is the retention bonus?", "Developer")
        context = generator.generate.await_args.args[1]

        assert "5%" in context
        assert "17%" not in context
        assert [source.chunk_id for source in response.sources] == [developer_id]
        assert all(source.filename != "hr-retention.md" for source in response.sources)
        assert "17%" not in response.answer
    finally:
        await client.close()


async def test_missing_empty_and_malformed_role_metadata_fail_closed() -> None:
    collection = "rbac_malformed"
    client = AsyncQdrantClient(location=":memory:")
    try:
        await create_collection(client, collection)
        valid = point(uuid4(), "valid.md", ["HR"])
        missing = point(uuid4(), "missing.md", ["HR"])
        assert missing.payload is not None
        missing.payload.pop("allowed_roles")
        await client.upsert(
            collection_name=collection,
            points=[
                valid,
                missing,
                point(uuid4(), "empty.md", []),
                point(uuid4(), "scalar.md", "HR"),
                point(uuid4(), "mixed.md", ["HR", 7]),
                point(uuid4(), "unknown.md", ["Admin"]),
            ],
            wait=True,
        )

        retriever = DenseRetriever(settings(collection), client)
        raw_response = await client.query_points(
            collection_name=collection,
            query=[1.0, 0.0],
            using="dense",
            query_filter=retriever.role_filter("HR"),
            limit=10,
            with_payload=True,
        )
        chunks = await retriever.search([1.0, 0.0], "HR")

        assert {(point.payload or {}).get("filename") for point in raw_response.points} == {
            "valid.md",
            "mixed.md",
        }
        assert [chunk.filename for chunk in chunks] == ["valid.md"]
    finally:
        await client.close()


async def test_deleted_document_vectors_are_not_retrievable() -> None:
    collection = "rbac_deletion"
    client = AsyncQdrantClient(location=":memory:")
    configured = settings(collection)
    document_id = uuid4()
    chunks = [
        IndexedChunk(
            id=uuid4(),
            parsed=ParsedChunk(
                text=f"Restricted chunk {index}",
                section="Deletion",
                page=None,
                chunk_hash=str(index) * 64,
            ),
        )
        for index in (1, 2)
    ]
    index = DocumentVectorIndex(configured, client)
    retriever = DenseRetriever(configured, client)
    try:
        await create_collection(client, collection)
        await index.replace_document(
            document_id=document_id,
            filename="delete-me.md",
            allowed_roles=["HR", "Executive"],
            chunks=chunks,
            dense_vectors=[[1.0, 0.0], [0.9, 0.1]],
            sparse_vectors=[
                SparseEmbedding(indices=[1], values=[1.0]),
                SparseEmbedding(indices=[2], values=[1.0]),
            ],
        )

        assert len(await retriever.search([1.0, 0.0], "HR")) == 2
        assert len(await retriever.search([1.0, 0.0], "Executive")) == 2

        await index.delete_document(document_id)

        assert await retriever.search([1.0, 0.0], "HR") == []
        assert await retriever.search([1.0, 0.0], "Executive") == []
    finally:
        await client.close()
