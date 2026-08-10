import asyncio

from .db import close_db, init_db


async def main() -> None:
    try:
        await init_db()
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
