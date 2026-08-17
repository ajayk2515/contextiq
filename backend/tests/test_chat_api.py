from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.auth.security import create_access_token
from app.database import get_session
from app.main import app
from app.query_intelligence.domain import (
    ExecutedRetrievalStrategy,
    IntendedRetrievalStrategy,
    QueryCategory,
    RetrievalProfile,
)
from app.rag.schemas import ChatResponse, QueryIntelligenceMetadata


def query_metadata() -> QueryIntelligenceMetadata:
    return QueryIntelligenceMetadata(
        query_id=uuid4(),
        category=QueryCategory.FAQ,
        profile=RetrievalProfile.FAST,
        intended_strategy=IntendedRetrievalStrategy.DENSE,
        executed_strategy=ExecutedRetrievalStrategy.DENSE,
        candidate_top_k=3,
        classification_fallback=False,
    )


async def test_chat_rejects_missing_authentication_and_invalid_message() -> None:
    with patch("app.rag.router.RagService") as service:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            missing_auth = await client.post("/api/chat", json={"message": "Question"})
            invalid_auth = await client.post(
                "/api/chat",
                json={"message": "Question"},
                headers={"Authorization": "Bearer invalid-token"},
            )

    assert missing_auth.status_code == 401
    assert invalid_auth.status_code == 401
    service.assert_not_called()

    async def override_user() -> User:
        return User(id=uuid4(), email="hr@demo.com", password_hash="unused", role="HR")

    app.dependency_overrides[get_current_user] = override_user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            invalid = await client.post("/api/chat", json={"message": "   "})
            untrusted_role = await client.post(
                "/api/chat", json={"message": "Question", "role": "Executive"}
            )
            untrusted_permissions = await client.post(
                "/api/chat",
                json={"message": "Question", "allowed_roles": ["Executive"]},
            )
    finally:
        app.dependency_overrides.clear()

    assert invalid.status_code == 422
    assert untrusted_role.status_code == 422
    assert untrusted_permissions.status_code == 422


async def test_chat_uses_role_from_authenticated_server_identity() -> None:
    current_user = User(id=uuid4(), email="hr@demo.com", password_hash="unused", role="HR")

    async def override_user() -> User:
        return current_user

    service = MagicMock()
    service.answer = AsyncMock(
        return_value=ChatResponse(
            answer="Grounded answer",
            sources=[],
            insufficient_context=False,
            query_intelligence=query_metadata(),
        )
    )
    service.close = AsyncMock()
    app.dependency_overrides[get_current_user] = override_user
    try:
        with patch("app.rag.router.RagService", return_value=service):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post("/api/chat", json={"message": "What is the policy?"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    service.answer.assert_awaited_once_with("What is the policy?", current_user.id, "HR")
    service.close.assert_awaited_once()


async def test_chat_uses_current_database_role_instead_of_stale_jwt_role() -> None:
    current_user = User(id=uuid4(), email="hr@demo.com", password_hash="unused", role="HR")
    stale_token = create_access_token(current_user.id, "Developer")
    result = MagicMock()
    result.scalar_one_or_none.return_value = current_user
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = result

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    service = MagicMock()
    service.answer = AsyncMock(
        return_value=ChatResponse(
            answer="Grounded answer",
            sources=[],
            insufficient_context=False,
            query_intelligence=query_metadata(),
        )
    )
    service.close = AsyncMock()
    app.dependency_overrides[get_session] = override_session
    try:
        with patch("app.rag.router.RagService", return_value=service):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/chat",
                    json={"message": "What is the policy?"},
                    headers={"Authorization": f"Bearer {stale_token}"},
                )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    service.answer.assert_awaited_once_with("What is the policy?", current_user.id, "HR")
