from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.optimization.schemas import OptimizationRecommendationResponse
from app.query_intelligence.domain import ExecutedRetrievalStrategy


class AnalyticsMetrics(BaseModel):
    total_queries: int
    avg_retrieval_latency_ms: float | None
    faithfulness: float | None
    answer_relevancy: float | None
    context_precision: float | None
    context_recall: float | None


class StrategyDistributionItem(BaseModel):
    strategy: ExecutedRetrievalStrategy
    count: int


class LatencyPoint(BaseModel):
    query_id: UUID
    timestamp: datetime
    retrieval_latency_ms: int


class EvaluationHistoryItem(BaseModel):
    run_id: UUID
    completed_at: datetime
    faithfulness: float | None
    answer_relevancy: float | None
    context_precision: float | None
    context_recall: float | None


class AnalyticsSummaryResponse(BaseModel):
    summary: AnalyticsMetrics
    strategy_distribution: list[StrategyDistributionItem]
    latency_series: list[LatencyPoint]
    evaluation_history: list[EvaluationHistoryItem]
    recommendations: list[OptimizationRecommendationResponse]
