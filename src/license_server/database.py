from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlmodel import SQLModel
from .config import settings

def normalize_db_url(url: str) -> str:
    """Normalizes database URL for async drivers.

    Supports:
    - PostgreSQL: postgresql:// -> postgresql+asyncpg://
    - SQLite: sqlite:// -> sqlite+aiosqlite://

    Args:
        url: The raw database connection URL.

    Returns:
        str: The normalized async-compatible connection URL.

    Raises:
        ValueError: If the URL scheme is not supported.
    """
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("sqlite://"):
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    if url.startswith(("postgresql+asyncpg://", "sqlite+aiosqlite://")):
        return url
    raise ValueError(f"Unsupported DATABASE_URL scheme: {url.split('://')[0] if '://' in url else url}")

db_url = normalize_db_url(settings.DATABASE_URL)

# SQLite-specific config
connect_args = {}
if db_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_async_engine(
    db_url,
    pool_size=5 if not db_url.startswith("sqlite") else 0,
    max_overflow=10 if not db_url.startswith("sqlite") else 0,
    pool_pre_ping=True,
    connect_args=connect_args,
)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """Initializes the database by creating all defined SQLModel tables.

    Uses an asynchronous connection to run synchronous metadata creation.
    """
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def get_session() -> AsyncSession:
    """Dependency for providing an asynchronous database session.

    Yields:
        AsyncSession: A scoped asynchronous database session.
    """
    async with async_session_maker() as session:
        yield session
