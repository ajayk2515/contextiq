from collections.abc import AsyncIterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.database import get_session
from app.main import app
from app.optimization.models import (
    OptimizationMetric,
    OptimizationRecommendation,
    OptimizationStatus,
)


def user() -> User:
    return User(id=uuid4(), email="hr@demo.com", password_hash="unused", role="HR")


def recommendation() -> OptimizationRecommendation:
    return OptimizationRecommendation(
        id=uuid4(),
        evaluation_run_id=uuid4(),
        metric=OptimizationMetric.CONTEXT_RECALL,
        current_value=0.5,
        threshold=0.65,
        recommendation="Increase hybrid candidate coverage.",
        status=OptimizationStatus.OPEN,
        profile="BALANCED",
        strategy="HYBRID_RRF",
        created_at=datetime.now(UTC),
    )


async def request(
    method: str,
    path: str,
    session: AsyncSession,
    json: object | None = None,
    authenticated: bool = True,
):
    async def override_user() -> User:
        return user()

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    if authenticated:
        app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_session] = override_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.request(method, path, json=json)
    finally:
        app.dependency_overrides.clear()


async def test_lists_open_recommendations_scoped_to_evaluation_run() -> None:
    item = recommendation()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [item]
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = result

    response = await request(
        "GET", f"/api/recommendations?evaluation_run_id={item.evaluation_run_id}", session
    )

    assert response.status_code == 200
    assert response.json()[0]["metric"] == "CONTEXT_RECALL"
    statement = str(session.execute.await_args.args[0])
    assert "optimization_recommendations.status" in statement
    assert "optimization_recommendations.evaluation_run_id" in statement


async def test_dismisses_recommendation_without_deleting_it() -> None:
    item = recommendation()
    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = item

    response = await request(
        "PATCH",
        f"/api/recommendations/{item.id}",
        session,
        {"status": "DISMISSED"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "DISMISSED"
    assert item.status == OptimizationStatus.DISMISSED
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(item)
    session.delete.assert_not_called()


async def test_rejects_arbitrary_status_and_missing_recommendation() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = None

    invalid = await request(
        "PATCH",
        f"/api/recommendations/{uuid4()}",
        session,
        {"status": "APPLIED"},
    )
    missing = await request(
        "PATCH",
        f"/api/recommendations/{uuid4()}",
        session,
        {"status": "DISMISSED"},
    )

    assert invalid.status_code == 422
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "RECOMMENDATION_NOT_FOUND"


async def test_recommendation_endpoints_require_authentication() -> None:
    response = await request(
        "GET", "/api/recommendations", AsyncMock(spec=AsyncSession), authenticated=False
    )

    assert response.status_code == 401
