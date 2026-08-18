from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.schemas import AnalyticsMetrics, AnalyticsSummaryResponse
from app.analytics.service import build_analytics_summary
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.database import get_session
from app.main import app
from app.optimization.models import (
    OptimizationMetric,
    OptimizationRecommendation,
    OptimizationStatus,
)


def current_user() -> User:
    return User(id=uuid4(), email="hr@demo.com", password_hash="unused", role="HR")


async def request(session: AsyncSession, authenticated: bool = True):
    async def override_user() -> User:
        return current_user()

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    if authenticated:
        app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_session] = override_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.get("/api/analytics/summary")
    finally:
        app.dependency_overrides.clear()


def query_result(*, one: object | None = None, rows: list[object] | None = None) -> MagicMock:
    result = MagicMock()
    if one is not None:
        result.one.return_value = one
    if rows is not None:
        result.all.return_value = rows
    return result


async def test_summary_requires_authentication() -> None:
    response = await request(AsyncMock(spec=AsyncSession), authenticated=False)

    assert response.status_code == 401


async def test_summary_endpoint_returns_aggregate_response() -> None:
    payload = AnalyticsSummaryResponse(
        summary=AnalyticsMetrics(
            total_queries=4,
            avg_retrieval_latency_ms=812.5,
            faithfulness=0.9,
            answer_relevancy=0.8,
            context_precision=0.7,
            context_recall=0.6,
        ),
        strategy_distribution=[],
        latency_series=[],
        evaluation_history=[],
        recommendations=[],
    )
    with patch("app.analytics.router.build_analytics_summary", new=AsyncMock(return_value=payload)):
        response = await request(AsyncMock(spec=AsyncSession))

    assert response.status_code == 200
    assert response.json()["summary"]["total_queries"] == 4
    assert "query_text" not in response.text


async def test_build_summary_maps_counts_latency_evaluations_and_recommendations() -> None:
    now = datetime.now(UTC)
    run_id = uuid4()
    older_query_id = uuid4()
    newer_query_id = uuid4()
    recommendation = OptimizationRecommendation(
        id=uuid4(),
        evaluation_run_id=run_id,
        metric=OptimizationMetric.CONTEXT_RECALL,
        current_value=0.5,
        threshold=0.65,
        recommendation="Increase the hybrid candidate pool.",
        status=OptimizationStatus.OPEN,
        profile="BALANCED",
        strategy="HYBRID_RRF",
        created_at=now,
    )

    totals = query_result(one=SimpleNamespace(total_queries=3, avg_retrieval_latency_ms=812.5))
    strategies = query_result(
        rows=[
            SimpleNamespace(strategy="DENSE", query_count=2),
            SimpleNamespace(strategy="HYBRID_RRF", query_count=1),
        ]
    )
    latency = query_result(
        rows=[
            SimpleNamespace(query_id=newer_query_id, timestamp=now, retrieval_latency_ms=900),
            SimpleNamespace(
                query_id=older_query_id,
                timestamp=now - timedelta(minutes=1),
                retrieval_latency_ms=725,
            ),
        ]
    )
    evaluations = query_result(
        rows=[
            SimpleNamespace(
                run_id=run_id,
                completed_at=now,
                faithfulness=0.9,
                answer_relevancy=None,
                context_precision=0.7,
                context_recall=0.6,
            )
        ]
    )
    recommendations = MagicMock()
    recommendations.scalars.return_value.all.return_value = [recommendation]
    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = [totals, strategies, latency, evaluations, recommendations]

    result = await build_analytics_summary(session)

    assert result.summary.total_queries == 3
    assert result.summary.avg_retrieval_latency_ms == 812.5
    assert result.summary.answer_relevancy is None
    assert [(item.strategy, item.count) for item in result.strategy_distribution] == [
        ("DENSE", 2),
        ("HYBRID_RRF", 1),
    ]
    assert [item.query_id for item in result.latency_series] == [
        older_query_id,
        newer_query_id,
    ]
    assert result.evaluation_history[0].context_precision == 0.7
    assert result.recommendations[0].recommendation == "Increase the hybrid candidate pool."


async def test_build_summary_preserves_no_data_as_null_not_zero() -> None:
    empty = query_result(rows=[])
    recommendations = MagicMock()
    recommendations.scalars.return_value.all.return_value = []
    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = [
        query_result(one=SimpleNamespace(total_queries=0, avg_retrieval_latency_ms=None)),
        empty,
        empty,
        empty,
        recommendations,
    ]

    result = await build_analytics_summary(session)

    assert result.summary.total_queries == 0
    assert result.summary.avg_retrieval_latency_ms is None
    assert result.summary.faithfulness is None
    assert result.strategy_distribution == []
    assert result.latency_series == []
    assert result.evaluation_history == []
    assert result.recommendations == []
