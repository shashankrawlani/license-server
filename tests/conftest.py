import pytest
import os
import asyncio
import shutil
import tempfile
from typing import AsyncGenerator
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel, select, delete
from license_server.config import settings
from unittest.mock import patch

# Set testing environment variables - use file-based SQLite for tests
os.environ["ADMIN_API_KEY"] = "test-admin-key"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///test_licenses.db"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["BASE_URL"] = "http://testserver"
os.environ["ENVIRONMENT"] = "dev"

from license_server.main import app
from license_server.database import get_session
from license_server.limiter import limiter
from license_server.config import settings

# Force settings for tests
settings.ADMIN_API_KEY = "test-admin-key"
settings.DATABASE_URL = os.environ["DATABASE_URL"]
settings.RATE_LIMIT_ENABLED = False
settings.ENVIRONMENT = "dev"

# Disable rate limiting for tests
limiter.enabled = False

# Test engine using in-memory SQLite
test_engine = create_async_engine(
    os.environ["DATABASE_URL"],
    connect_args={"check_same_thread": False},
    poolclass=NullPool
)
test_async_session_maker = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

@pytest.fixture(scope="session", autouse=True)
async def setup_database():
    """Create all tables once for the entire test session."""
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)

@pytest.fixture(params=[False, True], autouse=True)
def toggle_multi_tenant(request):
    """Parametrize all tests to run in both single and multi-tenant modes."""
    settings.MULTI_TENANT_MODE = request.param
    yield

@pytest.fixture(autouse=True)
def reset_app_cache():
    """Reset the lazy app cache between tests to prevent stale state."""
    import license_server.routes as routes_module
    routes_module._cached_single_app = None
    yield
    routes_module._cached_single_app = None

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(name="session")
async def session_fixture() -> AsyncGenerator[AsyncSession, None]:
    """Provide a session and clean up all data after each test."""
    from license_server.models import License, VerificationRequest, App
    
    async with test_async_session_maker() as session:
        yield session
        
        # Clean up ALL data after each test for full isolation
        async with test_engine.begin() as conn:
            await conn.execute(delete(License))
            await conn.execute(delete(VerificationRequest))
            await conn.execute(delete(App))
            await conn.commit()

@pytest.fixture(name="client")
async def client_fixture(session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def _get_test_session():
        yield session
    
    app.dependency_overrides[get_session] = _get_test_session
    async with AsyncClient(
        transport=ASGITransport(app=app), 
        base_url="http://testserver"
    ) as client:
        yield client
    app.dependency_overrides.clear()

@pytest.fixture
async def test_app(session: AsyncSession):
    """Create a test app and return its credentials."""
    from license_server.models import App
    from argon2 import PasswordHasher
    import secrets
    
    ph = PasswordHasher()
    api_key = secrets.token_hex(32)
    api_key_hash = ph.hash(api_key)
    
    app_record = App(
        slug="test-app",
        name="Test Application",
        api_key_hash=api_key_hash
    )
    session.add(app_record)
    await session.commit()
    
    return {"slug": "test-app", "api_key": api_key}

@pytest.fixture
def temp_keys_dir():
    """Create a temporary directory for keys and cleanup after."""
    old_private = settings.PRIVATE_KEY_PATH
    old_public = settings.PUBLIC_KEY_PATH
    
    tmpdir = tempfile.mkdtemp()
    settings.PRIVATE_KEY_PATH = os.path.join(tmpdir, "private.pem")
    settings.PUBLIC_KEY_PATH = os.path.join(tmpdir, "public.pem")
    
    yield tmpdir
    
    shutil.rmtree(tmpdir)
    settings.PRIVATE_KEY_PATH = old_private
    settings.PUBLIC_KEY_PATH = old_public

@pytest.fixture(autouse=True)
def mock_send_email():
    """Mock send_email globally to avoid hitting Resend and fix domain errors."""
    with patch("license_server.routes.send_email") as mock:
        yield mock

@pytest.fixture
def target_app_id(test_app):
    """Always use the test app slug."""
    return test_app["slug"]

@pytest.fixture
def auth_headers(test_app):
    """Headers for API calls based on mode."""
    if settings.MULTI_TENANT_MODE:
        return {
            "X-App-Id": test_app["slug"],
            "X-App-Key": test_app["api_key"]
        }
    return {} # Ignored in single-tenant mode
