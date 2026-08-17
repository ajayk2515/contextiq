import asyncio
import hashlib
import logging
import tempfile
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser
from app.auth.models import User, UserRole
from app.config import get_settings
from app.database import get_session
from app.documents.errors import (
    raise_delete_forbidden,
    raise_document_error,
    raise_document_not_found,
)
from app.documents.models import Document, DocumentStatus
from app.documents.schemas import DocumentResponse, DocumentUploader
from app.ingestion.service import process_document
from app.ingestion.vector_index import DocumentVectorIndex

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["documents"])

SUPPORTED_TYPES = {
    ".pdf": {"application/pdf"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    ".pptx": {"application/vnd.openxmlformats-officedocument.presentationml.presentation"},
    ".md": {"text/markdown", "text/plain"},
    ".markdown": {"text/markdown", "text/plain"},
}
GENERIC_CONTENT_TYPES = {"application/octet-stream", "binary/octet-stream"}


def _safe_filename(raw_filename: str | None) -> str:
    filename = (raw_filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not filename or "\x00" in filename or len(filename) > 255:
        raise_document_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_FILENAME",
            "The uploaded file must have a valid filename of at most 255 characters.",
        )
    return filename


def _validate_file_type(filename: str, content_type: str | None) -> str:
    extension = Path(filename).suffix.lower()
    expected_types = SUPPORTED_TYPES.get(extension)
    if expected_types is None:
        raise_document_error(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "UNSUPPORTED_FILE_TYPE",
            "Supported file types are PDF, DOCX, PPTX, and Markdown.",
        )
    if content_type and content_type not in expected_types | GENERIC_CONTENT_TYPES:
        raise_document_error(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "UNSUPPORTED_FILE_TYPE",
            "The file content type does not match its supported extension.",
        )
    return ".md" if extension == ".markdown" else extension


def _document_response(document: Document, uploader: User) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        filename=document.filename,
        file_hash=document.file_hash,
        status=DocumentStatus(document.status),
        allowed_roles=[UserRole(role) for role in document.allowed_roles],
        chunk_count=document.chunk_count,
        error_message=document.error_message,
        uploader=DocumentUploader(id=uploader.id, email=uploader.email),
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


async def _write_temporary_file(file: UploadFile, extension: str) -> tuple[str, str]:
    settings = get_settings()
    maximum_bytes = settings.max_upload_size_mb * 1024 * 1024
    byte_count = 0
    digest = hashlib.sha256()
    temporary = tempfile.NamedTemporaryFile(prefix="ekip_", suffix=extension, delete=False)
    path = temporary.name
    try:
        while content := await file.read(1024 * 1024):
            byte_count += len(content)
            if byte_count > maximum_bytes:
                raise_document_error(
                    status.HTTP_413_CONTENT_TOO_LARGE,
                    "FILE_TOO_LARGE",
                    f"The file exceeds the {settings.max_upload_size_mb} MB upload limit.",
                )
            digest.update(content)
            temporary.write(content)
    except Exception:
        temporary.close()
        await asyncio.to_thread(Path(path).unlink, missing_ok=True)
        raise
    finally:
        temporary.close()
        await file.close()

    if byte_count == 0:
        await asyncio.to_thread(Path(path).unlink, missing_ok=True)
        raise_document_error(
            status.HTTP_400_BAD_REQUEST,
            "EMPTY_FILE",
            "The uploaded file is empty.",
        )
    return path, digest.hexdigest()


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
    session: Annotated[AsyncSession, Depends(get_session)],
    file: Annotated[UploadFile, File()],
    allowed_roles: Annotated[list[UserRole], Form()],
) -> DocumentResponse:
    filename = _safe_filename(file.filename)
    extension = _validate_file_type(filename, file.content_type)
    roles = list(dict.fromkeys(role.value for role in allowed_roles))
    if not roles:
        raise_document_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "ROLES_REQUIRED",
            "Select at least one allowed role.",
        )
    temporary_path, file_hash = await _write_temporary_file(file, extension)
    document = Document(
        filename=filename,
        file_hash=file_hash,
        status=DocumentStatus.PROCESSING,
        uploaded_by=current_user.id,
        allowed_roles=roles,
    )
    try:
        session.add(document)
        await session.commit()
        await session.refresh(document)
    except Exception:
        await asyncio.to_thread(Path(temporary_path).unlink, missing_ok=True)
        raise

    background_tasks.add_task(process_document, document.id, temporary_path)
    return _document_response(document, current_user)


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    _current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[DocumentResponse]:
    result = await session.execute(
        select(Document, User)
        .join(User, User.id == Document.uploaded_by)
        .order_by(Document.created_at.desc())
    )
    return [_document_response(document, uploader) for document, uploader in result.all()]


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    _current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DocumentResponse:
    result = await session.execute(
        select(Document, User)
        .join(User, User.id == Document.uploaded_by)
        .where(Document.id == document_id)
    )
    record = result.one_or_none()
    if record is None:
        raise_document_not_found()
    return _document_response(record[0], record[1])


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    document = await session.get(Document, document_id)
    if document is None:
        raise_document_not_found()
    if document.uploaded_by != current_user.id:
        raise_delete_forbidden()

    vector_index = DocumentVectorIndex(get_settings())
    try:
        await vector_index.delete_document(document_id)
    except Exception:
        logger.exception("Could not delete Qdrant vectors for document %s", document_id)
        raise_document_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "DOCUMENT_DELETE_FAILED",
            "The document could not be deleted while vector storage is unavailable.",
        )
    finally:
        await vector_index.close()

    await session.delete(document)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
