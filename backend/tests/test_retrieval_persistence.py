from contextlib import AbstractAsyncContextManager
from types import TracebackType
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.query_intelligence.domain import ExecutedRetrievalStrategy
from app.query_intelligence.models import RetrievalLog
from app.query_intelligence.retrieval_persistence import (
    SNIPPET_MAX_CHARACTERS,
    RetrievalLogWriter,
)
from app.rag.retrieval import RetrievedChunk


class SessionContext(AbstractAsyncContextManager[MagicMock]):
    def __init__(self, session: MagicMock) -> None:
        self.session = session

    async def __aenter__(self) -> MagicMock:
        return self.session

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


def candidate() -> RetrievedChunk:
    return RetrievedChunk(
        document_id=uuid4(),
        chunk_id=uuid4(),
        filename="hr-policy.pdf",
        page=4,
        section="Retention",
        text="  Confidential   retention details.  " + "x" * 600,
        allowed_roles=("HR", "Executive"),
        score=0.91,
        rank_before=2,
        rrf_score=0.027,
        reranker_score=0.82,
        rank_after=1,
    )


async def test_writer_persists_immutable_candidate_snapshot() -> None:
    query_id = uuid4()
    retrieved = candidate()
    session = MagicMock()
    session.commit = AsyncMock()

    with patch(
        "app.query_intelligence.retrieval_persistence.AsyncSessionFactory",
        return_value=SessionContext(session),
    ):
        await RetrievalLogWriter().record(
            query_id,
            [retrieved],
            {retrieved.chunk_id},
            ExecutedRetrievalStrategy.HYBRID_RRF_RERANK,
        )

    persisted = session.add_all.call_args.args[0][0]
    assert isinstance(persisted, RetrievalLog)
    assert persisted.query_id == query_id
    assert persisted.document_id == retrieved.document_id
    assert persisted.chunk_id == retrieved.chunk_id
    assert persisted.filename == "hr-policy.pdf"
    assert persisted.page == 4
    assert persisted.section == "Retention"
    assert len(persisted.snippet) == SNIPPET_MAX_CHARACTERS
    assert "  " not in persisted.snippet
    assert persisted.rank_before == 2
    assert persisted.rank_after == 1
    assert persisted.retrieval_score is None
    assert persisted.rrf_score == 0.027
    assert persisted.reranker_score == 0.82
    assert persisted.included_in_context is True
    session.commit.assert_awaited_once()


async def test_dense_writer_exposes_dense_score_and_context_exclusion() -> None:
    retrieved = candidate()
    session = MagicMock()
    session.commit = AsyncMock()

    with patch(
        "app.query_intelligence.retrieval_persistence.AsyncSessionFactory",
        return_value=SessionContext(session),
    ):
        await RetrievalLogWriter().record(
            uuid4(),
            [retrieved],
            set(),
            ExecutedRetrievalStrategy.DENSE,
        )

    persisted = session.add_all.call_args.args[0][0]
    assert persisted.retrieval_score == 0.91
    assert persisted.rrf_score == 0.027
    assert persisted.included_in_context is False


async def test_balanced_writer_exposes_rrf_without_dense_or_reranker_scores() -> None:
    retrieved = candidate()
    retrieved = RetrievedChunk(
        document_id=retrieved.document_id,
        chunk_id=retrieved.chunk_id,
        filename=retrieved.filename,
        page=retrieved.page,
        section=retrieved.section,
        text=retrieved.text,
        allowed_roles=retrieved.allowed_roles,
        score=retrieved.score,
        rank_before=retrieved.rank_before,
        rrf_score=retrieved.rrf_score,
    )
    session = MagicMock()
    session.commit = AsyncMock()

    with patch(
        "app.query_intelligence.retrieval_persistence.AsyncSessionFactory",
        return_value=SessionContext(session),
    ):
        await RetrievalLogWriter().record(
            uuid4(),
            [retrieved],
            {retrieved.chunk_id},
            ExecutedRetrievalStrategy.HYBRID_RRF,
        )

    persisted = session.add_all.call_args.args[0][0]
    assert persisted.retrieval_score is None
    assert persisted.rrf_score == 0.027
    assert persisted.reranker_score is None
    assert persisted.rank_after is None


async def test_writer_skips_database_session_when_there_are_no_candidates() -> None:
    with patch(
        "app.query_intelligence.retrieval_persistence.AsyncSessionFactory"
    ) as session_factory:
        await RetrievalLogWriter().record(
            uuid4(),
            [],
            set(),
            ExecutedRetrievalStrategy.HYBRID_RRF,
        )

    session_factory.assert_not_called()
