import argparse
import asyncio
from uuid import UUID

from app.database import close_database
from app.optimization.service import generate_recommendations


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate deterministic recommendations for one completed evaluation run."
    )
    parser.add_argument("run_id", type=UUID)
    return parser.parse_args()


async def main(run_id: UUID) -> None:
    try:
        recommendations = await generate_recommendations(run_id)
    finally:
        await close_database()
    print(f"Generated {len(recommendations)} recommendations for evaluation run {run_id}.")


if __name__ == "__main__":
    asyncio.run(main(_arguments().run_id))
