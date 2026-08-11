from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.errors import raise_unauthorized
from app.auth.models import User
from app.auth.security import InvalidAccessTokenError, decode_access_token
from app.database import get_session

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise_unauthorized()

    try:
        claims = decode_access_token(credentials.credentials)
    except InvalidAccessTokenError:
        raise_unauthorized()

    result = await session.execute(select(User).where(User.id == claims.sub))
    user = result.scalar_one_or_none()
    if user is None:
        raise_unauthorized()

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
