from dataclasses import dataclass

from app.query_intelligence.domain import (
    ExecutedRetrievalStrategy,
    IntendedRetrievalStrategy,
    QueryCategory,
    RetrievalProfile,
)


@dataclass(frozen=True)
class RetrievalProfileConfig:
    profile: RetrievalProfile
    intended_strategy: IntendedRetrievalStrategy
    executed_strategy: ExecutedRetrievalStrategy
    candidate_top_k: int
    reranker_enabled: bool
    final_top_k: int | None = None


PROFILE_CONFIGS = {
    RetrievalProfile.FAST: RetrievalProfileConfig(
        profile=RetrievalProfile.FAST,
        intended_strategy=IntendedRetrievalStrategy.DENSE,
        executed_strategy=ExecutedRetrievalStrategy.DENSE,
        candidate_top_k=3,
        reranker_enabled=False,
    ),
    RetrievalProfile.BALANCED: RetrievalProfileConfig(
        profile=RetrievalProfile.BALANCED,
        intended_strategy=IntendedRetrievalStrategy.HYBRID,
        executed_strategy=ExecutedRetrievalStrategy.HYBRID_RRF,
        candidate_top_k=8,
        reranker_enabled=False,
    ),
    RetrievalProfile.ACCURATE: RetrievalProfileConfig(
        profile=RetrievalProfile.ACCURATE,
        intended_strategy=IntendedRetrievalStrategy.HYBRID_WITH_RERANK,
        executed_strategy=ExecutedRetrievalStrategy.HYBRID_RRF,
        candidate_top_k=15,
        reranker_enabled=False,
        final_top_k=5,
    ),
}

CATEGORY_PROFILE_MAP = {
    QueryCategory.FAQ: RetrievalProfile.FAST,
    QueryCategory.SPECIFIC_SEARCH: RetrievalProfile.BALANCED,
    QueryCategory.MULTI_DOC_COMPARISON: RetrievalProfile.ACCURATE,
    QueryCategory.SUMMARIZATION: RetrievalProfile.ACCURATE,
    QueryCategory.RESTRICTED_DATA: RetrievalProfile.BALANCED,
}

FALLBACK_CATEGORY = QueryCategory.SPECIFIC_SEARCH
FALLBACK_PROFILE = RetrievalProfile.BALANCED


def profile_for_category(category: QueryCategory) -> RetrievalProfile:
    return CATEGORY_PROFILE_MAP[category]


def profile_config(profile: RetrievalProfile) -> RetrievalProfileConfig:
    return PROFILE_CONFIGS[profile]
