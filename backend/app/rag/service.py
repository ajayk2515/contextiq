import logging
from time import perf_counter
from uuid import UUID

from app.config import Settings
from app.ingestion.embeddings import EmbeddingService
from app.query_intelligence.classifier import QueryClassifier
from app.query_intelligence.domain import ExecutedRetrievalStrategy, QueryDecision
from app.query_intelligence.persistence import QueryLogWriter
from app.query_intelligence.profiles import RetrievalProfileConfig, profile_config
from app.rag.errors import raise_chat_unavailable
from app.rag.generation import AnswerGenerator
from app.rag.prompting import INSUFFICIENT_CONTEXT_ANSWER, build_context
from app.rag.reranking import RerankerService
from app.rag.retrieval import QdrantRetriever, RetrievedChunk
from app.rag.schemas import ChatResponse, ChatSource, QueryIntelligenceMetadata

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


def _query_metadata(
    query_id: UUID,
    decision: QueryDecision,
    profile: RetrievalProfileConfig,
) -> QueryIntelligenceMetadata:
    return QueryIntelligenceMetadata(
        query_id=query_id,
        category=decision.category,
        profile=decision.profile,
        intended_strategy=profile.intended_strategy,
        executed_strategy=profile.executed_strategy,
        candidate_top_k=profile.candidate_top_k,
        classification_fallback=decision.used_fallback,
    )


class RagService:
    def __init__(
        self,
        settings: Settings,
        embedding_service: EmbeddingService | None = None,
        retriever: QdrantRetriever | None = None,
        generator: AnswerGenerator | None = None,
        classifier: QueryClassifier | None = None,
        query_log_writer: QueryLogWriter | None = None,
        reranker: RerankerService | None = None,
    ) -> None:
        self.settings = settings
        self.embedding_service = embedding_service or EmbeddingService(settings)
        self.retriever = retriever or QdrantRetriever(settings)
        self.generator = generator or AnswerGenerator(settings)
        self.classifier = classifier or QueryClassifier(settings)
        self.query_log_writer = query_log_writer or QueryLogWriter()
        self.reranker = reranker or RerankerService(settings)

    async def answer(self, question: str, user_id: UUID, role: str) -> ChatResponse:
        decision = await self.classifier.classify(question)
        profile = profile_config(decision.profile)
        retrieval_started = perf_counter()

        try:
            query_vectors = await self.embedding_service.dense([question])
        except Exception:
            logger.exception("Query embedding failed")
            raise_chat_unavailable(
                "QUERY_EMBEDDING_FAILED",
                "The question could not be embedded. Please try again.",
            )

        if profile.executed_strategy in {
            ExecutedRetrievalStrategy.HYBRID_RRF,
            ExecutedRetrievalStrategy.HYBRID_RRF_RERANK,
        }:
            try:
                sparse_vectors = await self.embedding_service.sparse([question])
            except Exception:
                logger.exception("Sparse query generation failed")
                raise_chat_unavailable(
                    "SPARSE_QUERY_FAILED",
                    "The lexical query representation could not be generated. Please try again.",
                )
            try:
                chunks = await self.retriever.search_hybrid(
                    query_vectors[0],
                    sparse_vectors[0],
                    role,
                    profile.candidate_top_k,
                )
            except Exception:
                logger.exception("Hybrid RRF retrieval failed")
                raise_chat_unavailable(
                    "HYBRID_RETRIEVAL_FAILED",
                    "Hybrid document retrieval is temporarily unavailable. Please try again.",
                )
        else:
            try:
                chunks = await self.retriever.search_dense(
                    query_vectors[0], role, profile.candidate_top_k
                )
            except Exception:
                logger.exception("Dense retrieval failed")
                raise_chat_unavailable(
                    "RETRIEVAL_FAILED",
                    "Document retrieval is temporarily unavailable. Please try again.",
                )

        if profile.reranker_enabled:
            try:
                if profile.final_top_k is None:
                    raise RuntimeError("The reranking profile has no final candidate limit.")
                chunks = await self.reranker.rerank(
                    question,
                    chunks,
                    profile.final_top_k,
                )
            except Exception:
                logger.exception("Cross-encoder reranking failed")
                raise_chat_unavailable(
                    "RERANKING_FAILED",
                    "The retrieved documents could not be reranked. Please try again.",
                )
        retrieval_latency_ms = max(0, round((perf_counter() - retrieval_started) * 1000))

        try:
            query_id = await self.query_log_writer.record(
                user_id,
                question,
                decision,
                profile,
                retrieval_latency_ms,
            )
        except Exception:
            logger.exception("Query metadata persistence failed")
            raise_chat_unavailable(
                "QUERY_LOG_FAILED",
                "Query metadata could not be saved. Please try again.",
            )

        metadata = _query_metadata(query_id, decision, profile)
        context, included_chunks = build_context(chunks, self.settings.rag_max_context_chars)
        if not included_chunks:
            return ChatResponse(
                answer=INSUFFICIENT_CONTEXT_ANSWER,
                sources=[],
                insufficient_context=True,
                query_intelligence=metadata,
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
            query_intelligence=metadata,
        )

    async def close(self) -> None:
        await self.retriever.close()
