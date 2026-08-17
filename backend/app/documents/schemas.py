from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.auth.models import UserRole
from app.documents.models import DocumentStatus


class DocumentUploader(BaseModel):
    id: UUID
    email: str


class DocumentResponse(BaseModel):
    id: UUID
    filename: str
    file_hash: str
    status: DocumentStatus
    allowed_roles: list[UserRole]
    chunk_count: int
    error_message: str | None
    uploader: DocumentUploader
    created_at: datetime
    updated_at: datetime
