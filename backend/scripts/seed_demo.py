import asyncio

from app.auth.seeding import DEMO_USERS, seed_demo_users
from app.config import get_settings
from app.database import AsyncSessionFactory, close_database


async def main() -> None:
    settings = get_settings()
    if settings.demo_user_password is None:
        raise SystemExit("DEMO_USER_PASSWORD must be configured before seeding demo users.")

    async with AsyncSessionFactory() as session:
        await seed_demo_users(session, settings.demo_user_password.get_secret_value())
    await close_database()

    print(f"Seeded {len(DEMO_USERS)} demo users.")
    for user in DEMO_USERS:
        print(f"- {user.email} ({user.role.value})")


if __name__ == "__main__":
    asyncio.run(main())
