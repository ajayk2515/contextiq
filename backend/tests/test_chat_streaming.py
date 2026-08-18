from collections.abc import AsyncIterator
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient, Response

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.conversations.models import Message, MessageRole
from app.conversations.service import ConversationTurn
from app.main import app
from app.query_intelligence.domain import (
    ExecutedRetrievalStrategy,
    IntendedRetrievalStrategy,
    QueryCategory,
    RetrievalProfile,
)
from app.rag.prompting import INSUFFICIENT_CONTEXT_ANSWER, ConversationHistoryMessage
from app.rag.schemas import ChatSource, QueryIntelligenceMetadata, TokenEvent
from app.rag.service import PreparedAnswer, RagService
from app.rag.sse import sse_event


def current_user() -> User:
    return User(id=uuid4(), email="hr@demo.com", password_hash="unused", role="HR")


def prepared(insufficient: bool = False) -> PreparedAnswer:
    source = ChatSource(
        document_id=uuid4(),
        chunk_id=uuid4(),
        filename="policy.md",
        page=None,
        section="Leave",
        snippet="Employees receive leave.",
    )
    return PreparedAnswer(
        question="What is the leave policy?",
        context="[SOURCE 1]\nPolicy",
        contexts=() if insufficient else ("Policy",),
        sources=[] if insufficient else [source],
        insufficient_context=insufficient,
        query_intelligence=QueryIntelligenceMetadata(
            query_id=uuid4(),
            category=QueryCategory.FAQ,
            profile=RetrievalProfile.FAST,
            intended_strategy=IntendedRetrievalStrategy.DENSE,
            executed_strategy=ExecutedRetrievalStrategy.DENSE,
            candidate_top_k=3,
            classification_fallback=False,
        ),
    )


async def stream_request(user: User, conversation_id: object) -> Response:
    async def override_user() -> User:
        return user

    app.dependency_overrides[get_current_user] = override_user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.post(
                "/api/chat/stream",
                json={
                    "conversation_id": str(conversation_id),
                    "message": "What is the leave policy?",
                },
            )
    finally:
        app.dependency_overrides.clear()


async def test_stream_emits_metadata_tokens_citations_complete_and_persists_assistant() -> None:
    user = current_user()
    conversation_id = uuid4()
    user_message_id = uuid4()
    assistant_id = uuid4()
    result = prepared()
    history = [ConversationHistoryMessage(role="assistant", content="Earlier answer")]
    store = MagicMock()
    store.begin_turn = AsyncMock(
        return_value=ConversationTurn(conversation_id, user_message_id, history)
    )
    store.persist_assistant = AsyncMock(
        return_value=Message(
            id=assistant_id,
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content="Grounded answer",
            sources=[],
            created_at=datetime.now(UTC),
        )
    )
    service = MagicMock()
    service.prepare = AsyncMock(return_value=result)
    service.close = AsyncMock()

    async def tokens(*_: object) -> AsyncIterator[str]:
        yield "Grounded "
        yield "answer"

    service.stream = tokens
    with (
        patch("app.rag.router.ConversationStore", return_value=store),
        patch("app.rag.router.RagService", return_value=service),
    ):
        response = await stream_request(user, conversation_id)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert [line for line in response.text.splitlines() if line.startswith("event:")] == [
        "event: metadata",
        "event: token",
        "event: token",
        "event: citations",
        "event: complete",
    ]
    assert str(result.query_intelligence.query_id) in response.text
    assert str(assistant_id) in response.text
    store.begin_turn.assert_awaited_once_with(
        conversation_id, user.id, "What is the leave policy?", 8
    )
    service.prepare.assert_awaited_once_with("What is the leave policy?", user.id, "HR")
    persist_args = store.persist_assistant.await_args.args
    assert persist_args[2] == "Grounded answer"
    assert persist_args[3] == result.query_intelligence.query_id
    assert persist_args[4] == result.sources
    service.close.assert_awaited_once()


async def test_stream_failure_keeps_user_message_without_completed_assistant() -> None:
    user = current_user()
    conversation_id = uuid4()
    store = MagicMock()
    store.begin_turn = AsyncMock(return_value=ConversationTurn(conversation_id, uuid4(), []))
    store.persist_assistant = AsyncMock()
    service = MagicMock()
    service.prepare = AsyncMock(return_value=prepared())
    service.close = AsyncMock()

    async def failing_stream(*_: object) -> AsyncIterator[str]:
        yield "Partial"
        raise HTTPException(
            status_code=503,
            detail={"code": "ANSWER_GENERATION_FAILED", "message": "Generation failed safely."},
        )

    service.stream = failing_stream
    with (
        patch("app.rag.router.ConversationStore", return_value=store),
        patch("app.rag.router.RagService", return_value=service),
    ):
        response = await stream_request(user, conversation_id)

    assert "event: token" in response.text
    assert "event: error" in response.text
    assert "ANSWER_GENERATION_FAILED" in response.text
    assert "event: complete" not in response.text
    store.persist_assistant.assert_not_awaited()


async def test_stream_rejects_cross_user_conversation_before_rag_execution() -> None:
    user = current_user()
    store = MagicMock()
    store.begin_turn = AsyncMock(
        side_effect=HTTPException(
            status_code=404,
            detail={
                "code": "CONVERSATION_NOT_FOUND",
                "message": "The requested conversation was not found.",
            },
        )
    )
    with (
        patch("app.rag.router.ConversationStore", return_value=store),
        patch("app.rag.router.RagService") as rag_service,
    ):
        response = await stream_request(user, uuid4())

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "CONVERSATION_NOT_FOUND"
    rag_service.assert_not_called()


async def test_insufficient_context_stream_is_deterministic_without_llm() -> None:
    generator = SimpleNamespace(stream=MagicMock())
    service = RagService.__new__(RagService)
    service.generator = generator

    tokens = [token async for token in service.stream(prepared(insufficient=True), [])]

    assert tokens == [INSUFFICIENT_CONTEXT_ANSWER]
    generator.stream.assert_not_called()


def test_sse_formatting_json_encodes_newlines_quotes_and_unicode() -> None:
    encoded = sse_event("token", TokenEvent(text='line one\n"quoted" caf\u00e9'))

    assert encoded.startswith("event: token\ndata: ")
    assert encoded.endswith("\n\n")
    assert '\\n\\"quoted\\" caf\u00e9' in encoded
