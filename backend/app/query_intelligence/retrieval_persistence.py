import logging
from uuid import UUID

from app.database import AsyncSessionFactory
from app.query_intelligence.domain import ExecutedRetrievalStrategy
from app.query_intelligence.models import RetrievalLog
from app.rag.retrieval import RetrievedChunk

logger = logging.getLogger(__name__)
SNIPPET_MAX_CHARACTERS = 500


def retrieval_snippet(text: str, maximum_characters: int = SNIPPET_MAX_CHARACTERS) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= maximum_characters:
        return normalized
    return normalized[: maximum_characters - 3].rstrip() + "..."


class RetrievalLogWriter:
    async def record(
        self,
        query_id: UUID,
        candidates: list[RetrievedChunk],
        included_chunk_ids: set[UUID],
        strategy: ExecutedRetrievalStrategy,
    ) -> None:
        if not candidates:
            logger.info("No retrieval candidates to snapshot for query %s", query_id)
            return

        retrieval_logs = [
            RetrievalLog(
                query_id=query_id,
                document_id=candidate.document_id,
                chunk_id=candidate.chunk_id,
                filename=candidate.filename,
                page=candidate.page,
                section=candidate.section,
                snippet=retrieval_snippet(candidate.text),
                rank_before=candidate.rank_before,
                rank_after=candidate.rank_after,
                retrieval_score=(
                    candidate.score if strategy == ExecutedRetrievalStrategy.DENSE else None
                ),
                rrf_score=candidate.rrf_score,
                reranker_score=candidate.reranker_score,
                included_in_context=candidate.chunk_id in included_chunk_ids,
            )
            for candidate in candidates
        ]
        async with AsyncSessionFactory() as session:
            session.add_all(retrieval_logs)
            await session.commit()
        logger.info(
            "Persisted %d retrieval snapshots for query %s using %s",
            len(retrieval_logs),
            query_id,
            strategy.value,
        )
