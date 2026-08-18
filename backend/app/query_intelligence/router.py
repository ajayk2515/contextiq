from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser
from app.database import get_session
from app.query_intelligence.domain import (
    ExecutedRetrievalStrategy,
    QueryCategory,
    RetrievalProfile,
)
from app.query_intelligence.errors import raise_query_not_found
from app.query_intelligence.models import QueryLog, RetrievalLog
from app.query_intelligence.schemas import QueryDetail, QuerySummary, RetrievalSnapshot

router = APIRouter(prefix="/api/queries", tags=["query-inspector"])
RECENT_QUERY_LIMIT = 50


async def get_owned_query(session: AsyncSession, query_id: UUID, user_id: UUID) -> QueryLog:
    result = await session.execute(
        select(QueryLog).where(QueryLog.id == query_id, QueryLog.user_id == user_id)
    )
    query = result.scalar_one_or_none()
    if query is None:
        raise_query_not_found()
    return query


@router.get("", response_model=list[QuerySummary])
async def list_queries(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[QueryLog]:
    result = await session.execute(
        select(QueryLog)
        .where(QueryLog.user_id == current_user.id)
        .order_by(QueryLog.created_at.desc(), QueryLog.id.desc())
        .limit(RECENT_QUERY_LIMIT)
    )
    return list(result.scalars().all())


@router.get("/{query_id}", response_model=QueryDetail)
async def get_query(
    query_id: UUID,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> QueryDetail:
    query = await get_owned_query(session, query_id, current_user.id)
    counts = await session.execute(
        select(
            func.count(RetrievalLog.id),
            func.count(RetrievalLog.id).filter(RetrievalLog.included_in_context.is_(True)),
        ).where(RetrievalLog.query_id == query.id)
    )
    candidate_count, final_context_count = counts.one()
    return QueryDetail(
        id=query.id,
        query_text=query.query_text,
        query_category=QueryCategory(query.query_category),
        retrieval_profile=RetrievalProfile(query.retrieval_profile),
        retrieval_strategy=ExecutedRetrievalStrategy(query.retrieval_strategy),
        retrieval_latency_ms=query.retrieval_latency_ms,
        classifier_fallback=query.classifier_fallback,
        created_at=query.created_at,
        candidate_count=candidate_count,
        final_context_count=final_context_count,
        reranked=query.retrieval_strategy == ExecutedRetrievalStrategy.HYBRID_RRF_RERANK,
    )


@router.get("/{query_id}/retrieval", response_model=list[RetrievalSnapshot])
async def get_query_retrieval(
    query_id: UUID,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[RetrievalLog]:
    query = await get_owned_query(session, query_id, current_user.id)
    result = await session.execute(
        select(RetrievalLog)
        .where(RetrievalLog.query_id == query.id)
        .order_by(
            RetrievalLog.rank_before.asc().nulls_last(),
            RetrievalLog.created_at,
            RetrievalLog.id,
        )
    )
    return list(result.scalars().all())
