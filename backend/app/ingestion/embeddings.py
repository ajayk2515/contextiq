import asyncio
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.config import Settings


class EmbeddingConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class SparseEmbedding:
    indices: list[int]
    values: list[float]


@lru_cache(maxsize=1)
def _sparse_model() -> Any:
    from fastembed import SparseTextEmbedding

    return SparseTextEmbedding(model_name="Qdrant/bm25")


class EmbeddingService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def dense(self, texts: list[str]) -> list[list[float]]:
        from openai import AsyncOpenAI

        if self.settings.openai_api_key is None:
            raise EmbeddingConfigurationError("OpenAI embeddings are not configured.")
        client = AsyncOpenAI(api_key=self.settings.openai_api_key.get_secret_value())
        try:
            embeddings: list[list[float]] = []
            for start in range(0, len(texts), 64):
                response = await client.embeddings.create(
                    model=self.settings.openai_embedding_model,
                    input=texts[start : start + 64],
                    dimensions=self.settings.openai_embedding_dimensions,
                )
                embeddings.extend(
                    item.embedding for item in sorted(response.data, key=lambda item: item.index)
                )
            return embeddings
        finally:
            await client.close()

    async def sparse(self, texts: list[str]) -> list[SparseEmbedding]:
        def generate() -> list[SparseEmbedding]:
            return [
                SparseEmbedding(
                    indices=embedding.indices.tolist(),
                    values=embedding.values.tolist(),
                )
                for embedding in _sparse_model().embed(texts)
            ]

        return await asyncio.to_thread(generate)
