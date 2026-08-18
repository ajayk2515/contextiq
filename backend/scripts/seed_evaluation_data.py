import asyncio

from app.config import get_settings
from app.database import close_database
from app.evaluations.demo_data import EVALUATION_DOCUMENTS, seed_evaluation_data


async def main() -> None:
    try:
        seeded, unchanged = await seed_evaluation_data(get_settings())
    finally:
        await close_database()
    print(f"Evaluation corpus ready: {seeded} ingested, {unchanged} unchanged.")
    for document in EVALUATION_DOCUMENTS:
        print(f"- {document.filename}")


if __name__ == "__main__":
    asyncio.run(main())
