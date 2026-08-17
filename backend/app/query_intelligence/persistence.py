from uuid import UUID

from app.database import AsyncSessionFactory
from app.query_intelligence.domain import QueryDecision
from app.query_intelligence.models import QueryLog
from app.query_intelligence.profiles import RetrievalProfileConfig


class QueryLogWriter:
    async def record(
        self,
        user_id: UUID,
        query_text: str,
        decision: QueryDecision,
        profile: RetrievalProfileConfig,
        retrieval_latency_ms: int,
    ) -> UUID:
        async with AsyncSessionFactory() as session:
            query_log = QueryLog(
                user_id=user_id,
                query_text=query_text,
                query_category=decision.category.value,
                retrieval_profile=decision.profile.value,
                retrieval_strategy=profile.executed_strategy.value,
                classifier_fallback=decision.used_fallback,
                retrieval_latency_ms=retrieval_latency_ms,
            )
            session.add(query_log)
            await session.commit()
            await session.refresh(query_log)
            return query_log.id
