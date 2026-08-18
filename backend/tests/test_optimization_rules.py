import pytest

from app.optimization.models import OptimizationMetric
from app.optimization.rules import (
    CONTEXT_PRECISION_THRESHOLD,
    CONTEXT_RECALL_THRESHOLD,
    RETRIEVAL_LATENCY_THRESHOLD_MS,
    OptimizationObservation,
    evaluate_rules,
)
from app.query_intelligence.domain import ExecutedRetrievalStrategy, RetrievalProfile


def observation(
    profile: RetrievalProfile = RetrievalProfile.BALANCED,
    strategy: ExecutedRetrievalStrategy = ExecutedRetrievalStrategy.HYBRID_RRF,
    recall: float | None = 0.9,
    precision: float | None = 0.9,
    latency: float = 500,
) -> OptimizationObservation:
    return OptimizationObservation(profile, strategy, recall, precision, latency)


@pytest.mark.parametrize(
    ("profile", "strategy", "expected_text"),
    [
        (RetrievalProfile.FAST, ExecutedRetrievalStrategy.DENSE, "BALANCED"),
        (
            RetrievalProfile.BALANCED,
            ExecutedRetrievalStrategy.HYBRID_RRF,
            "hybrid candidate pool",
        ),
        (
            RetrievalProfile.ACCURATE,
            ExecutedRetrievalStrategy.HYBRID_RRF_RERANK,
            "before reranking",
        ),
    ],
)
def test_low_recall_rule_is_profile_and_strategy_aware(
    profile: RetrievalProfile,
    strategy: ExecutedRetrievalStrategy,
    expected_text: str,
) -> None:
    result = evaluate_rules(observation(profile, strategy, recall=0.5))

    assert len(result) == 1
    assert result[0].metric == OptimizationMetric.CONTEXT_RECALL
    assert result[0].current_value == 0.5
    assert result[0].threshold == CONTEXT_RECALL_THRESHOLD
    assert expected_text in result[0].recommendation


@pytest.mark.parametrize("recall", [CONTEXT_RECALL_THRESHOLD, None])
def test_recall_boundary_and_null_do_not_trigger(recall: float | None) -> None:
    assert evaluate_rules(observation(recall=recall)) == []


def test_low_precision_recommends_reranking_only_when_not_already_active() -> None:
    balanced = evaluate_rules(observation(precision=0.45))[0]
    accurate = evaluate_rules(
        observation(
            RetrievalProfile.ACCURATE,
            ExecutedRetrievalStrategy.HYBRID_RRF_RERANK,
            precision=0.45,
        )
    )[0]

    assert balanced.metric == OptimizationMetric.CONTEXT_PRECISION
    assert "Consider using ACCURATE" in balanced.recommendation
    assert "remains low after reranking" in accurate.recommendation
    assert "Enable reranking" not in accurate.recommendation


@pytest.mark.parametrize("precision", [CONTEXT_PRECISION_THRESHOLD, None])
def test_precision_boundary_and_null_do_not_trigger(precision: float | None) -> None:
    assert evaluate_rules(observation(precision=precision)) == []


def test_high_latency_uses_actual_expensive_strategy() -> None:
    result = evaluate_rules(
        observation(
            RetrievalProfile.ACCURATE,
            ExecutedRetrievalStrategy.HYBRID_RRF_RERANK,
            latency=3000,
        )
    )

    assert result[0].metric == OptimizationMetric.RETRIEVAL_LATENCY_MS
    assert result[0].threshold == RETRIEVAL_LATENCY_THRESHOLD_MS
    assert "ACCURATE retrieval exceeds" in result[0].recommendation


def test_latency_boundary_does_not_trigger() -> None:
    assert evaluate_rules(observation(latency=RETRIEVAL_LATENCY_THRESHOLD_MS)) == []


def test_multiple_rules_generate_distinct_recommendations() -> None:
    result = evaluate_rules(observation(recall=0.5, precision=0.45, latency=3200))

    assert {item.metric for item in result} == {
        OptimizationMetric.CONTEXT_RECALL,
        OptimizationMetric.CONTEXT_PRECISION,
        OptimizationMetric.RETRIEVAL_LATENCY_MS,
    }


def test_healthy_metrics_generate_no_recommendations() -> None:
    assert evaluate_rules(observation()) == []
