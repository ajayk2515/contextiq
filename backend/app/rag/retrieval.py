from dataclasses import dataclass
from typing import Any
from uuid import UUID

from qdrant_client import AsyncQdrantClient, models

from app.auth.models import UserRole
from app.config import Settings
from app.ingestion.embeddings import SparseEmbedding
from app.vector_store import create_qdrant_client

SUPPORTED_ROLES = frozenset(role.value for role in UserRole)


@dataclass(frozen=True)
class RetrievedChunk:
    document_id: UUID
    chunk_id: UUID
    filename: str
    page: int | None
    section: str | None
    text: str
    allowed_roles: tuple[str, ...]
    score: float
    rank_before: int | None = None
    rrf_score: float | None = None
    reranker_score: float | None = None
    rank_after: int | None = None


class QdrantRetriever:
    def __init__(self, settings: Settings, client: AsyncQdrantClient | None = None) -> None:
        self.settings = settings
        self.client = client or create_qdrant_client()
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self.client.close()

    @staticmethod
    def role_filter(role: str) -> models.Filter:
        validated_role = UserRole(role)
        return models.Filter(
            must=[
                models.FieldCondition(
                    key="allowed_roles[]",
                    match=models.MatchValue(value=validated_role.value),
                )
            ]
        )

    async def search_dense(
        self, query_vector: list[float], role: str, top_k: int
    ) -> list[RetrievedChunk]:
        collection = self.settings.qdrant_documents_collection
        if not await self.client.collection_exists(collection):
            return []

        response = await self.client.query_points(
            collection_name=collection,
            query=query_vector,
            using="dense",
            query_filter=self.role_filter(role),
            limit=top_k,
            score_threshold=self.settings.rag_score_threshold,
            with_payload=True,
            with_vectors=False,
        )
        return [
            chunk
            for rank, point in enumerate(response.points, start=1)
            if (
                chunk := self._to_retrieved_chunk(
                    point.payload,
                    point.score,
                    role,
                    rank_before=rank,
                )
            )
            is not None
        ]

    async def search_hybrid(
        self,
        dense_vector: list[float],
        sparse_vector: SparseEmbedding,
        role: str,
        top_k: int,
    ) -> list[RetrievedChunk]:
        collection = self.settings.qdrant_documents_collection
        if not await self.client.collection_exists(collection):
            return []

        role_filter = self.role_filter(role)
        response = await self.client.query_points(
            collection_name=collection,
            prefetch=[
                models.Prefetch(
                    query=dense_vector,
                    using="dense",
                    filter=role_filter,
                    limit=top_k,
                    score_threshold=self.settings.rag_score_threshold,
                ),
                models.Prefetch(
                    query=models.SparseVector(
                        indices=sparse_vector.indices,
                        values=sparse_vector.values,
                    ),
                    using="sparse",
                    filter=role_filter,
                    limit=top_k,
                ),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            query_filter=role_filter,
            limit=top_k,
            with_payload=True,
            with_vectors=False,
        )
        return [
            chunk
            for rank, point in enumerate(response.points, start=1)
            if (
                chunk := self._to_retrieved_chunk(
                    point.payload,
                    point.score,
                    role,
                    rank_before=rank,
                    rrf_score=float(point.score),
                )
            )
            is not None
        ]

    @staticmethod
    def _to_retrieved_chunk(
        payload: dict[str, Any] | None,
        score: float,
        role: str,
        rank_before: int | None = None,
        rrf_score: float | None = None,
    ) -> RetrievedChunk | None:
        if payload is None:
            return None
        allowed_roles = payload.get("allowed_roles")
        if (
            not isinstance(allowed_roles, list)
            or not allowed_roles
            or any(type(item) is not str or item not in SUPPORTED_ROLES for item in allowed_roles)
            or role not in allowed_roles
        ):
            return None
        try:
            return RetrievedChunk(
                document_id=UUID(str(payload["document_id"])),
                chunk_id=UUID(str(payload["chunk_id"])),
                filename=str(payload["filename"]),
                page=int(payload["page"]) if payload.get("page") is not None else None,
                section=str(payload["section"]) if payload.get("section") is not None else None,
                text=str(payload["text"]),
                allowed_roles=tuple(allowed_roles),
                score=float(score),
                rank_before=rank_before,
                rrf_score=rrf_score,
            )
        except (KeyError, TypeError, ValueError):
            return None
