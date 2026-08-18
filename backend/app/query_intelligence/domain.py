from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class QueryCategory(StrEnum):
    FAQ = "FAQ"
    SPECIFIC_SEARCH = "SPECIFIC_SEARCH"
    MULTI_DOC_COMPARISON = "MULTI_DOC_COMPARISON"
    SUMMARIZATION = "SUMMARIZATION"
    RESTRICTED_DATA = "RESTRICTED_DATA"


class RetrievalProfile(StrEnum):
    FAST = "FAST"
    BALANCED = "BALANCED"
    ACCURATE = "ACCURATE"


class IntendedRetrievalStrategy(StrEnum):
    DENSE = "DENSE"
    HYBRID = "HYBRID"
    HYBRID_WITH_RERANK = "HYBRID_WITH_RERANK"


class ExecutedRetrievalStrategy(StrEnum):
    DENSE = "DENSE"
    HYBRID_RRF = "HYBRID_RRF"


class StructuredClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: QueryCategory
    recommended_profile: RetrievalProfile


class QueryDecision(BaseModel):
    category: QueryCategory
    profile: RetrievalProfile
    used_fallback: bool = False
