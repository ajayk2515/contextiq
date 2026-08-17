import logging

from app.config import Settings
from app.query_intelligence.domain import QueryDecision, StructuredClassification
from app.query_intelligence.profiles import (
    FALLBACK_CATEGORY,
    FALLBACK_PROFILE,
    profile_for_category,
)

logger = logging.getLogger(__name__)

CLASSIFICATION_PROMPT = """Classify the user's document question into exactly one category.
FAQ: a simple factual question answerable from a small amount of context.
SPECIFIC_SEARCH: a targeted lookup for a policy, concept, identifier, section, or detail.
MULTI_DOC_COMPARISON: compares or combines information across multiple sources.
SUMMARIZATION: asks for a broad summary or key points.
RESTRICTED_DATA: explicitly asks for confidential, sensitive, HR, finance, or executive data.

Map categories to profiles exactly:
FAQ -> FAST
SPECIFIC_SEARCH -> BALANCED
MULTI_DOC_COMPARISON -> ACCURATE
SUMMARIZATION -> ACCURATE
RESTRICTED_DATA -> BALANCED

Classification never grants access. Return only the structured classification."""


class QueryClassifier:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def classify(self, question: str) -> QueryDecision:
        try:
            return await self._classify(question)
        except Exception:
            logger.warning("Query classification failed; using the deterministic fallback")
            return QueryDecision(
                category=FALLBACK_CATEGORY,
                profile=FALLBACK_PROFILE,
                used_fallback=True,
            )

    async def _classify(self, question: str) -> QueryDecision:
        from openai import AsyncOpenAI

        if self.settings.openai_api_key is None:
            raise RuntimeError("OpenAI query classification is not configured.")

        client = AsyncOpenAI(api_key=self.settings.openai_api_key.get_secret_value())
        try:
            response = await client.responses.parse(
                model=self.settings.openai_chat_model,
                instructions=CLASSIFICATION_PROMPT,
                input=question,
                text_format=StructuredClassification,
                temperature=0,
                max_output_tokens=120,
                store=False,
            )
            parsed = response.output_parsed
            if not isinstance(parsed, StructuredClassification):
                raise ValueError("OpenAI returned no valid query classification.")
            expected_profile = profile_for_category(parsed.category)
            if parsed.recommended_profile != expected_profile:
                raise ValueError("The classified category and profile do not match.")
            return QueryDecision(category=parsed.category, profile=expected_profile)
        finally:
            await client.close()
