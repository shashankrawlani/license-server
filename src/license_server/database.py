from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlmodel import SQLModel
from .config import settings

# PostgreSQL-only:
def normalize_db_url(url: str) -> str:
    """Normalizes a PostgreSQL URL for use with the asyncpg driver.

    Converts 'postgresql://' or 'postgres://' schemes to 
    'postgresql+asyncpg://' if not already present.

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
    if not url.startswith("postgresql+asyncpg://"):
        raise ValueError(f"Unsupported DATABASE_URL scheme: {url.split('://')[0] if '://' in url else url}")
    return url

db_url = normalize_db_url(settings.DATABASE_URL)
engine = create_async_engine(
    db_url,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
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
