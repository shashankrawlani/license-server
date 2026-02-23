
import asyncio
import os
import sys

# Add src to path
sys.path.append(os.path.join(os.getcwd(), "src"))

from license_server.database import SQLModel, engine
from license_server.models import * # Ensure all models are loaded

async def reset():
    print("Dropping tables for license_server...")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        print("Creating tables for license_server...")
        await conn.run_sync(SQLModel.metadata.create_all)
    print("Reset complete.")

if __name__ == "__main__":
    asyncio.run(reset())
