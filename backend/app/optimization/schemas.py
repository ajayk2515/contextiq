from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.optimization.models import OptimizationMetric, OptimizationStatus
from app.query_intelligence.domain import ExecutedRetrievalStrategy, RetrievalProfile


class OptimizationRecommendationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    evaluation_run_id: UUID
    metric: OptimizationMetric
    current_value: float
    threshold: float
    recommendation: str
    status: OptimizationStatus
    profile: RetrievalProfile | None
    strategy: ExecutedRetrievalStrategy | None
    created_at: datetime


class DismissRecommendationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["DISMISSED"]
