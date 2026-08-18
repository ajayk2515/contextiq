from collections.abc import AsyncIterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.conversations.models import Conversation, Message, MessageRole
from app.database import get_session
from app.main import app


def user(email: str = "developer@demo.com") -> User:
    return User(id=uuid4(), email=email, password_hash="unused", role="Developer")


async def request(method: str, path: str, current_user: User, session: AsyncSession):
    async def override_user() -> User:
        return current_user

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_session] = override_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.request(method, path)
    finally:
        app.dependency_overrides.clear()


async def test_create_and_list_only_authenticated_users_conversations() -> None:
    current_user = user()
    other_user = user("hr@demo.com")
    now = datetime.now(UTC)
    own = Conversation(
        id=uuid4(),
        user_id=current_user.id,
        title="Own conversation",
        created_at=now,
        updated_at=now,
    )
    session = AsyncMock(spec=AsyncSession)

    async def refresh_created(conversation: Conversation) -> None:
        conversation.id = uuid4()
        conversation.created_at = now
        conversation.updated_at = now

    list_result = MagicMock()
    list_result.scalars.return_value.all.return_value = [own]
    session.refresh.side_effect = refresh_created
    session.execute.return_value = list_result

    created = await request("POST", "/api/conversations", current_user, session)
    listed = await request("GET", "/api/conversations", current_user, session)

    assert created.status_code == 201
    assert created.json()["title"] == "New conversation"
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [str(own.id)]
    created_model = session.add.call_args.args[0]
    assert isinstance(created_model, Conversation)
    assert created_model.user_id == current_user.id
    assert created_model.user_id != other_user.id


async def test_loads_owned_messages_chronologically_with_persisted_sources() -> None:
    current_user = user()
    now = datetime.now(UTC)
    conversation = Conversation(
        id=uuid4(),
        user_id=current_user.id,
        title="Leave policy",
        created_at=now,
        updated_at=now,
    )
    source = {
        "document_id": str(uuid4()),
        "chunk_id": str(uuid4()),
        "filename": "policy.md",
        "page": None,
        "section": "Leave",
        "snippet": "Sixteen weeks of leave.",
    }
    messages = [
        Message(
            id=uuid4(),
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content="What is the leave duration?",
            sources=[],
            insufficient_context=False,
            created_at=now,
        ),
        Message(
            id=uuid4(),
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content="Sixteen weeks.",
            sources=[source],
            insufficient_context=False,
            created_at=now,
        ),
    ]
    owned_result = MagicMock()
    owned_result.scalar_one_or_none.return_value = conversation
    messages_result = MagicMock()
    messages_result.all.return_value = [(message, None) for message in messages]
    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = [owned_result, messages_result]

    response = await request("GET", f"/api/conversations/{conversation.id}", current_user, session)

    assert response.status_code == 200
    payload = response.json()
    assert [message["role"] for message in payload["messages"]] == ["USER", "ASSISTANT"]
    assert payload["messages"][1]["sources"][0]["filename"] == "policy.md"


async def test_cross_user_detail_and_delete_are_safe_not_found() -> None:
    current_user = user()
    conversation_id = uuid4()
    missing_result = MagicMock()
    missing_result.scalar_one_or_none.return_value = None
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = missing_result

    detail = await request("GET", f"/api/conversations/{conversation_id}", current_user, session)
    deleted = await request(
        "DELETE", f"/api/conversations/{conversation_id}", current_user, session
    )

    assert detail.status_code == deleted.status_code == 404
    assert detail.json()["detail"]["code"] == "CONVERSATION_NOT_FOUND"
    assert deleted.json()["detail"]["code"] == "CONVERSATION_NOT_FOUND"
    session.delete.assert_not_awaited()


async def test_delete_owned_conversation_uses_database_cascade() -> None:
    current_user = user()
    conversation = Conversation(id=uuid4(), user_id=current_user.id, title="Delete me")
    owned_result = MagicMock()
    owned_result.scalar_one_or_none.return_value = conversation
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = owned_result

    response = await request(
        "DELETE", f"/api/conversations/{conversation.id}", current_user, session
    )

    assert response.status_code == 204
    session.delete.assert_awaited_once_with(conversation)
    session.commit.assert_awaited_once()
