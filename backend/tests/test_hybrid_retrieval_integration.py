from uuid import UUID, uuid4

from qdrant_client import AsyncQdrantClient, models

from app.config import Settings
from app.ingestion.embeddings import SparseEmbedding
from app.rag.retrieval import QdrantRetriever


def settings(collection: str) -> Settings:
    return Settings(
        jwt_secret="unit-test-jwt-secret-with-at-least-thirty-two-characters",
        openai_api_key=None,
        openai_embedding_dimensions=2,
        qdrant_documents_collection=collection,
        rag_score_threshold=0.1,
    )


def point(
    chunk_id: UUID,
    filename: str,
    dense: list[float],
    sparse_index: int,
    sparse_value: float,
) -> models.PointStruct:
    return models.PointStruct(
        id=str(chunk_id),
        vector={
            "dense": dense,
            "sparse": models.SparseVector(
                indices=[sparse_index],
                values=[sparse_value],
            ),
        },
        payload={
            "document_id": str(uuid4()),
            "chunk_id": str(chunk_id),
            "filename": filename,
            "page": None,
            "section": "Hybrid Verification",
            "text": filename,
            "allowed_roles": ["Developer"],
        },
    )


async def test_native_rrf_combines_dense_sparse_and_overlap_rankings() -> None:
    collection = "hybrid_rrf_controlled"
    client = AsyncQdrantClient(location=":memory:")
    dense_id = uuid4()
    overlap_id = uuid4()
    sparse_id = uuid4()
    try:
        await client.create_collection(
            collection_name=collection,
            vectors_config={"dense": models.VectorParams(size=2, distance=models.Distance.COSINE)},
            sparse_vectors_config={"sparse": models.SparseVectorParams()},
        )
        await client.upsert(
            collection_name=collection,
            points=[
                point(dense_id, "dense-only.md", [1.0, 0.0], 99, 1.0),
                point(overlap_id, "overlap.md", [0.8, 0.2], 42, 0.8),
                point(sparse_id, "sparse-only-HR-RET-204.md", [0.0, 1.0], 42, 1.0),
            ],
            wait=True,
        )
        retriever = QdrantRetriever(settings(collection), client)

        chunks = await retriever.search_hybrid(
            [1.0, 0.0],
            SparseEmbedding(indices=[42], values=[1.0]),
            "Developer",
            3,
        )

        assert chunks[0].chunk_id == overlap_id
        assert {chunk.chunk_id for chunk in chunks} == {dense_id, overlap_id, sparse_id}
        assert {chunk.filename for chunk in chunks} == {
            "dense-only.md",
            "overlap.md",
            "sparse-only-HR-RET-204.md",
        }
    finally:
        await client.close()
