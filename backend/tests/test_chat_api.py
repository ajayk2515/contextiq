from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from httpx import ASGITransport, AsyncClient

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.main import app
from app.rag.schemas import ChatResponse


async def test_chat_rejects_missing_authentication_and_invalid_message() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        missing_auth = await client.post("/api/chat", json={"message": "Question"})

    assert missing_auth.status_code == 401

    async def override_user() -> User:
        return User(id=uuid4(), email="hr@demo.com", password_hash="unused", role="HR")

    app.dependency_overrides[get_current_user] = override_user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            invalid = await client.post("/api/chat", json={"message": "   "})
            untrusted_role = await client.post(
                "/api/chat", json={"message": "Question", "role": "Executive"}
            )
    finally:
        app.dependency_overrides.clear()

    assert invalid.status_code == 422
    assert untrusted_role.status_code == 422


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
    service.answer.assert_awaited_once_with("What is the policy?", "HR")
    service.close.assert_awaited_once()
