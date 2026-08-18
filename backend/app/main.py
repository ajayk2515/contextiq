from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.auth.router import router as auth_router
from app.config import get_settings
from app.conversations.router import router as conversations_router
from app.database import close_database
from app.documents.router import router as documents_router
from app.evaluations.router import router as evaluations_router
from app.optimization.router import router as optimization_router
from app.query_intelligence.router import router as query_inspector_router
from app.rag.router import router as chat_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await close_database()


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="EKIP API",
        description="Enterprise Knowledge Intelligence Platform API",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(health_router)
    application.include_router(auth_router)
    application.include_router(documents_router)
    application.include_router(conversations_router)
    application.include_router(chat_router)
    application.include_router(query_inspector_router)
    application.include_router(evaluations_router)
    application.include_router(optimization_router)
    return application


app = create_app()
