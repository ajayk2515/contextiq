from contextlib import AbstractAsyncContextManager
from types import TracebackType
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from app.query_intelligence.domain import QueryCategory, QueryDecision, RetrievalProfile
from app.query_intelligence.models import QueryLog
from app.query_intelligence.persistence import QueryLogWriter
from app.query_intelligence.profiles import profile_config


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


async def test_query_log_writer_persists_routing_metadata() -> None:
    user_id = uuid4()
    query_id = uuid4()
    session = MagicMock()
    session.commit = AsyncMock()

    async def assign_query_id(item: QueryLog) -> None:
        item.id = query_id

    session.refresh = AsyncMock(side_effect=assign_query_id)
    decision = QueryDecision(
        category=QueryCategory.MULTI_DOC_COMPARISON,
        profile=RetrievalProfile.ACCURATE,
    )

    with patch(
        "app.query_intelligence.persistence.AsyncSessionFactory",
        return_value=SessionContext(session),
    ):
        persisted_id = await QueryLogWriter().record(
            user_id,
            "Compare the policies",
            decision,
            profile_config(RetrievalProfile.ACCURATE),
            24,
        )

    assert persisted_id == query_id
    item = session.add.call_args.args[0]
    assert isinstance(item, QueryLog)
    assert item.user_id == user_id
    assert item.query_text == "Compare the policies"
    assert item.query_category == "MULTI_DOC_COMPARISON"
    assert item.retrieval_profile == "ACCURATE"
    assert item.retrieval_strategy == "DENSE_FALLBACK"
    assert item.classifier_fallback is False
    assert item.retrieval_latency_ms == 24
    assert isinstance(item.id, UUID)
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(item)
