from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.config import Settings
from app.ingestion.embeddings import EmbeddingConfigurationError, EmbeddingService


def settings(**overrides: object) -> Settings:
    return Settings(
        jwt_secret="unit-test-jwt-secret-with-at-least-thirty-two-characters",
        **overrides,
    )


async def test_dense_embeddings_require_backend_api_key() -> None:
    with pytest.raises(EmbeddingConfigurationError):
        await EmbeddingService(settings(openai_api_key=None)).dense(["policy text"])


async def test_dense_embeddings_use_configured_openai_model_and_dimensions() -> None:
    create = AsyncMock(
        return_value=SimpleNamespace(
            data=[
                SimpleNamespace(index=1, embedding=[0.2, 0.3]),
                SimpleNamespace(index=0, embedding=[0.1, 0.4]),
            ]
        )
    )
    client = SimpleNamespace(embeddings=SimpleNamespace(create=create), close=AsyncMock())
    with patch("openai.AsyncOpenAI", return_value=client) as constructor:
        result = await EmbeddingService(
            settings(
                openai_api_key="test-only-key",
                openai_embedding_model="configured-model",
                openai_embedding_dimensions=2,
            )
        ).dense(["first", "second"])

    constructor.assert_called_once_with(api_key="test-only-key")
    create.assert_awaited_once_with(
        model="configured-model",
        input=["first", "second"],
        dimensions=2,
    )
    client.close.assert_awaited_once()
    assert result == [[0.1, 0.4], [0.2, 0.3]]


async def test_sparse_embeddings_generate_bm25_indices_and_values() -> None:
    result = await EmbeddingService(settings()).sparse(["annual leave policy"])

    assert len(result) == 1
    assert result[0].indices
    assert len(result[0].indices) == len(result[0].values)
