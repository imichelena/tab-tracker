"""Create transaction tables on PG."""
import asyncio
from database import engine, Base
from models import Transaction, TransactionItem  # noqa
import models  # ensure all models loaded

async def run():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Tables created successfully")

asyncio.run(run())
