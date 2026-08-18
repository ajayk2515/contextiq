from contextlib import AbstractAsyncContextManager
from pathlib import Path
from types import TracebackType
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.documents.models import Document, DocumentStatus
from app.ingestion.embeddings import EmbeddingConfigurationError, SparseEmbedding
from app.ingestion.parser import ParsedChunk
from app.ingestion.service import (
    INTERRUPTED_PROCESSING_MESSAGE,
    process_document,
    recover_interrupted_documents,
)


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


def document() -> Document:
    return Document(
        id=uuid4(),
        filename="policy.md",
        file_hash="a" * 64,
        status=DocumentStatus.PROCESSING,
        uploaded_by=uuid4(),
        allowed_roles=["HR", "Executive"],
    )


async def test_startup_recovery_marks_only_processing_documents_failed() -> None:
    processing = document()
    processing.chunk_count = 3
    ready = document()
    ready.status = DocumentStatus.READY
    ready.chunk_count = 2
    failed = document()
    failed.status = DocumentStatus.FAILED
    failed.error_message = "Existing failure"
    result = MagicMock()
    result.scalars.return_value.all.return_value = [processing, ready, failed]
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()
    vector_index = MagicMock()
    vector_index.delete_document = AsyncMock()
    vector_index.close = AsyncMock()

    with (
        patch(
            "app.ingestion.service.AsyncSessionFactory",
            return_value=SessionContext(session),
        ),
        patch("app.ingestion.service.DocumentVectorIndex", return_value=vector_index),
    ):
        recovered = await recover_interrupted_documents()

    assert recovered == 1
    assert processing.status == DocumentStatus.FAILED
    assert processing.chunk_count == 0
    assert processing.error_message == INTERRUPTED_PROCESSING_MESSAGE
    assert ready.status == DocumentStatus.READY
    assert ready.chunk_count == 2
    assert ready.error_message is None
    assert failed.status == DocumentStatus.FAILED
    assert failed.error_message == "Existing failure"
    vector_index.delete_document.assert_awaited_once_with(processing.id)
    vector_index.close.assert_awaited_once()
    session.commit.assert_awaited_once()


async def test_startup_recovery_does_nothing_without_processing_documents() -> None:
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()

    with (
        patch(
            "app.ingestion.service.AsyncSessionFactory",
            return_value=SessionContext(session),
        ),
        patch("app.ingestion.service.DocumentVectorIndex") as vector_index,
    ):
        recovered = await recover_interrupted_documents()

    assert recovered == 0
    vector_index.assert_not_called()
    session.commit.assert_not_awaited()


def first_session(item: Document) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = item
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    return session


async def test_processing_transitions_document_to_ready(tmp_path: Path) -> None:
    item = document()
    path = tmp_path / "policy.md"
    path.write_text("# Policy")
    start_session = first_session(item)
    finish_session = MagicMock()
    finish_session.get = AsyncMock(return_value=item)
    finish_session.commit = AsyncMock()
    sessions = iter([SessionContext(start_session), SessionContext(finish_session)])
    vector_index = MagicMock()
    vector_index.replace_document = AsyncMock()
    vector_index.delete_document = AsyncMock()
    vector_index.close = AsyncMock()
    embedding_service = MagicMock()
    embedding_service.dense = AsyncMock(return_value=[[0.1, 0.2]])
    embedding_service.sparse = AsyncMock(return_value=[SparseEmbedding(indices=[1], values=[0.5])])

    with (
        patch("app.ingestion.service.AsyncSessionFactory", side_effect=lambda: next(sessions)),
        patch(
            "app.ingestion.service.parse_and_chunk",
            return_value=[ParsedChunk("Policy", "Policy", None, "a" * 64)],
        ),
        patch("app.ingestion.service.EmbeddingService", return_value=embedding_service),
        patch("app.ingestion.service.DocumentVectorIndex", return_value=vector_index),
    ):
        await process_document(item.id, str(path))

    assert item.status == DocumentStatus.READY
    assert item.chunk_count == 1
    assert item.error_message is None
    vector_index.replace_document.assert_awaited_once()
    finish_session.commit.assert_awaited_once()
    assert not path.exists()


async def test_processing_failure_is_persisted_and_vectors_are_cleaned(tmp_path: Path) -> None:
    item = document()
    path = tmp_path / "policy.md"
    path.write_text("# Policy")
    start_session = first_session(item)
    fail_session = MagicMock()
    fail_session.get = AsyncMock(return_value=item)
    fail_session.commit = AsyncMock()
    sessions = iter([SessionContext(start_session), SessionContext(fail_session)])
    vector_index = MagicMock()
    vector_index.delete_document = AsyncMock()
    vector_index.close = AsyncMock()
    embedding_service = MagicMock()
    embedding_service.dense = AsyncMock(
        side_effect=EmbeddingConfigurationError("OpenAI embeddings are not configured.")
    )
    embedding_service.sparse = AsyncMock(return_value=[SparseEmbedding(indices=[1], values=[0.5])])

    with (
        patch("app.ingestion.service.AsyncSessionFactory", side_effect=lambda: next(sessions)),
        patch(
            "app.ingestion.service.parse_and_chunk",
            return_value=[ParsedChunk("Policy", "Policy", None, "a" * 64)],
        ),
        patch("app.ingestion.service.EmbeddingService", return_value=embedding_service),
        patch("app.ingestion.service.DocumentVectorIndex", return_value=vector_index),
    ):
        await process_document(item.id, str(path))

    assert item.status == DocumentStatus.FAILED
    assert item.chunk_count == 0
    assert item.error_message == "OpenAI embeddings are not configured."
    vector_index.delete_document.assert_awaited_once_with(item.id)
    fail_session.commit.assert_awaited_once()
    assert not path.exists()


async def test_failure_status_persists_when_vector_cleanup_is_unavailable(tmp_path: Path) -> None:
    item = document()
    path = tmp_path / "policy.md"
    path.write_text("# Policy")
    start_session = first_session(item)
    fail_session = MagicMock()
    fail_session.get = AsyncMock(return_value=item)
    fail_session.commit = AsyncMock()
    sessions = iter([SessionContext(start_session), SessionContext(fail_session)])
    vector_index = MagicMock()
    vector_index.delete_document = AsyncMock(side_effect=ConnectionError("Qdrant unavailable"))
    vector_index.close = AsyncMock()
    embedding_service = MagicMock()
    embedding_service.dense = AsyncMock(
        side_effect=EmbeddingConfigurationError("OpenAI embeddings are not configured.")
    )
    embedding_service.sparse = AsyncMock(return_value=[SparseEmbedding(indices=[1], values=[0.5])])

    with (
        patch("app.ingestion.service.AsyncSessionFactory", side_effect=lambda: next(sessions)),
        patch(
            "app.ingestion.service.parse_and_chunk",
            return_value=[ParsedChunk("Policy", "Policy", None, "a" * 64)],
        ),
        patch("app.ingestion.service.EmbeddingService", return_value=embedding_service),
        patch("app.ingestion.service.DocumentVectorIndex", return_value=vector_index),
    ):
        await process_document(item.id, str(path))

    assert item.status == DocumentStatus.FAILED
    assert item.error_message == "OpenAI embeddings are not configured."
    fail_session.commit.assert_awaited_once()
