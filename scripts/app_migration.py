import asyncio
import os
import sys
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from argon2 import PasswordHasher

# Add src to path to import license_server
sys.path.append(os.path.join(os.getcwd(), "src"))

from license_server.config import settings

ph = PasswordHasher()

async def migrate():
    print("Starting Multi-App migration...")
    
    # 'routellm' legacy key (optional)
    route_llm_key = settings.ROUTELLM_APP_KEY

    # Ensure we use the asyncpg driver
    db_url = settings.DATABASE_URL
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
        
    engine = create_async_engine(db_url)
    
    async with engine.begin() as conn:
        # 1. Create apps table
        print("Creating 'apps' table...")
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS apps (
                slug VARCHAR PRIMARY KEY,
                name VARCHAR NOT NULL,
                api_key_hash VARCHAR NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
            );
        """))

        # 2. Seed 'routellm' app (Optional — only if ROUTELLM_APP_KEY is set)
        if route_llm_key:
            print("Seeding legacy 'routellm' app...")
            routellm_hash = ph.hash(route_llm_key)
            await conn.execute(text("""
                INSERT INTO apps (slug, name, api_key_hash)
                VALUES (:slug, :name, :api_key_hash)
                ON CONFLICT (slug) DO NOTHING;
            """), {"slug": "routellm", "name": "RouteLLM", "api_key_hash": routellm_hash})
        else:
            print("No ROUTELLM_APP_KEY set. Skipping routellm seeding.")

        # 3. Add app_id column to existing tables
        tables = ["licenses", "verification_requests"]
        for table in tables:
            print(f"Checking '{table}' for app_id...")
            result = await conn.execute(text(f"SELECT column_name FROM information_schema.columns WHERE table_name='{table}' AND column_name='app_id'"))
            if not result.scalars().first():
                print(f"Adding 'app_id' to '{table}'...")
                await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN app_id VARCHAR"))

        # 4. Check for orphaned records (NULL app_id) — fail loudly
        for table in tables:
            result = await conn.execute(text(f"SELECT COUNT(*) FROM {table} WHERE app_id IS NULL"))
            null_count = result.scalar()
            if null_count > 0:
                raise RuntimeError(
                    f"Found {null_count} records in '{table}' with NULL app_id. "
                    f"Create an app first via POST /admin/apps, then run:\n"
                    f"  UPDATE {table} SET app_id = 'your-app-slug' WHERE app_id IS NULL"
                )
            
            # Make columns NOT NULL
            print(f"Setting 'app_id' to NOT NULL in '{table}'...")
            await conn.execute(text(f"ALTER TABLE {table} ALTER COLUMN app_id SET NOT NULL"))

        # 5. Add Constraints
        print("Adding Foreign Key and Unique constraints...")
        
        # Licenses
        await conn.execute(text("ALTER TABLE licenses DROP CONSTRAINT IF EXISTS licenses_app_id_fkey"))
        await conn.execute(text("ALTER TABLE licenses ADD CONSTRAINT licenses_app_id_fkey FOREIGN KEY (app_id) REFERENCES apps(slug) ON DELETE RESTRICT"))
        
        await conn.execute(text("ALTER TABLE licenses DROP CONSTRAINT IF EXISTS licenses_email_app_id_key"))
        await conn.execute(text("ALTER TABLE licenses ADD CONSTRAINT licenses_email_app_id_key UNIQUE (email, app_id)"))

        # Verification Requests
        await conn.execute(text("ALTER TABLE verification_requests DROP CONSTRAINT IF EXISTS verification_requests_app_id_fkey"))
        await conn.execute(text("ALTER TABLE verification_requests ADD CONSTRAINT verification_requests_app_id_fkey FOREIGN KEY (app_id) REFERENCES apps(slug) ON DELETE CASCADE"))
        
        await conn.execute(text("ALTER TABLE verification_requests DROP CONSTRAINT IF EXISTS verification_requests_email_app_id_key"))
        await conn.execute(text("ALTER TABLE verification_requests ADD CONSTRAINT verification_requests_email_app_id_key UNIQUE (email, app_id)"))

    print("Migration successful!")
    print("\nNext steps:")
    print("  1. Create your first app: POST /admin/apps")
    print("  2. Save the returned API key securely")

if __name__ == "__main__":
    asyncio.run(migrate())
