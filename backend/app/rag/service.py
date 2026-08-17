import logging

from app.config import Settings
from app.ingestion.embeddings import EmbeddingService
from app.rag.errors import raise_chat_unavailable
from app.rag.generation import AnswerGenerator
from app.rag.prompting import INSUFFICIENT_CONTEXT_ANSWER, build_context
from app.rag.retrieval import DenseRetriever, RetrievedChunk
from app.rag.schemas import ChatResponse, ChatSource

logger = logging.getLogger(__name__)


def _snippet(text: str, maximum_characters: int = 320) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= maximum_characters:
        return normalized
    return normalized[: maximum_characters - 3].rstrip() + "..."


def _source(chunk: RetrievedChunk) -> ChatSource:
    return ChatSource(
        document_id=chunk.document_id,
        chunk_id=chunk.chunk_id,
        filename=chunk.filename,
        page=chunk.page,
        section=chunk.section,
        snippet=_snippet(chunk.text),
    )


class RagService:
    def __init__(
        self,
        settings: Settings,
        embedding_service: EmbeddingService | None = None,
        retriever: DenseRetriever | None = None,
        generator: AnswerGenerator | None = None,
    ) -> None:
        self.settings = settings
        self.embedding_service = embedding_service or EmbeddingService(settings)
        self.retriever = retriever or DenseRetriever(settings)
        self.generator = generator or AnswerGenerator(settings)

    async def answer(self, question: str, role: str) -> ChatResponse:
        try:
            query_vectors = await self.embedding_service.dense([question])
        except Exception:
            logger.exception("Query embedding failed")
            raise_chat_unavailable(
                "QUERY_EMBEDDING_FAILED",
                "The question could not be embedded. Please try again.",
            )

        try:
            chunks = await self.retriever.search(query_vectors[0], role)
        except Exception:
            logger.exception("Dense retrieval failed")
            raise_chat_unavailable(
                "RETRIEVAL_FAILED",
                "Document retrieval is temporarily unavailable. Please try again.",
            )

        context, included_chunks = build_context(chunks, self.settings.rag_max_context_chars)
        if not included_chunks:
            return ChatResponse(
                answer=INSUFFICIENT_CONTEXT_ANSWER,
                sources=[],
                insufficient_context=True,
            )

        try:
            answer = await self.generator.generate(question, context)
        except Exception:
            logger.exception("Grounded answer generation failed")
            raise_chat_unavailable(
                "ANSWER_GENERATION_FAILED",
                "The answer could not be generated. Please try again.",
            )

        return ChatResponse(
            answer=answer,
            sources=[_source(chunk) for chunk in included_chunks],
            insufficient_context=False,
        )

    async def close(self) -> None:
        await self.retriever.close()
