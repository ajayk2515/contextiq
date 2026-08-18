import logging
import math
from dataclasses import dataclass
from typing import Any

from app.config import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RagasScores:
    faithfulness: float | None
    answer_relevancy: float | None
    context_precision: float | None
    context_recall: float | None
    failed_metrics: tuple[str, ...] = ()


class RagasEvaluator:
    def __init__(self, settings: Settings) -> None:
        if settings.openai_api_key is None:
            raise RuntimeError("OpenAI is not configured for evaluation.")

        from openai import AsyncOpenAI
        from ragas.embeddings import embedding_factory
        from ragas.llms import llm_factory
        from ragas.metrics.collections import (
            AnswerRelevancy,
            ContextPrecision,
            ContextRecall,
            Faithfulness,
        )

        self.client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())
        judge = llm_factory(settings.ragas_llm_model, client=self.client)
        embeddings = embedding_factory(
            "openai",
            model=settings.ragas_embedding_model,
            client=self.client,
        )
        self.metrics: dict[str, Any] = {
            "faithfulness": Faithfulness(llm=judge),
            "answer_relevancy": AnswerRelevancy(llm=judge, embeddings=embeddings),
            "context_precision": ContextPrecision(llm=judge),
            "context_recall": ContextRecall(llm=judge),
        }

    async def _score(self, name: str, **inputs: object) -> float | None:
        try:
            result = await self.metrics[name].ascore(**inputs)
            value = float(result.value)
            if not math.isfinite(value):
                raise ValueError("Metric returned a non-finite value.")
            if name == "answer_relevancy":
                if not -1 <= value <= 1:
                    raise ValueError("Metric returned a value outside its expected range.")
            elif not 0 <= value <= 1:
                raise ValueError("Metric returned a value outside its expected range.")
            return value
        except Exception:
            logger.exception("RAGAS metric %s failed", name)
            return None

    async def evaluate(
        self,
        question: str,
        answer: str,
        contexts: list[str],
        reference: str,
    ) -> RagasScores:
        values = {
            "faithfulness": await self._score(
                "faithfulness",
                user_input=question,
                response=answer,
                retrieved_contexts=contexts,
            ),
            "answer_relevancy": await self._score(
                "answer_relevancy",
                user_input=question,
                response=answer,
            ),
            "context_precision": await self._score(
                "context_precision",
                user_input=question,
                reference=reference,
                retrieved_contexts=contexts,
            ),
            "context_recall": await self._score(
                "context_recall",
                user_input=question,
                reference=reference,
                retrieved_contexts=contexts,
            ),
        }
        return RagasScores(
            faithfulness=values["faithfulness"],
            answer_relevancy=values["answer_relevancy"],
            context_precision=values["context_precision"],
            context_recall=values["context_recall"],
            failed_metrics=tuple(name for name, value in values.items() if value is None),
        )

    async def close(self) -> None:
        await self.client.close()
