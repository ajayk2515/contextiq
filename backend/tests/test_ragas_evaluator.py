from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.evaluations.ragas_adapter import RagasEvaluator


async def test_ragas_uses_exact_contexts_and_metric_specific_inputs() -> None:
    evaluator = RagasEvaluator.__new__(RagasEvaluator)
    evaluator.metrics = {
        "faithfulness": SimpleNamespace(ascore=AsyncMock(return_value=SimpleNamespace(value=0.9))),
        "answer_relevancy": SimpleNamespace(
            ascore=AsyncMock(return_value=SimpleNamespace(value=0.8))
        ),
        "context_precision": SimpleNamespace(
            ascore=AsyncMock(return_value=SimpleNamespace(value=0.7))
        ),
        "context_recall": SimpleNamespace(
            ascore=AsyncMock(return_value=SimpleNamespace(value=0.6))
        ),
    }
    contexts = ["first full chunk", "second full chunk"]

    scores = await evaluator.evaluate("Question", "Answer", contexts, "Reference")

    assert scores.faithfulness == 0.9
    assert scores.answer_relevancy == 0.8
    assert scores.context_precision == 0.7
    assert scores.context_recall == 0.6
    assert scores.failed_metrics == ()
    evaluator.metrics["faithfulness"].ascore.assert_awaited_once_with(
        user_input="Question", response="Answer", retrieved_contexts=contexts
    )
    evaluator.metrics["answer_relevancy"].ascore.assert_awaited_once_with(
        user_input="Question", response="Answer"
    )
    evaluator.metrics["context_precision"].ascore.assert_awaited_once_with(
        user_input="Question", reference="Reference", retrieved_contexts=contexts
    )
    evaluator.metrics["context_recall"].ascore.assert_awaited_once_with(
        user_input="Question", reference="Reference", retrieved_contexts=contexts
    )


async def test_one_metric_failure_returns_null_without_discarding_other_scores() -> None:
    evaluator = RagasEvaluator.__new__(RagasEvaluator)
    evaluator.metrics = {
        "faithfulness": SimpleNamespace(ascore=AsyncMock(return_value=SimpleNamespace(value=0.9))),
        "answer_relevancy": SimpleNamespace(
            ascore=AsyncMock(side_effect=RuntimeError("judge unavailable"))
        ),
        "context_precision": SimpleNamespace(
            ascore=AsyncMock(return_value=SimpleNamespace(value=0.7))
        ),
        "context_recall": SimpleNamespace(
            ascore=AsyncMock(return_value=SimpleNamespace(value=0.6))
        ),
    }

    scores = await evaluator.evaluate("Question", "Answer", ["Context"], "Reference")

    assert scores.answer_relevancy is None
    assert scores.failed_metrics == ("answer_relevancy",)
    assert scores.faithfulness == 0.9
    assert scores.context_precision == 0.7
    assert scores.context_recall == 0.6
