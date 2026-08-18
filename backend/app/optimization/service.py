import logging
from collections import defaultdict
from dataclasses import dataclass
from statistics import fmean
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionFactory
from app.evaluations.models import Evaluation, EvaluationRun, EvaluationRunStatus
from app.optimization.models import OptimizationRecommendation, OptimizationStatus
from app.optimization.rules import OptimizationObservation, evaluate_rules
from app.query_intelligence.domain import ExecutedRetrievalStrategy, RetrievalProfile
from app.query_intelligence.models import QueryLog

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EvaluationSample:
    profile: RetrievalProfile
    strategy: ExecutedRetrievalStrategy
    context_recall: float | None
    context_precision: float | None
    retrieval_latency_ms: int


def aggregate_observations(samples: list[EvaluationSample]) -> list[OptimizationObservation]:
    buckets: dict[tuple[RetrievalProfile, ExecutedRetrievalStrategy], list[EvaluationSample]] = (
        defaultdict(list)
    )
    for sample in samples:
        buckets[(sample.profile, sample.strategy)].append(sample)

    observations: list[OptimizationObservation] = []
    for (profile, strategy), profile_samples in sorted(
        buckets.items(), key=lambda item: (item[0][0].value, item[0][1].value)
    ):
        recall_values = [
            sample.context_recall for sample in profile_samples if sample.context_recall is not None
        ]
        precision_values = [
            sample.context_precision
            for sample in profile_samples
            if sample.context_precision is not None
        ]
        observations.append(
            OptimizationObservation(
                profile=profile,
                strategy=strategy,
                context_recall=fmean(recall_values) if recall_values else None,
                context_precision=fmean(precision_values) if precision_values else None,
                retrieval_latency_ms=fmean(
                    sample.retrieval_latency_ms for sample in profile_samples
                ),
            )
        )
    return observations


class OptimizationService:
    async def generate(
        self, session: AsyncSession, run_id: UUID
    ) -> list[OptimizationRecommendation]:
        run = await session.get(EvaluationRun, run_id)
        if run is None:
            raise ValueError("Evaluation run not found.")
        if run.status != EvaluationRunStatus.COMPLETED:
            logger.info("Skipped optimization for non-completed evaluation run %s", run_id)
            return []

        result = await session.execute(
            select(Evaluation, QueryLog)
            .join(QueryLog, QueryLog.id == Evaluation.query_id)
            .where(Evaluation.run_id == run_id)
        )
        samples = [
            EvaluationSample(
                profile=RetrievalProfile(query.retrieval_profile),
                strategy=ExecutedRetrievalStrategy(query.retrieval_strategy),
                context_recall=evaluation.context_recall,
                context_precision=evaluation.context_precision,
                retrieval_latency_ms=query.retrieval_latency_ms,
            )
            for evaluation, query in result.all()
        ]
        drafts = [
            draft
            for observation in aggregate_observations(samples)
            for draft in evaluate_rules(observation)
        ]

        await session.execute(
            delete(OptimizationRecommendation).where(
                OptimizationRecommendation.evaluation_run_id == run_id
            )
        )
        recommendations = [
            OptimizationRecommendation(
                evaluation_run_id=run_id,
                metric=draft.metric,
                current_value=draft.current_value,
                threshold=draft.threshold,
                recommendation=draft.recommendation,
                status=OptimizationStatus.OPEN,
                profile=draft.profile,
                strategy=draft.strategy,
            )
            for draft in drafts
        ]
        session.add_all(recommendations)
        await session.commit()
        logger.info(
            "Generated %d optimization recommendations for evaluation run %s",
            len(recommendations),
            run_id,
        )
        return recommendations


async def generate_recommendations(run_id: UUID) -> list[OptimizationRecommendation]:
    async with AsyncSessionFactory() as session:
        return await OptimizationService().generate(session, run_id)
