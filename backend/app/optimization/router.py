from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser
from app.database import get_session
from app.optimization.models import OptimizationRecommendation, OptimizationStatus
from app.optimization.schemas import (
    DismissRecommendationRequest,
    OptimizationRecommendationResponse,
)

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


@router.get("", response_model=list[OptimizationRecommendationResponse])
async def list_recommendations(
    _current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    evaluation_run_id: UUID | None = None,
    recommendation_status: Annotated[OptimizationStatus, Query(alias="status")] = (
        OptimizationStatus.OPEN
    ),
) -> list[OptimizationRecommendation]:
    statement = select(OptimizationRecommendation).where(
        OptimizationRecommendation.status == recommendation_status
    )
    if evaluation_run_id is not None:
        statement = statement.where(
            OptimizationRecommendation.evaluation_run_id == evaluation_run_id
        )
    result = await session.execute(statement.order_by(OptimizationRecommendation.created_at.desc()))
    return list(result.scalars().all())


@router.patch("/{recommendation_id}", response_model=OptimizationRecommendationResponse)
async def dismiss_recommendation(
    recommendation_id: UUID,
    _request: DismissRecommendationRequest,
    _current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OptimizationRecommendation:
    recommendation = await session.get(OptimizationRecommendation, recommendation_id)
    if recommendation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RECOMMENDATION_NOT_FOUND",
                "message": "Optimization recommendation not found.",
            },
        )
    recommendation.status = OptimizationStatus.DISMISSED
    await session.commit()
    await session.refresh(recommendation)
    return recommendation
