from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.schemas import AnalyticsSummaryResponse
from app.analytics.service import build_analytics_summary
from app.auth.dependencies import CurrentUser
from app.database import get_session

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get(
    "/summary",
    response_model=AnalyticsSummaryResponse,
    summary="Get aggregate retrieval and evaluation analytics",
)
async def get_analytics_summary(
    _current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AnalyticsSummaryResponse:
    """Return non-sensitive system aggregates for the analytics dashboard."""
    return await build_analytics_summary(session)
