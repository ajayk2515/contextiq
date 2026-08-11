from qdrant_client import AsyncQdrantClient

from app.config import get_settings


def create_qdrant_client() -> AsyncQdrantClient:
    settings = get_settings()
    return AsyncQdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
        timeout=5,
    )


async def check_qdrant() -> None:
    client = create_qdrant_client()
    try:
        await client.get_collections()
    finally:
        await client.close()
