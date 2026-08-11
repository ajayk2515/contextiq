import asyncio
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from app.database import check_database
from app.vector_store import check_qdrant

router = APIRouter(tags=["health"])


class DependencyHealth(BaseModel):
    database: str
    qdrant: str


class HealthResponse(BaseModel):
    status: str
    services: DependencyHealth


async def _dependency_status(check: Callable[[], Awaitable[None]]) -> str:
    try:
        await check()
    except Exception:
        return "unavailable"
    return "ok"


@router.get("/health", response_model=HealthResponse)
async def health(response: Response) -> HealthResponse:
    database_status, qdrant_status = await asyncio.gather(
        _dependency_status(check_database),
        _dependency_status(check_qdrant),
    )
    healthy = database_status == qdrant_status == "ok"
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthResponse(
        status="ok" if healthy else "degraded",
        services=DependencyHealth(database=database_status, qdrant=qdrant_status),
    )
