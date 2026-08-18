from collections.abc import AsyncIterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.database import get_session
from app.evaluations.models import Evaluation, EvaluationRun, EvaluationRunStatus
from app.main import app


def current_user() -> User:
    return User(id=uuid4(), email="developer@demo.com", password_hash="unused", role="Developer")


async def request(method: str, path: str, session: AsyncSession, json: object | None = None):
    async def override_user() -> User:
        return current_user()

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_session] = override_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.request(method, path, json=json)
    finally:
        app.dependency_overrides.clear()


async def test_authenticated_user_can_start_selected_cases() -> None:
    now = datetime.now(UTC)
    session = AsyncMock(spec=AsyncSession)
    session.add = MagicMock()
    session.commit = AsyncMock()

    async def refresh(run: EvaluationRun) -> None:
        run.id = uuid4()
        run.completed_cases = 0
        run.error_message = None
        run.started_at = now
        run.completed_at = None
        run.created_at = now

    session.refresh = AsyncMock(side_effect=refresh)
    with patch("app.evaluations.router.run_evaluation", new=AsyncMock()) as background:
        response = await request(
            "POST",
            "/api/evaluations/run",
            session,
            {"case_ids": ["faq-annual-leave"]},
        )

    assert response.status_code == 202
    assert response.json()["status"] == "RUNNING"
    assert response.json()["total_cases"] == 1
    background.assert_awaited_once()


async def test_start_rejects_unknown_case_and_request_paths() -> None:
    session = AsyncMock(spec=AsyncSession)

    unknown = await request("POST", "/api/evaluations/run", session, {"case_ids": ["unknown-case"]})
    path = await request(
        "POST", "/api/evaluations/run", session, {"dataset_path": "C:/private/data.json"}
    )

    assert unknown.status_code == 422
    assert unknown.json()["detail"]["code"] == "INVALID_EVALUATION_CASES"
    assert path.status_code == 422


async def test_detail_returns_nullable_metrics_and_averages_only_present_values() -> None:
    now = datetime.now(UTC)
    run = EvaluationRun(
        id=uuid4(),
        status=EvaluationRunStatus.COMPLETED,
        total_cases=2,
        completed_cases=2,
        started_at=now,
        completed_at=now,
        created_at=now,
    )
    first = Evaluation(
        id=uuid4(),
        run_id=run.id,
        evaluation_case_id="one",
        query_id=uuid4(),
        question="Question one",
        role="Developer",
        expected_answer="Reference",
        expected_document="policy.md",
        generated_answer="Answer",
        faithfulness=0.8,
        answer_relevancy=None,
        context_precision=0.6,
        context_recall=0.4,
        insufficient_context=False,
        created_at=now,
    )
    second = Evaluation(
        id=uuid4(),
        run_id=run.id,
        evaluation_case_id="two",
        question="Question two",
        role="HR",
        expected_answer="Reference",
        expected_document="policy.md",
        generated_answer=None,
        faithfulness=None,
        answer_relevancy=None,
        context_precision=0.8,
        context_recall=None,
        failure_category="RETRIEVAL",
        error_message="No context.",
        insufficient_context=True,
        created_at=now,
    )
    result = MagicMock()
    result.scalars.return_value.all.return_value = [first, second]
    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = run
    session.execute.return_value = result

    response = await request("GET", f"/api/evaluations/{run.id}", session)

    assert response.status_code == 200
    body = response.json()
    assert body["averages"] == {
        "faithfulness": 0.8,
        "answer_relevancy": None,
        "context_precision": 0.7,
        "context_recall": 0.4,
    }
    assert body["evaluations"][1]["failure_category"] == "RETRIEVAL"
