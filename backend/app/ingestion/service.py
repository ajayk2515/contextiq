import asyncio
import logging
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select

from app.config import get_settings
from app.database import AsyncSessionFactory
from app.documents.models import Document, DocumentStatus
from app.ingestion.embeddings import EmbeddingService
from app.ingestion.parser import parse_and_chunk
from app.ingestion.vector_index import DocumentVectorIndex, IndexedChunk

logger = logging.getLogger(__name__)


def _safe_failure_message(error: Exception) -> str:
    if isinstance(error, ValueError | RuntimeError):
        return str(error)[:1000]
    return "Document processing failed. Check the server logs for details."


async def _set_failed(document_id: UUID, error: Exception) -> None:
    async with AsyncSessionFactory() as session:
        document = await session.get(Document, document_id)
        if document is None:
            return
        document.status = DocumentStatus.FAILED
        document.chunk_count = 0
        document.error_message = _safe_failure_message(error)
        await session.commit()


async def process_document(document_id: UUID, temporary_path: str) -> None:
    settings = get_settings()
    path = Path(temporary_path)
    vector_index = DocumentVectorIndex(settings)
    try:
        async with AsyncSessionFactory() as session:
            result = await session.execute(select(Document).where(Document.id == document_id))
            document = result.scalar_one_or_none()
            if document is None:
                return
            filename = document.filename
            allowed_roles = list(document.allowed_roles)

        parsed = await asyncio.to_thread(
            parse_and_chunk,
            path,
            settings.chunk_size,
            settings.chunk_overlap,
        )
        texts = [chunk.text for chunk in parsed]
        embedding_service = EmbeddingService(settings)
        dense_vectors, sparse_vectors = await asyncio.gather(
            embedding_service.dense(texts),
            embedding_service.sparse(texts),
        )
        indexed = [IndexedChunk(id=uuid4(), parsed=chunk) for chunk in parsed]
        await vector_index.replace_document(
            document_id,
            filename,
            allowed_roles,
            indexed,
            dense_vectors,
            sparse_vectors,
        )

        async with AsyncSessionFactory() as session:
            document = await session.get(Document, document_id)
            if document is None:
                await vector_index.delete_document(document_id)
                return
            document.status = DocumentStatus.READY
            document.chunk_count = len(indexed)
            document.error_message = None
            await session.commit()
    except Exception as error:
        logger.exception("Document ingestion failed for %s", document_id)
        try:
            await vector_index.delete_document(document_id)
        except Exception:
            logger.exception("Could not clean vectors for failed document %s", document_id)
        await _set_failed(document_id, error)
    finally:
        await vector_index.close()
        await asyncio.to_thread(path.unlink, missing_ok=True)
