import hashlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.database import get_session
from app.documents.models import Document, DocumentStatus
from app.main import app


def user(email: str = "hr@demo.com") -> User:
    return User(id=uuid4(), email=email, password_hash="unused", role="HR")


async def request(
    method: str,
    url: str,
    current_user: User,
    session: AsyncSession,
    **kwargs: Any,
) -> Response:
    async def override_user() -> User:
        return current_user

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_session] = override_session
    try:
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, url, **kwargs)
    finally:
        app.dependency_overrides.clear()


def session_mock() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


async def test_documents_reject_missing_authentication() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/documents")

    assert response.status_code == 401


async def test_upload_validates_type_and_empty_file() -> None:
    current_user = user()
    session = session_mock()
    unsupported = await request(
        "POST",
        "/api/documents",
        current_user,
        session,
        files={"file": ("notes.txt", b"content", "text/plain")},
        data={"allowed_roles": "HR"},
    )
    empty = await request(
        "POST",
        "/api/documents",
        current_user,
        session,
        files={"file": ("notes.md", b"", "text/markdown")},
        data={"allowed_roles": "HR"},
    )

    assert unsupported.status_code == 415
    assert unsupported.json()["detail"]["code"] == "UNSUPPORTED_FILE_TYPE"
    assert empty.status_code == 400
    assert empty.json()["detail"]["code"] == "EMPTY_FILE"


async def test_upload_rejects_file_over_configured_limit() -> None:
    current_user = user()
    session = session_mock()
    configured = SimpleNamespace(max_upload_size_mb=1)
    with patch("app.documents.router.get_settings", return_value=configured):
        response = await request(
            "POST",
            "/api/documents",
            current_user,
            session,
            files={"file": ("policy.md", b"x" * (1024 * 1024 + 1), "text/markdown")},
            data={"allowed_roles": "HR"},
        )

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "FILE_TOO_LARGE"


async def test_upload_sanitizes_filename_hashes_file_and_starts_background_task() -> None:
    current_user = user()
    session = session_mock()

    async def refresh(document: Document) -> None:
        now = datetime.now(UTC)
        document.id = uuid4()
        document.chunk_count = 0
        document.created_at = now
        document.updated_at = now

    async def finish_background(_document_id: object, temporary_path: str) -> None:
        del temporary_path

    session.refresh.side_effect = refresh
    background = AsyncMock(side_effect=finish_background)
    with patch("app.documents.router.process_document", background):
        response = await request(
            "POST",
            "/api/documents",
            current_user,
            session,
            files={"file": ("../policy.md", b"# Policy", "text/markdown")},
            data={"allowed_roles": ["HR", "Executive"]},
        )

    assert response.status_code == 202
    payload = response.json()
    assert payload["filename"] == "policy.md"
    assert payload["status"] == "PROCESSING"
    assert payload["allowed_roles"] == ["HR", "Executive"]
    assert payload["file_hash"] == hashlib.sha256(b"# Policy").hexdigest()
    background.assert_awaited_once()


async def test_list_and_detail_return_metadata_without_chunk_text() -> None:
    current_user = user()
    document = Document(
        id=uuid4(),
        filename="policy.md",
        file_hash="a" * 64,
        status=DocumentStatus.READY,
        uploaded_by=current_user.id,
        allowed_roles=["HR"],
        chunk_count=2,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    list_result = MagicMock()
    list_result.all.return_value = [(document, current_user)]
    detail_result = MagicMock()
    detail_result.one_or_none.return_value = (document, current_user)
    session = session_mock()
    session.execute.side_effect = [list_result, detail_result]

    listed = await request("GET", "/api/documents", current_user, session)
    detailed = await request("GET", f"/api/documents/{document.id}", current_user, session)

    assert listed.status_code == detailed.status_code == 200
    assert listed.json()[0]["chunk_count"] == 2
    assert "text" not in detailed.json()


async def test_only_uploader_can_delete_document() -> None:
    uploader = user("uploader@demo.com")
    other_user = user("other@demo.com")
    document = Document(
        id=uuid4(),
        filename="policy.md",
        file_hash="a" * 64,
        status=DocumentStatus.READY,
        uploaded_by=uploader.id,
        allowed_roles=["HR"],
    )
    session = session_mock()
    session.get.return_value = document
    with patch("app.documents.router.DocumentVectorIndex") as vector_index:
        response = await request("DELETE", f"/api/documents/{document.id}", other_user, session)

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "DOCUMENT_DELETE_FORBIDDEN"
    vector_index.assert_not_called()
    session.delete.assert_not_awaited()


async def test_uploader_delete_removes_vectors_and_metadata() -> None:
    uploader = user("uploader@demo.com")
    document = Document(
        id=uuid4(),
        filename="policy.md",
        file_hash="a" * 64,
        status=DocumentStatus.READY,
        uploaded_by=uploader.id,
        allowed_roles=["HR"],
    )
    session = session_mock()
    session.get.return_value = document
    index = MagicMock()
    index.delete_document = AsyncMock()
    index.close = AsyncMock()
    with patch("app.documents.router.DocumentVectorIndex", return_value=index):
        response = await request("DELETE", f"/api/documents/{document.id}", uploader, session)

    assert response.status_code == 204
    index.delete_document.assert_awaited_once_with(document.id)
    session.delete.assert_awaited_once_with(document)
    session.commit.assert_awaited_once()
