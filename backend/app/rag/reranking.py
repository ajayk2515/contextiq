import asyncio
from collections.abc import Iterable
from dataclasses import replace
from functools import lru_cache
from typing import Protocol, cast

from app.config import Settings
from app.rag.retrieval import RetrievedChunk


class CrossEncoder(Protocol):
    def rerank(
        self,
        query: str,
        documents: Iterable[str],
        batch_size: int = 64,
        **kwargs: object,
    ) -> Iterable[float]: ...


@lru_cache(maxsize=1)
def _cross_encoder_model(model_name: str) -> CrossEncoder:
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    return cast(
        CrossEncoder,
        TextCrossEncoder(
            model_name=model_name,
            providers=["CPUExecutionProvider"],
            lazy_load=True,
        ),
    )


class RerankerService:
    def __init__(self, settings: Settings, model: CrossEncoder | None = None) -> None:
        self.settings = settings
        self._model = model

    async def rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        final_top_k: int,
    ) -> list[RetrievedChunk]:
        if not candidates:
            return []

        def score_candidates() -> list[float]:
            model = self._model or _cross_encoder_model(self.settings.reranker_model)
            return [
                float(score)
                for score in model.rerank(
                    query,
                    [candidate.text for candidate in candidates],
                    batch_size=min(16, len(candidates)),
                )
            ]

        scores = await asyncio.to_thread(score_candidates)
        if len(scores) != len(candidates):
            raise RuntimeError("The reranker returned an unexpected number of scores.")

        scored = list(zip(candidates, scores, strict=True))
        scored.sort(key=lambda item: item[1], reverse=True)
        return [
            replace(candidate, reranker_score=score, rank_after=rank)
            for rank, (candidate, score) in enumerate(scored[:final_top_k], start=1)
        ]
