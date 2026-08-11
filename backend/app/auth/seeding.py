from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User, UserRole
from app.auth.security import hash_password


@dataclass(frozen=True)
class DemoUser:
    email: str
    role: UserRole


DEMO_USERS = (
    DemoUser("developer@demo.com", UserRole.DEVELOPER),
    DemoUser("hr@demo.com", UserRole.HR),
    DemoUser("finance@demo.com", UserRole.FINANCE),
    DemoUser("executive@demo.com", UserRole.EXECUTIVE),
)


async def seed_demo_users(session: AsyncSession, password: str) -> None:
    for demo_user in DEMO_USERS:
        result = await session.execute(select(User).where(User.email == demo_user.email))
        user = result.scalar_one_or_none()
        encoded_password = hash_password(password)
        if user is None:
            session.add(
                User(
                    email=demo_user.email,
                    password_hash=encoded_password,
                    role=demo_user.role.value,
                )
            )
        else:
            user.password_hash = encoded_password
            user.role = demo_user.role.value
    await session.commit()
