from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.query_intelligence.classifier import QueryClassifier
from app.query_intelligence.domain import (
    ExecutedRetrievalStrategy,
    IntendedRetrievalStrategy,
    QueryCategory,
    RetrievalProfile,
    StructuredClassification,
)
from app.query_intelligence.profiles import (
    CATEGORY_PROFILE_MAP,
    FALLBACK_CATEGORY,
    FALLBACK_PROFILE,
    profile_config,
)


def settings() -> Settings:
    return Settings(
        jwt_secret="unit-test-jwt-secret-with-at-least-thirty-two-characters",
        openai_api_key="test-openai-key",
    )


def test_all_categories_map_to_the_required_profiles() -> None:
    assert CATEGORY_PROFILE_MAP == {
        QueryCategory.FAQ: RetrievalProfile.FAST,
        QueryCategory.SPECIFIC_SEARCH: RetrievalProfile.BALANCED,
        QueryCategory.MULTI_DOC_COMPARISON: RetrievalProfile.ACCURATE,
        QueryCategory.SUMMARIZATION: RetrievalProfile.ACCURATE,
        QueryCategory.RESTRICTED_DATA: RetrievalProfile.BALANCED,
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"category": "UNKNOWN", "recommended_profile": "FAST"},
        {"category": "FAQ", "recommended_profile": "UNKNOWN"},
    ],
)
def test_structured_classification_rejects_unknown_enum_values(
    payload: dict[str, str],
) -> None:
    with pytest.raises(ValidationError):
        StructuredClassification.model_validate(payload)


def test_retrieval_profile_configuration_matches_phase_five_contract() -> None:
    fast = profile_config(RetrievalProfile.FAST)
    balanced = profile_config(RetrievalProfile.BALANCED)
    accurate = profile_config(RetrievalProfile.ACCURATE)

    assert (
        fast.intended_strategy,
        fast.executed_strategy,
        fast.candidate_top_k,
        fast.reranker_enabled,
        fast.final_top_k,
    ) == (
        IntendedRetrievalStrategy.DENSE,
        ExecutedRetrievalStrategy.DENSE,
        3,
        False,
        None,
    )
    assert (
        balanced.intended_strategy,
        balanced.executed_strategy,
        balanced.candidate_top_k,
        balanced.reranker_enabled,
        balanced.final_top_k,
    ) == (
        IntendedRetrievalStrategy.HYBRID,
        ExecutedRetrievalStrategy.HYBRID_RRF,
        8,
        False,
        None,
    )
    assert (
        accurate.intended_strategy,
        accurate.executed_strategy,
        accurate.candidate_top_k,
        accurate.reranker_enabled,
        accurate.final_top_k,
    ) == (
        IntendedRetrievalStrategy.HYBRID_WITH_RERANK,
        ExecutedRetrievalStrategy.HYBRID_RRF,
        15,
        False,
        5,
    )


@pytest.mark.parametrize(
    ("question", "category", "profile"),
    [
        ("How many annual leave days are provided?", QueryCategory.FAQ, RetrievalProfile.FAST),
        (
            "Find the parental leave policy.",
            QueryCategory.SPECIFIC_SEARCH,
            RetrievalProfile.BALANCED,
        ),
        (
            "Compare the HR and Finance travel policies.",
            QueryCategory.MULTI_DOC_COMPARISON,
            RetrievalProfile.ACCURATE,
        ),
        (
            "Summarize the employee handbook.",
            QueryCategory.SUMMARIZATION,
            RetrievalProfile.ACCURATE,
        ),
        (
            "What is the confidential HR retention bonus?",
            QueryCategory.RESTRICTED_DATA,
            RetrievalProfile.BALANCED,
        ),
    ],
)
async def test_classifier_uses_openai_structured_output(
    question: str,
    category: QueryCategory,
    profile: RetrievalProfile,
) -> None:
    parsed = StructuredClassification(
        category=category,
        recommended_profile=profile,
    )
    client = SimpleNamespace(
        responses=SimpleNamespace(
            parse=AsyncMock(return_value=SimpleNamespace(output_parsed=parsed))
        ),
        close=AsyncMock(),
    )

    with patch("openai.AsyncOpenAI", return_value=client) as client_factory:
        decision = await QueryClassifier(settings()).classify(question)

    assert decision.category == category
    assert decision.profile == profile
    assert decision.used_fallback is False
    assert client_factory.call_args.kwargs["api_key"] == "test-openai-key"
    parse_call = client.responses.parse.await_args.kwargs
    assert parse_call["text_format"] is StructuredClassification
    assert parse_call["input"] == question
    assert parse_call["store"] is False
    client.close.assert_awaited_once()


@pytest.mark.parametrize(
    "provider_result",
    [
        RuntimeError("provider unavailable"),
        SimpleNamespace(output_parsed=None),
        SimpleNamespace(
            output_parsed=StructuredClassification(
                category=QueryCategory.FAQ,
                recommended_profile=RetrievalProfile.ACCURATE,
            )
        ),
    ],
)
async def test_classifier_failures_use_deterministic_balanced_fallback(
    provider_result: object,
) -> None:
    parse = AsyncMock(
        side_effect=provider_result if isinstance(provider_result, Exception) else None,
        return_value=provider_result,
    )
    client = SimpleNamespace(
        responses=SimpleNamespace(parse=parse),
        close=AsyncMock(),
    )

    with patch("openai.AsyncOpenAI", return_value=client):
        decision = await QueryClassifier(settings()).classify("Find the travel policy")

    assert decision.category == FALLBACK_CATEGORY
    assert decision.profile == FALLBACK_PROFILE
    assert decision.used_fallback is True
    client.close.assert_awaited_once()


async def test_missing_openai_configuration_uses_fallback_without_creating_client() -> None:
    configured = settings().model_copy(update={"openai_api_key": None})

    with patch("openai.AsyncOpenAI") as client_factory:
        decision = await QueryClassifier(configured).classify("Find the policy")

    assert decision.category == FALLBACK_CATEGORY
    assert decision.profile == FALLBACK_PROFILE
    assert decision.used_fallback is True
    client_factory.assert_not_called()
