import asyncio
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.auth.dependencies import CurrentUser
from app.config import get_settings
from app.conversations.service import ConversationStore
from app.rag.schemas import (
    ChatRequest,
    ChatResponse,
    ChatStreamRequest,
    CitationsEvent,
    CompleteEvent,
    StreamErrorEvent,
    TokenEvent,
)
from app.rag.service import RagService
from app.rag.sse import sse_event

router = APIRouter(prefix="/api/chat", tags=["chat"])
logger = logging.getLogger(__name__)


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest, current_user: CurrentUser) -> ChatResponse:
    service = RagService(get_settings())
    try:
        return await service.answer(request.message, current_user.id, current_user.role)
    finally:
        await service.close()


def _stream_error(error: Exception) -> StreamErrorEvent:
    if isinstance(error, HTTPException) and isinstance(error.detail, dict):
        code = error.detail.get("code")
        message = error.detail.get("message")
        if isinstance(code, str) and isinstance(message, str):
            return StreamErrorEvent(code=code, message=message)
    return StreamErrorEvent(
        code="CHAT_STREAM_FAILED",
        message="The response stream could not be completed. Please try again.",
    )


@router.post("/stream")
async def stream_chat(
    request: ChatStreamRequest,
    current_user: CurrentUser,
) -> StreamingResponse:
    settings = get_settings()
    conversations = ConversationStore()
    turn = await conversations.begin_turn(
        request.conversation_id,
        current_user.id,
        request.message,
        settings.chat_history_message_limit,
    )
    service = RagService(settings)

    async def events() -> AsyncIterator[str]:
        try:
            prepared = await service.prepare(request.message, current_user.id, current_user.role)
            yield sse_event("metadata", prepared.query_intelligence)

            answer_parts: list[str] = []
            async for token in service.stream(prepared, turn.history):
                answer_parts.append(token)
                yield sse_event("token", TokenEvent(text=token))

            answer = "".join(answer_parts).strip()
            if not answer:
                raise RuntimeError("The completed answer was empty.")
            assistant = await conversations.persist_assistant(
                turn.conversation_id,
                current_user.id,
                answer,
                prepared.query_intelligence.query_id,
                prepared.sources,
                prepared.insufficient_context,
            )
            yield sse_event("citations", CitationsEvent(sources=prepared.sources))
            yield sse_event(
                "complete",
                CompleteEvent(
                    query_id=prepared.query_intelligence.query_id,
                    assistant_message_id=assistant.id,
                    insufficient_context=prepared.insufficient_context,
                ),
            )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.exception("Chat stream failed")
            yield sse_event("error", _stream_error(error))
        finally:
            await service.close()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
