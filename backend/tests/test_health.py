from unittest.mock import AsyncMock, patch

from httpx import ASGITransport, AsyncClient

from app.main import app, lifespan


async def test_startup_recovers_interrupted_documents() -> None:
    recovery = AsyncMock()
    close = AsyncMock()

    with (
        patch("app.main.recover_interrupted_documents", recovery),
        patch("app.main.close_database", close),
    ):
        async with lifespan(app):
            recovery.assert_awaited_once()

    close.assert_awaited_once()


async def test_health_reports_connected_dependencies() -> None:
    with (
        patch("app.api.health.check_database", new=AsyncMock()),
        patch("app.api.health.check_qdrant", new=AsyncMock()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "services": {"database": "ok", "qdrant": "ok"},
    }


async def test_health_fails_cleanly_when_a_dependency_is_unavailable() -> None:
    with (
        patch(
            "app.api.health.check_database",
            new=AsyncMock(side_effect=ConnectionError("database unavailable")),
        ),
        patch("app.api.health.check_qdrant", new=AsyncMock()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")

    assert response.status_code == 503
    assert response.json() == {
        "status": "degraded",
        "services": {"database": "unavailable", "qdrant": "ok"},
    }
    assert "database unavailable" not in response.text
