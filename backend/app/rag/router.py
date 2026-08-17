from fastapi import APIRouter

from app.auth.dependencies import CurrentUser
from app.config import get_settings
from app.rag.schemas import ChatRequest, ChatResponse
from app.rag.service import RagService

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest, current_user: CurrentUser) -> ChatResponse:
    service = RagService(get_settings())
    try:
        return await service.answer(request.message, current_user.role)
    finally:
        await service.close()
