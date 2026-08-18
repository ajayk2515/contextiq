from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.schemas import (
    AnalyticsMetrics,
    AnalyticsSummaryResponse,
    EvaluationHistoryItem,
    LatencyPoint,
    StrategyDistributionItem,
)
from app.evaluations.models import Evaluation, EvaluationRun, EvaluationRunStatus
from app.optimization.models import OptimizationRecommendation, OptimizationStatus
from app.optimization.schemas import OptimizationRecommendationResponse
from app.query_intelligence.models import QueryLog

LATENCY_POINT_LIMIT = 100
EVALUATION_RUN_LIMIT = 20
RECOMMENDATION_LIMIT = 20


async def build_analytics_summary(session: AsyncSession) -> AnalyticsSummaryResponse:
    query_totals = (
        await session.execute(
            select(
                func.count(QueryLog.id).label("total_queries"),
                func.avg(QueryLog.retrieval_latency_ms).label("avg_retrieval_latency_ms"),
            )
        )
    ).one()

    strategy_rows = (
        await session.execute(
            select(
                QueryLog.retrieval_strategy.label("strategy"),
                func.count(QueryLog.id).label("query_count"),
            )
            .group_by(QueryLog.retrieval_strategy)
            .order_by(QueryLog.retrieval_strategy)
        )
    ).all()

    recent_latency_rows = (
        await session.execute(
            select(
                QueryLog.id.label("query_id"),
                QueryLog.created_at.label("timestamp"),
                QueryLog.retrieval_latency_ms,
            )
            .order_by(QueryLog.created_at.desc())
            .limit(LATENCY_POINT_LIMIT)
        )
    ).all()

    evaluation_rows = (
        await session.execute(
            select(
                EvaluationRun.id.label("run_id"),
                EvaluationRun.completed_at,
                func.avg(Evaluation.faithfulness).label("faithfulness"),
                func.avg(Evaluation.answer_relevancy).label("answer_relevancy"),
                func.avg(Evaluation.context_precision).label("context_precision"),
                func.avg(Evaluation.context_recall).label("context_recall"),
            )
            .outerjoin(Evaluation, Evaluation.run_id == EvaluationRun.id)
            .where(
                EvaluationRun.status == EvaluationRunStatus.COMPLETED,
                EvaluationRun.completed_at.is_not(None),
            )
            .group_by(EvaluationRun.id, EvaluationRun.completed_at)
            .order_by(EvaluationRun.completed_at.desc())
            .limit(EVALUATION_RUN_LIMIT)
        )
    ).all()

    recommendation_result = await session.execute(
        select(OptimizationRecommendation)
        .where(OptimizationRecommendation.status == OptimizationStatus.OPEN)
        .order_by(OptimizationRecommendation.created_at.desc())
        .limit(RECOMMENDATION_LIMIT)
    )
    recommendations = list(recommendation_result.scalars().all())

    latest_evaluation = evaluation_rows[0] if evaluation_rows else None
    return AnalyticsSummaryResponse(
        summary=AnalyticsMetrics(
            total_queries=int(query_totals.total_queries or 0),
            avg_retrieval_latency_ms=(
                float(query_totals.avg_retrieval_latency_ms)
                if query_totals.avg_retrieval_latency_ms is not None
                else None
            ),
            faithfulness=(
                float(latest_evaluation.faithfulness)
                if latest_evaluation is not None and latest_evaluation.faithfulness is not None
                else None
            ),
            answer_relevancy=(
                float(latest_evaluation.answer_relevancy)
                if latest_evaluation is not None and latest_evaluation.answer_relevancy is not None
                else None
            ),
            context_precision=(
                float(latest_evaluation.context_precision)
                if latest_evaluation is not None and latest_evaluation.context_precision is not None
                else None
            ),
            context_recall=(
                float(latest_evaluation.context_recall)
                if latest_evaluation is not None and latest_evaluation.context_recall is not None
                else None
            ),
        ),
        strategy_distribution=[
            StrategyDistributionItem(strategy=row.strategy, count=int(row.query_count))
            for row in strategy_rows
        ],
        latency_series=[
            LatencyPoint(
                query_id=row.query_id,
                timestamp=row.timestamp,
                retrieval_latency_ms=row.retrieval_latency_ms,
            )
            for row in reversed(recent_latency_rows)
        ],
        evaluation_history=[
            EvaluationHistoryItem(
                run_id=row.run_id,
                completed_at=row.completed_at,
                faithfulness=float(row.faithfulness) if row.faithfulness is not None else None,
                answer_relevancy=(
                    float(row.answer_relevancy) if row.answer_relevancy is not None else None
                ),
                context_precision=(
                    float(row.context_precision) if row.context_precision is not None else None
                ),
                context_recall=(
                    float(row.context_recall) if row.context_recall is not None else None
                ),
            )
            for row in reversed(evaluation_rows)
        ],
        recommendations=[
            OptimizationRecommendationResponse.model_validate(item, from_attributes=True)
            for item in recommendations
        ],
    )
