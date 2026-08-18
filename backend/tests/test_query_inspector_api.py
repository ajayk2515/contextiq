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
from app.query_intelligence.models import QueryLog, RetrievalLog


def user(email: str = "developer@demo.com") -> User:
    return User(id=uuid4(), email=email, password_hash="unused", role="Developer")


def query(current_user: User, strategy: str = "HYBRID_RRF_RERANK") -> QueryLog:
    return QueryLog(
        id=uuid4(),
        user_id=current_user.id,
        query_text="Compare the leave policies",
        query_category="MULTI_DOC_COMPARISON",
        retrieval_profile="ACCURATE",
        retrieval_strategy=strategy,
        classifier_fallback=False,
        retrieval_latency_ms=42,
        created_at=datetime.now(UTC),
    )


def snapshot(query_id) -> RetrievalLog:
    return RetrievalLog(
        id=uuid4(),
        query_id=query_id,
        document_id=uuid4(),
        chunk_id=uuid4(),
        filename="deleted-source.pdf",
        page=None,
        section="Leave",
        snippet="Historical source content remains inspectable.",
        rank_before=3,
        rank_after=1,
        retrieval_score=None,
        rrf_score=0.025,
        reranker_score=0.88,
        included_in_context=True,
        created_at=datetime.now(UTC),
    )


async def request(path: str, current_user: User, session: AsyncSession):
    async def override_user() -> User:
        return current_user

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_session] = override_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.get(path)
    finally:
        app.dependency_overrides.clear()


async def test_lists_only_current_users_queries_in_repository_order() -> None:
    current_user = user()
    own_query = query(current_user, "DENSE")
    result = MagicMock()
    result.scalars.return_value.all.return_value = [own_query]
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = result

    response = await request("/api/queries", current_user, session)

    assert response.status_code == 200
    assert response.json()[0]["id"] == str(own_query.id)
    assert response.json()[0]["retrieval_strategy"] == "DENSE"
    statement = str(session.execute.await_args.args[0])
    assert "query_logs.user_id" in statement
    assert "ORDER BY query_logs.created_at DESC" in statement
    assert "LIMIT" in statement


async def test_returns_owned_query_counts_and_historical_snapshot() -> None:
    current_user = user()
    own_query = query(current_user)
    persisted_snapshot = snapshot(own_query.id)
    owned_result = MagicMock()
    owned_result.scalar_one_or_none.return_value = own_query
    count_result = MagicMock()
    count_result.one.return_value = (7, 5)
    retrieval_result = MagicMock()
    retrieval_result.scalars.return_value.all.return_value = [persisted_snapshot]
    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = [owned_result, count_result, owned_result, retrieval_result]

    detail = await request(f"/api/queries/{own_query.id}", current_user, session)
    retrieval = await request(f"/api/queries/{own_query.id}/retrieval", current_user, session)

    assert detail.status_code == 200
    assert detail.json()["candidate_count"] == 7
    assert detail.json()["final_context_count"] == 5
    assert detail.json()["reranked"] is True
    assert retrieval.status_code == 200
    item = retrieval.json()[0]
    assert item["filename"] == "deleted-source.pdf"
    assert item["document_id"] == str(persisted_snapshot.document_id)
    assert item["rrf_score"] == 0.025
    assert item["reranker_score"] == 0.88
    assert item["included_in_context"] is True


async def test_cross_user_query_and_retrieval_return_same_safe_not_found() -> None:
    current_user = user()
    query_id = uuid4()
    missing = MagicMock()
    missing.scalar_one_or_none.return_value = None
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = missing

    detail = await request(f"/api/queries/{query_id}", current_user, session)
    retrieval = await request(f"/api/queries/{query_id}/retrieval", current_user, session)

    assert detail.status_code == retrieval.status_code == 404
    assert detail.json()["detail"]["code"] == "QUERY_NOT_FOUND"
    assert retrieval.json()["detail"]["code"] == "QUERY_NOT_FOUND"
    for call in session.execute.await_args_list:
        assert "query_logs.user_id" in str(call.args[0])
