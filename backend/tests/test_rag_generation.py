from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.config import Settings
from app.ingestion.embeddings import EmbeddingConfigurationError
from app.rag.generation import AnswerGenerator
from app.rag.prompting import SYSTEM_PROMPT, ConversationHistoryMessage


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "jwt_secret": "unit-test-jwt-secret-with-at-least-thirty-two-characters",
        "openai_api_key": None,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


async def test_answer_generation_uses_configured_model_and_grounding_prompt() -> None:
    create = AsyncMock(return_value=SimpleNamespace(output_text="Grounded answer [SOURCE 1]"))
    client = SimpleNamespace(responses=SimpleNamespace(create=create), close=AsyncMock())
    configured = settings(
        openai_api_key="test-only-key",
        openai_chat_model="configured-chat-model",
        rag_max_answer_tokens=321,
    )

    with patch("openai.AsyncOpenAI", return_value=client) as constructor:
        answer = await AnswerGenerator(configured).generate("Question?", "[SOURCE 1]\nContext")

    constructor.assert_called_once_with(api_key="test-only-key")
    create.assert_awaited_once_with(
        model="configured-chat-model",
        instructions=SYSTEM_PROMPT,
        input="Question:\nQuestion?\n\nRetrieved context:\n[SOURCE 1]\nContext",
        temperature=0.1,
        max_output_tokens=321,
        store=False,
    )
    client.close.assert_awaited_once()
    assert answer == "Grounded answer [SOURCE 1]"


async def test_answer_generation_requires_backend_openai_key() -> None:
    with pytest.raises(EmbeddingConfigurationError):
        await AnswerGenerator(settings()).generate("Question?", "Context")


async def test_answer_streaming_uses_bounded_history_and_emits_only_text_deltas() -> None:
    async def events():
        for event in [
            SimpleNamespace(type="response.created"),
            SimpleNamespace(type="response.output_text.delta", delta="Grounded "),
            SimpleNamespace(type="response.output_text.delta", delta="answer"),
            SimpleNamespace(type="response.completed"),
        ]:
            yield event

    create = AsyncMock(return_value=events())
    client = SimpleNamespace(responses=SimpleNamespace(create=create), close=AsyncMock())
    configured = settings(openai_api_key="test-only-key")
    history = [
        ConversationHistoryMessage(role="user", content="Earlier question"),
        ConversationHistoryMessage(role="assistant", content="Earlier grounded answer"),
    ]

    with patch("openai.AsyncOpenAI", return_value=client):
        tokens = [
            token
            async for token in AnswerGenerator(configured).stream(
                "Follow-up?", "[SOURCE 1]\nContext", history
            )
        ]

    assert tokens == ["Grounded ", "answer"]
    request = create.await_args.kwargs
    assert request["stream"] is True
    assert request["input"] == [
        {"role": "user", "content": "Earlier question"},
        {"role": "assistant", "content": "Earlier grounded answer"},
        {
            "role": "user",
            "content": "Question:\nFollow-up?\n\nRetrieved context:\n[SOURCE 1]\nContext",
        },
    ]
    client.close.assert_awaited_once()
