from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.evaluations.models import Evaluation, EvaluationRun, EvaluationRunStatus
from app.optimization.models import OptimizationMetric, OptimizationStatus
from app.optimization.service import (
    EvaluationSample,
    OptimizationService,
    aggregate_observations,
)
from app.query_intelligence.domain import ExecutedRetrievalStrategy, RetrievalProfile
from app.query_intelligence.models import QueryLog


def completed_run() -> EvaluationRun:
    now = datetime.now(UTC)
    return EvaluationRun(
        id=uuid4(),
        status=EvaluationRunStatus.COMPLETED,
        total_cases=1,
        completed_cases=1,
        started_at=now,
        completed_at=now,
        created_at=now,
    )


def evaluation(run_id, recall: float | None = 0.5, precision: float | None = 0.45):
    return Evaluation(
        id=uuid4(),
        run_id=run_id,
        evaluation_case_id="controlled-case",
        query_id=uuid4(),
        question="Controlled question",
        role="Developer",
        expected_answer="Reference",
        expected_document="policy.md",
        generated_answer="Answer",
        context_recall=recall,
        context_precision=precision,
        created_at=datetime.now(UTC),
    )


def query(query_id, profile: str = "BALANCED", latency: int = 3200) -> QueryLog:
    return QueryLog(
        id=query_id,
        user_id=uuid4(),
        query_text="Controlled question",
        query_category="SPECIFIC_SEARCH",
        retrieval_profile=profile,
        retrieval_strategy=("HYBRID_RRF_RERANK" if profile == "ACCURATE" else "HYBRID_RRF"),
        classifier_fallback=False,
        retrieval_latency_ms=latency,
        created_at=datetime.now(UTC),
    )


def session_for(run: EvaluationRun, rows: list[tuple[Evaluation, QueryLog]]) -> AsyncMock:
    row_result = MagicMock()
    row_result.all.return_value = rows
    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = run
    session.execute.side_effect = [row_result, MagicMock()]
    session.add_all = MagicMock()
    return session


def test_aggregation_groups_profiles_and_ignores_null_quality_metrics() -> None:
    observations = aggregate_observations(
        [
            EvaluationSample(
                RetrievalProfile.FAST,
                ExecutedRetrievalStrategy.DENSE,
                None,
                0.4,
                200,
            ),
            EvaluationSample(
                RetrievalProfile.FAST,
                ExecutedRetrievalStrategy.DENSE,
                0.8,
                0.8,
                400,
            ),
            EvaluationSample(
                RetrievalProfile.ACCURATE,
                ExecutedRetrievalStrategy.HYBRID_RRF_RERANK,
                0.9,
                0.9,
                3000,
            ),
        ]
    )

    assert len(observations) == 2
    accurate, fast = observations
    assert accurate.profile == RetrievalProfile.ACCURATE
    assert accurate.retrieval_latency_ms == 3000
    assert fast.context_recall == 0.8
    assert fast.context_precision == pytest.approx(0.6)
    assert fast.retrieval_latency_ms == 300


async def test_service_persists_multiple_rules_and_transactionally_replaces_existing() -> None:
    run = completed_run()
    item = evaluation(run.id)
    query_log = query(item.query_id)
    session = session_for(run, [(item, query_log)])

    recommendations = await OptimizationService().generate(session, run.id)

    assert {item.metric for item in recommendations} == {
        OptimizationMetric.CONTEXT_RECALL,
        OptimizationMetric.CONTEXT_PRECISION,
        OptimizationMetric.RETRIEVAL_LATENCY_MS,
    }
    assert all(item.status == OptimizationStatus.OPEN for item in recommendations)
    assert all(item.profile == RetrievalProfile.BALANCED for item in recommendations)
    assert "DELETE FROM optimization_recommendations" in str(
        session.execute.await_args_list[1].args[0]
    )
    session.add_all.assert_called_once_with(recommendations)
    session.commit.assert_awaited_once()


async def test_regeneration_replaces_instead_of_appending_duplicates() -> None:
    run = completed_run()
    item = evaluation(run.id, recall=0.5, precision=0.45)
    query_log = query(item.query_id, latency=3200)
    row_result = MagicMock()
    row_result.all.return_value = [(item, query_log)]
    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = run
    session.execute.side_effect = [row_result, MagicMock(), row_result, MagicMock()]
    session.add_all = MagicMock()

    first = await OptimizationService().generate(session, run.id)
    second = await OptimizationService().generate(session, run.id)

    assert len(first) == len(second) == 3
    assert {recommendation.metric for recommendation in first} == {
        recommendation.metric for recommendation in second
    }
    assert len(session.add_all.call_args_list[0].args[0]) == 3
    assert len(session.add_all.call_args_list[1].args[0]) == 3
    assert session.commit.await_count == 2
    delete_statements = [
        call.args[0]
        for call in session.execute.await_args_list
        if "DELETE FROM optimization_recommendations" in str(call.args[0])
    ]
    assert len(delete_statements) == 2


async def test_failed_evaluation_run_is_not_optimized() -> None:
    run = completed_run()
    run.status = EvaluationRunStatus.FAILED
    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = run

    recommendations = await OptimizationService().generate(session, run.id)

    assert recommendations == []
    session.execute.assert_not_awaited()
    session.commit.assert_not_awaited()
