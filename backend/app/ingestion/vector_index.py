from dataclasses import dataclass
from uuid import UUID

from qdrant_client import AsyncQdrantClient, models

from app.config import Settings
from app.ingestion.embeddings import SparseEmbedding
from app.ingestion.parser import ParsedChunk
from app.vector_store import create_qdrant_client


@dataclass(frozen=True)
class IndexedChunk:
    id: UUID
    parsed: ParsedChunk


class DocumentVectorIndex:
    def __init__(self, settings: Settings, client: AsyncQdrantClient | None = None) -> None:
        self.settings = settings
        self.client = client or create_qdrant_client()
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self.client.close()

    async def ensure_collection(self) -> None:
        name = self.settings.qdrant_documents_collection
        if not await self.client.collection_exists(name):
            await self.client.create_collection(
                collection_name=name,
                vectors_config={
                    "dense": models.VectorParams(
                        size=self.settings.openai_embedding_dimensions,
                        distance=models.Distance.COSINE,
                    )
                },
                sparse_vectors_config={
                    "sparse": models.SparseVectorParams(
                        index=models.SparseIndexParams(on_disk=False)
                    )
                },
            )
        await self.client.create_payload_index(
            name, "document_id", field_schema=models.PayloadSchemaType.KEYWORD
        )
        await self.client.create_payload_index(
            name, "allowed_roles[]", field_schema=models.PayloadSchemaType.KEYWORD
        )

    def document_filter(self, document_id: UUID) -> models.Filter:
        return models.Filter(
            must=[
                models.FieldCondition(
                    key="document_id",
                    match=models.MatchValue(value=str(document_id)),
                )
            ]
        )

    async def delete_document(self, document_id: UUID) -> None:
        name = self.settings.qdrant_documents_collection
        if not await self.client.collection_exists(name):
            return
        await self.client.delete(
            collection_name=name,
            points_selector=self.document_filter(document_id),
            wait=True,
        )

    async def replace_document(
        self,
        document_id: UUID,
        filename: str,
        allowed_roles: list[str],
        chunks: list[IndexedChunk],
        dense_vectors: list[list[float]],
        sparse_vectors: list[SparseEmbedding],
    ) -> None:
        if not (len(chunks) == len(dense_vectors) == len(sparse_vectors)):
            raise ValueError("Chunk and embedding counts do not match.")
        await self.ensure_collection()
        await self.delete_document(document_id)
        points = []
        for index, (chunk, dense, sparse) in enumerate(
            zip(chunks, dense_vectors, sparse_vectors, strict=True)
        ):
            points.append(
                models.PointStruct(
                    id=str(chunk.id),
                    vector={
                        "dense": dense,
                        "sparse": models.SparseVector(
                            indices=sparse.indices,
                            values=sparse.values,
                        ),
                    },
                    payload={
                        "document_id": str(document_id),
                        "chunk_id": str(chunk.id),
                        "filename": filename,
                        "page": chunk.parsed.page,
                        "section": chunk.parsed.section,
                        "chunk_index": index,
                        "text": chunk.parsed.text,
                        "chunk_hash": chunk.parsed.chunk_hash,
                        "allowed_roles": allowed_roles,
                    },
                )
            )
        for start in range(0, len(points), 100):
            await self.client.upsert(
                collection_name=self.settings.qdrant_documents_collection,
                points=points[start : start + 100],
                wait=True,
            )
