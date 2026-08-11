from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.auth.security import create_access_token, hash_password
from app.database import get_session
from app.main import app


def make_session(user: User | None) -> AsyncMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = result
    return session


async def request_with_session(
    method: str,
    url: str,
    session: AsyncMock,
    **kwargs: Any,
) -> Response:
    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = override_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.request(method, url, **kwargs)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture(scope="module")
def demo_user() -> User:
    return User(
        id=uuid4(),
        email="hr@demo.com",
        password_hash=hash_password("correct-password"),
        role="HR",
    )


async def test_valid_credentials_return_jwt(demo_user: User) -> None:
    response = await request_with_session(
        "POST",
        "/api/auth/login",
        make_session(demo_user),
        json={"email": "HR@DEMO.COM", "password": "correct-password"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]
    assert payload["user"] == {
        "id": str(demo_user.id),
        "email": "hr@demo.com",
        "role": "HR",
    }


async def test_invalid_credentials_fail_safely(demo_user: User) -> None:
    response = await request_with_session(
        "POST",
        "/api/auth/login",
        make_session(demo_user),
        json={"email": demo_user.email, "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "INVALID_CREDENTIALS"
    assert "password_hash" not in response.text


async def test_login_rejects_frontend_supplied_role(demo_user: User) -> None:
    response = await request_with_session(
        "POST",
        "/api/auth/login",
        make_session(demo_user),
        json={
            "email": demo_user.email,
            "password": "correct-password",
            "role": "Executive",
        },
    )

    assert response.status_code == 422


async def test_me_rejects_missing_and_invalid_tokens() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        missing_response = await client.get("/api/auth/me")
        invalid_response = await client.get(
            "/api/auth/me", headers={"Authorization": "Bearer invalid"}
        )

    assert missing_response.status_code == 401
    assert invalid_response.status_code == 401
    assert missing_response.json()["detail"]["code"] == "UNAUTHORIZED"


async def test_me_resolves_current_role_from_database(demo_user: User) -> None:
    token = create_access_token(demo_user.id, "Developer")
    response = await request_with_session(
        "GET",
        "/api/auth/me",
        make_session(demo_user),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "HR"
