from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.config import Settings
from app.ingestion.embeddings import SparseEmbedding
from app.query_intelligence.domain import (
    ExecutedRetrievalStrategy,
    QueryCategory,
    QueryDecision,
    RetrievalProfile,
)
from app.query_intelligence.profiles import profile_config
from app.rag.prompting import (
    INSUFFICIENT_CONTEXT_ANSWER,
    ConversationHistoryMessage,
    build_context,
)
from app.rag.reranking import RerankerService
from app.rag.retrieval import RetrievedChunk
from app.rag.service import RagService


def settings(**overrides: object) -> Settings:
    return Settings(
        jwt_secret="unit-test-jwt-secret-with-at-least-thirty-two-characters",
        openai_api_key=None,
        openai_embedding_dimensions=2,
        **overrides,
    )


def chunk(
    text: str = "Employees receive twenty days of annual leave.",
    filename: str = "handbook.md",
    rank_before: int | None = None,
) -> RetrievedChunk:
    return RetrievedChunk(
        document_id=uuid4(),
        chunk_id=uuid4(),
        filename=filename,
        page=None,
        section="Annual Leave",
        text=text,
        allowed_roles=("HR",),
        score=0.84,
        rank_before=rank_before,
        rrf_score=0.84 if rank_before is not None else None,
    )


def query_decision(
    category: QueryCategory = QueryCategory.FAQ,
    profile: RetrievalProfile = RetrievalProfile.FAST,
    used_fallback: bool = False,
) -> QueryDecision:
    return QueryDecision(category=category, profile=profile, used_fallback=used_fallback)


def retrieval_log_writer() -> SimpleNamespace:
    return SimpleNamespace(record=AsyncMock())


async def test_rag_service_builds_grounded_context_and_real_chunk_citations() -> None:
    retrieved = chunk()
    user_id = uuid4()
    decision = query_decision()
    embedding = SimpleNamespace(
        dense=AsyncMock(return_value=[[0.1, 0.2]]),
        sparse=AsyncMock(),
    )
    retriever = SimpleNamespace(
        search_dense=AsyncMock(return_value=[retrieved]),
        search_hybrid=AsyncMock(),
        close=AsyncMock(),
    )
    generator = SimpleNamespace(generate=AsyncMock(return_value="Employees receive 20 days."))
    classifier = SimpleNamespace(classify=AsyncMock(return_value=decision))
    query_log_writer = SimpleNamespace(record=AsyncMock(return_value=uuid4()))
    snapshot_writer = retrieval_log_writer()
    query_id = query_log_writer.record.return_value
    service = RagService(
        settings(),
        embedding,
        retriever,
        generator,
        classifier,
        query_log_writer,
        retrieval_log_writer=snapshot_writer,
    )

    response = await service.answer("How much annual leave is provided?", user_id, "HR")

    classifier.classify.assert_awaited_once_with("How much annual leave is provided?")
    retriever.search_dense.assert_awaited_once_with([0.1, 0.2], "HR", 3)
    retriever.search_hybrid.assert_not_awaited()
    embedding.sparse.assert_not_awaited()
    prompt_context = generator.generate.await_args.args[1]
    assert "[SOURCE 1]" in prompt_context
    assert "Filename: handbook.md" in prompt_context
    assert "Section: Annual Leave" in prompt_context
    assert retrieved.text in prompt_context
    assert response.insufficient_context is False
    assert response.sources[0].document_id == retrieved.document_id
    assert response.sources[0].chunk_id == retrieved.chunk_id
    assert response.query_intelligence.category == QueryCategory.FAQ
    assert response.query_intelligence.profile == RetrievalProfile.FAST
    assert response.query_intelligence.executed_strategy == ExecutedRetrievalStrategy.DENSE
    log_args = query_log_writer.record.await_args.args
    assert log_args[:4] == (
        user_id,
        "How much annual leave is provided?",
        decision,
        profile_config(RetrievalProfile.FAST),
    )
    assert isinstance(log_args[4], int)
    assert log_args[4] >= 0
    snapshot_writer.record.assert_awaited_once_with(
        query_id,
        [retrieved],
        {retrieved.chunk_id},
        ExecutedRetrievalStrategy.DENSE,
    )


async def test_rag_service_returns_deterministic_insufficient_context_without_llm() -> None:
    decision = query_decision(
        QueryCategory.SPECIFIC_SEARCH,
        RetrievalProfile.BALANCED,
        used_fallback=True,
    )
    sparse = SparseEmbedding(indices=[4], values=[0.7])
    embedding = SimpleNamespace(
        dense=AsyncMock(return_value=[[0.1, 0.2]]),
        sparse=AsyncMock(return_value=[sparse]),
    )
    retriever = SimpleNamespace(
        search_dense=AsyncMock(),
        search_hybrid=AsyncMock(return_value=[]),
        close=AsyncMock(),
    )
    generator = SimpleNamespace(generate=AsyncMock())
    classifier = SimpleNamespace(classify=AsyncMock(return_value=decision))
    query_log_writer = SimpleNamespace(record=AsyncMock(return_value=uuid4()))
    service = RagService(
        settings(),
        embedding,
        retriever,
        generator,
        classifier,
        query_log_writer,
        retrieval_log_writer=retrieval_log_writer(),
    )

    response = await service.answer("What is the moon office policy?", uuid4(), "Developer")

    assert response.answer == INSUFFICIENT_CONTEXT_ANSWER
    assert response.insufficient_context is True
    assert response.sources == []
    assert response.query_intelligence.profile == RetrievalProfile.BALANCED
    assert response.query_intelligence.candidate_top_k == 8
    assert response.query_intelligence.executed_strategy == (ExecutedRetrievalStrategy.HYBRID_RRF)
    assert response.query_intelligence.classification_fallback is True
    embedding.sparse.assert_awaited_once_with(["What is the moon office policy?"])
    retriever.search_dense.assert_not_awaited()
    retriever.search_hybrid.assert_awaited_once_with([0.1, 0.2], sparse, "Developer", 8)
    generator.generate.assert_not_awaited()


@pytest.mark.parametrize(
    ("category", "profile", "top_k", "strategy"),
    [
        (QueryCategory.FAQ, RetrievalProfile.FAST, 3, ExecutedRetrievalStrategy.DENSE),
        (
            QueryCategory.SPECIFIC_SEARCH,
            RetrievalProfile.BALANCED,
            8,
            ExecutedRetrievalStrategy.HYBRID_RRF,
        ),
        (
            QueryCategory.MULTI_DOC_COMPARISON,
            RetrievalProfile.ACCURATE,
            15,
            ExecutedRetrievalStrategy.HYBRID_RRF_RERANK,
        ),
    ],
)
async def test_rag_service_applies_profile_top_k_and_reports_actual_strategy(
    category: QueryCategory,
    profile: RetrievalProfile,
    top_k: int,
    strategy: ExecutedRetrievalStrategy,
) -> None:
    sparse = SparseEmbedding(indices=[4], values=[0.7])
    embedding = SimpleNamespace(
        dense=AsyncMock(return_value=[[0.1, 0.2]]),
        sparse=AsyncMock(return_value=[sparse]),
    )
    retriever = SimpleNamespace(
        search_dense=AsyncMock(return_value=[]),
        search_hybrid=AsyncMock(return_value=[]),
        close=AsyncMock(),
    )
    classifier = SimpleNamespace(classify=AsyncMock(return_value=query_decision(category, profile)))
    query_log_writer = SimpleNamespace(record=AsyncMock(return_value=uuid4()))
    reranker = SimpleNamespace(rerank=AsyncMock(return_value=[]))
    service = RagService(
        settings(),
        embedding,
        retriever,
        SimpleNamespace(generate=AsyncMock()),
        classifier,
        query_log_writer,
        reranker,
        retrieval_log_writer(),
    )

    response = await service.answer("Question", uuid4(), "Executive")

    if profile == RetrievalProfile.FAST:
        retriever.search_dense.assert_awaited_once_with([0.1, 0.2], "Executive", top_k)
        retriever.search_hybrid.assert_not_awaited()
        embedding.sparse.assert_not_awaited()
    else:
        embedding.sparse.assert_awaited_once_with(["Question"])
        retriever.search_dense.assert_not_awaited()
        retriever.search_hybrid.assert_awaited_once_with([0.1, 0.2], sparse, "Executive", top_k)
    if profile == RetrievalProfile.ACCURATE:
        reranker.rerank.assert_awaited_once_with("Question", [], 0)
    else:
        reranker.rerank.assert_not_awaited()
    assert response.query_intelligence.candidate_top_k == top_k
    assert response.query_intelligence.executed_strategy == strategy


async def test_accurate_reranking_limits_context_and_citations_to_final_five() -> None:
    candidates = [
        chunk(
            text=f"Authorized candidate passage {index}",
            filename=f"candidate-{index}.md",
            rank_before=index,
        )
        for index in range(1, 8)
    ]
    model = SimpleNamespace(rerank=lambda *_args, **_kwargs: [0.1, 0.9, 0.2, 0.8, 0.7, 0.6, 0.5])
    reranker = RerankerService(settings(), model)
    generator = SimpleNamespace(generate=AsyncMock(return_value="Grounded comparison"))
    snapshot_writer = retrieval_log_writer()
    service = RagService(
        settings(),
        SimpleNamespace(
            dense=AsyncMock(return_value=[[0.1, 0.2]]),
            sparse=AsyncMock(return_value=[SparseEmbedding(indices=[4], values=[0.7])]),
        ),
        SimpleNamespace(
            search_dense=AsyncMock(),
            search_hybrid=AsyncMock(return_value=candidates),
            close=AsyncMock(),
        ),
        generator,
        SimpleNamespace(
            classify=AsyncMock(
                return_value=query_decision(
                    QueryCategory.MULTI_DOC_COMPARISON,
                    RetrievalProfile.ACCURATE,
                )
            )
        ),
        SimpleNamespace(record=AsyncMock(return_value=uuid4())),
        reranker,
        snapshot_writer,
    )

    response = await service.answer("Compare the policies", uuid4(), "HR")

    assert [source.filename for source in response.sources] == [
        "candidate-2.md",
        "candidate-4.md",
        "candidate-5.md",
        "candidate-6.md",
        "candidate-7.md",
    ]
    context = generator.generate.await_args.args[1]
    assert "Authorized candidate passage 1" not in context
    assert "Authorized candidate passage 3" not in context
    assert context.count("[SOURCE ") == 5
    assert response.query_intelligence.executed_strategy == (
        ExecutedRetrievalStrategy.HYBRID_RRF_RERANK
    )
    persisted_candidates = snapshot_writer.record.await_args.args[1]
    included_ids = snapshot_writer.record.await_args.args[2]
    assert len(persisted_candidates) == 7
    assert {candidate.rank_after for candidate in persisted_candidates} == set(range(1, 8))
    assert len(included_ids) == 5
    assert candidates[0].chunk_id not in included_ids
    assert candidates[2].chunk_id not in included_ids


async def test_accurate_reranker_failure_returns_safe_error() -> None:
    service = RagService(
        settings(),
        SimpleNamespace(
            dense=AsyncMock(return_value=[[0.1, 0.2]]),
            sparse=AsyncMock(return_value=[SparseEmbedding(indices=[4], values=[0.7])]),
        ),
        SimpleNamespace(
            search_dense=AsyncMock(),
            search_hybrid=AsyncMock(return_value=[chunk(rank_before=1)]),
            close=AsyncMock(),
        ),
        SimpleNamespace(generate=AsyncMock()),
        SimpleNamespace(
            classify=AsyncMock(
                return_value=query_decision(
                    QueryCategory.MULTI_DOC_COMPARISON,
                    RetrievalProfile.ACCURATE,
                )
            )
        ),
        SimpleNamespace(record=AsyncMock(return_value=uuid4())),
        SimpleNamespace(rerank=AsyncMock(side_effect=RuntimeError("model unavailable"))),
    )

    with pytest.raises(HTTPException) as error:
        await service.answer("Compare the policies", uuid4(), "HR")

    assert error.value.status_code == 503
    assert error.value.detail["code"] == "RERANKING_FAILED"


@pytest.mark.parametrize(
    ("embedding_result", "retrieval_result", "generation_result", "expected_code"),
    [
        (RuntimeError("embedding unavailable"), [], "unused", "QUERY_EMBEDDING_FAILED"),
        ([[0.1, 0.2]], RuntimeError("qdrant unavailable"), "unused", "RETRIEVAL_FAILED"),
        ([[0.1, 0.2]], [chunk()], RuntimeError("openai unavailable"), "ANSWER_GENERATION_FAILED"),
    ],
)
async def test_rag_service_maps_provider_failures_to_safe_errors(
    embedding_result: object,
    retrieval_result: object,
    generation_result: object,
    expected_code: str,
) -> None:
    embedding = SimpleNamespace(
        dense=AsyncMock(
            side_effect=embedding_result if isinstance(embedding_result, Exception) else None,
            return_value=embedding_result,
        ),
        sparse=AsyncMock(),
    )
    retriever = SimpleNamespace(
        search_dense=AsyncMock(
            side_effect=retrieval_result if isinstance(retrieval_result, Exception) else None,
            return_value=retrieval_result,
        ),
        search_hybrid=AsyncMock(),
        close=AsyncMock(),
    )
    generator = SimpleNamespace(
        generate=AsyncMock(
            side_effect=generation_result if isinstance(generation_result, Exception) else None,
            return_value=generation_result,
        )
    )
    classifier = SimpleNamespace(classify=AsyncMock(return_value=query_decision()))
    query_log_writer = SimpleNamespace(record=AsyncMock(return_value=uuid4()))
    service = RagService(
        settings(),
        embedding,
        retriever,
        generator,
        classifier,
        query_log_writer,
        retrieval_log_writer=retrieval_log_writer(),
    )

    with pytest.raises(HTTPException) as error:
        await service.answer("Question", uuid4(), "HR")

    assert error.value.status_code == 503
    assert error.value.detail["code"] == expected_code


@pytest.mark.parametrize(
    ("sparse_result", "hybrid_result", "expected_code"),
    [
        (RuntimeError("bm25 unavailable"), [], "SPARSE_QUERY_FAILED"),
        (
            [SparseEmbedding(indices=[4], values=[0.7])],
            RuntimeError("fusion unavailable"),
            "HYBRID_RETRIEVAL_FAILED",
        ),
    ],
)
async def test_rag_service_maps_hybrid_failures_to_safe_errors(
    sparse_result: object,
    hybrid_result: object,
    expected_code: str,
) -> None:
    embedding = SimpleNamespace(
        dense=AsyncMock(return_value=[[0.1, 0.2]]),
        sparse=AsyncMock(
            side_effect=sparse_result if isinstance(sparse_result, Exception) else None,
            return_value=sparse_result,
        ),
    )
    retriever = SimpleNamespace(
        search_dense=AsyncMock(),
        search_hybrid=AsyncMock(
            side_effect=hybrid_result if isinstance(hybrid_result, Exception) else None,
            return_value=hybrid_result,
        ),
        close=AsyncMock(),
    )
    service = RagService(
        settings(),
        embedding,
        retriever,
        SimpleNamespace(generate=AsyncMock()),
        SimpleNamespace(
            classify=AsyncMock(
                return_value=query_decision(
                    QueryCategory.SPECIFIC_SEARCH, RetrievalProfile.BALANCED
                )
            )
        ),
        SimpleNamespace(record=AsyncMock(return_value=uuid4())),
        retrieval_log_writer=retrieval_log_writer(),
    )

    with pytest.raises(HTTPException) as error:
        await service.answer("Question", uuid4(), "HR")

    assert error.value.status_code == 503
    assert error.value.detail["code"] == expected_code


async def test_rag_service_maps_query_log_failure_to_safe_error() -> None:
    service = RagService(
        settings(),
        SimpleNamespace(dense=AsyncMock(return_value=[[0.1, 0.2]]), sparse=AsyncMock()),
        SimpleNamespace(
            search_dense=AsyncMock(return_value=[]),
            search_hybrid=AsyncMock(),
            close=AsyncMock(),
        ),
        SimpleNamespace(generate=AsyncMock()),
        SimpleNamespace(classify=AsyncMock(return_value=query_decision())),
        SimpleNamespace(record=AsyncMock(side_effect=RuntimeError("database unavailable"))),
    )

    with pytest.raises(HTTPException) as error:
        await service.answer("Question", uuid4(), "HR")

    assert error.value.status_code == 503
    assert error.value.detail["code"] == "QUERY_LOG_FAILED"


def test_context_builder_preserves_boundaries_and_respects_limit() -> None:
    first = chunk("First authorized source")
    second = chunk("Second source that should not fit")
    first_context, _ = build_context([first], 10000)

    context, included = build_context([first, second], len(first_context))

    assert context == first_context
    assert included == [first]


async def test_accurate_streaming_uses_shared_reranked_top_five_and_history() -> None:
    candidates = [chunk(f"Candidate {index}", f"candidate-{index}.md") for index in range(7)]
    reranked = candidates[1:6] + [candidates[0], candidates[6]]
    reranker = SimpleNamespace(rerank=AsyncMock(return_value=reranked))
    snapshot_writer = retrieval_log_writer()

    streamed_history: list[ConversationHistoryMessage] = []

    async def token_stream(
        _question: str,
        _context: str,
        received_history: list[ConversationHistoryMessage],
    ):
        streamed_history.extend(received_history)
        yield "Grounded comparison"

    generator = SimpleNamespace(generate=AsyncMock(), stream=token_stream)
    service = RagService(
        settings(),
        SimpleNamespace(
            dense=AsyncMock(return_value=[[0.1, 0.2]]),
            sparse=AsyncMock(return_value=[SparseEmbedding(indices=[4], values=[0.7])]),
        ),
        SimpleNamespace(
            search_dense=AsyncMock(),
            search_hybrid=AsyncMock(return_value=candidates),
            close=AsyncMock(),
        ),
        generator,
        SimpleNamespace(
            classify=AsyncMock(
                return_value=query_decision(
                    QueryCategory.MULTI_DOC_COMPARISON,
                    RetrievalProfile.ACCURATE,
                )
            )
        ),
        SimpleNamespace(record=AsyncMock(return_value=uuid4())),
        reranker,
        snapshot_writer,
    )
    history = [ConversationHistoryMessage(role="assistant", content="Earlier grounded answer")]

    prepared = await service.prepare("Compare the policies", uuid4(), "HR")
    tokens = [token async for token in service.stream(prepared, history)]

    reranker.rerank.assert_awaited_once_with("Compare the policies", candidates, 7)
    assert prepared.query_intelligence.executed_strategy == (
        ExecutedRetrievalStrategy.HYBRID_RRF_RERANK
    )
    assert len(prepared.sources) == 5
    assert tokens == ["Grounded comparison"]
    assert streamed_history == history
    persisted_candidates = snapshot_writer.record.await_args.args[1]
    assert persisted_candidates == reranked
    assert snapshot_writer.record.await_args.args[2] == {
        candidate.chunk_id for candidate in reranked[:5]
    }


async def test_retrieval_snapshot_failure_does_not_block_grounded_answer() -> None:
    retrieved = chunk()
    snapshot_writer = SimpleNamespace(
        record=AsyncMock(side_effect=RuntimeError("snapshot database unavailable"))
    )
    service = RagService(
        settings(),
        SimpleNamespace(dense=AsyncMock(return_value=[[0.1, 0.2]]), sparse=AsyncMock()),
        SimpleNamespace(
            search_dense=AsyncMock(return_value=[retrieved]),
            search_hybrid=AsyncMock(),
            close=AsyncMock(),
        ),
        SimpleNamespace(generate=AsyncMock(return_value="Grounded answer")),
        SimpleNamespace(classify=AsyncMock(return_value=query_decision())),
        SimpleNamespace(record=AsyncMock(return_value=uuid4())),
        retrieval_log_writer=snapshot_writer,
    )

    response = await service.answer("Question", uuid4(), "HR")

    assert response.answer == "Grounded answer"
    snapshot_writer.record.assert_awaited_once()
