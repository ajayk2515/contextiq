from dataclasses import dataclass

from app.optimization.models import OptimizationMetric
from app.query_intelligence.domain import ExecutedRetrievalStrategy, RetrievalProfile

CONTEXT_RECALL_THRESHOLD = 0.65
CONTEXT_PRECISION_THRESHOLD = 0.60
RETRIEVAL_LATENCY_THRESHOLD_MS = 2500.0


@dataclass(frozen=True)
class OptimizationObservation:
    profile: RetrievalProfile
    strategy: ExecutedRetrievalStrategy
    context_recall: float | None
    context_precision: float | None
    retrieval_latency_ms: float


@dataclass(frozen=True)
class RecommendationDraft:
    metric: OptimizationMetric
    current_value: float
    threshold: float
    recommendation: str
    profile: RetrievalProfile
    strategy: ExecutedRetrievalStrategy


def _recall_recommendation(observation: OptimizationObservation) -> str:
    if observation.strategy == ExecutedRetrievalStrategy.HYBRID_RRF_RERANK:
        return (
            "ACCURATE retrieval still has low context recall. Consider increasing the "
            "initial hybrid candidate pool before reranking."
        )
    if observation.strategy == ExecutedRetrievalStrategy.HYBRID_RRF:
        return (
            "Hybrid retrieval has low context recall. Consider increasing the hybrid "
            "candidate pool."
        )
    return (
        "Dense retrieval has low context recall. Consider routing similar queries to "
        "BALANCED or increasing the dense candidate count."
    )


def _precision_recommendation(observation: OptimizationObservation) -> str:
    if observation.strategy == ExecutedRetrievalStrategy.HYBRID_RRF_RERANK:
        return (
            "Context precision remains low after reranking. Review candidate generation "
            "or reduce noisy retrieval breadth."
        )
    if observation.strategy == ExecutedRetrievalStrategy.HYBRID_RRF:
        return (
            "Hybrid retrieval has low context precision. Consider using ACCURATE "
            "cross-encoder reranking for this query type."
        )
    return (
        "Dense retrieval has low context precision. Consider using BALANCED or ACCURATE "
        "for query types where dense-only retrieval is noisy."
    )


def _latency_recommendation(observation: OptimizationObservation) -> str:
    if observation.strategy == ExecutedRetrievalStrategy.HYBRID_RRF_RERANK:
        return (
            "ACCURATE retrieval exceeds the latency target. Use FAST or BALANCED for "
            "queries that do not require comparison or reranking."
        )
    if observation.strategy == ExecutedRetrievalStrategy.HYBRID_RRF:
        return (
            "Hybrid retrieval exceeds the latency target. Review candidate count or route "
            "simple FAQ queries to FAST."
        )
    return (
        "Dense retrieval exceeds the latency target. Review embedding and Qdrant latency "
        "before reducing retrieval quality."
    )


def evaluate_rules(observation: OptimizationObservation) -> list[RecommendationDraft]:
    recommendations: list[RecommendationDraft] = []
    if (
        observation.context_recall is not None
        and observation.context_recall < CONTEXT_RECALL_THRESHOLD
    ):
        recommendations.append(
            RecommendationDraft(
                metric=OptimizationMetric.CONTEXT_RECALL,
                current_value=observation.context_recall,
                threshold=CONTEXT_RECALL_THRESHOLD,
                recommendation=_recall_recommendation(observation),
                profile=observation.profile,
                strategy=observation.strategy,
            )
        )
    if (
        observation.context_precision is not None
        and observation.context_precision < CONTEXT_PRECISION_THRESHOLD
    ):
        recommendations.append(
            RecommendationDraft(
                metric=OptimizationMetric.CONTEXT_PRECISION,
                current_value=observation.context_precision,
                threshold=CONTEXT_PRECISION_THRESHOLD,
                recommendation=_precision_recommendation(observation),
                profile=observation.profile,
                strategy=observation.strategy,
            )
        )
    if observation.retrieval_latency_ms > RETRIEVAL_LATENCY_THRESHOLD_MS:
        recommendations.append(
            RecommendationDraft(
                metric=OptimizationMetric.RETRIEVAL_LATENCY_MS,
                current_value=observation.retrieval_latency_ms,
                threshold=RETRIEVAL_LATENCY_THRESHOLD_MS,
                recommendation=_latency_recommendation(observation),
                profile=observation.profile,
                strategy=observation.strategy,
            )
        )
    return recommendations
