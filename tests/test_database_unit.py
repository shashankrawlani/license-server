import pytest
from license_server.database import normalize_db_url

def test_db_url_normalization():
    """Test various database URL formats."""
    # PostgreSQL
    assert normalize_db_url("postgres://u:p@h/d") == "postgresql+asyncpg://u:p@h/d"
    assert normalize_db_url("postgresql://u:p@h/d") == "postgresql+asyncpg://u:p@h/d"
    assert normalize_db_url("postgresql+asyncpg://u:p@h/d") == "postgresql+asyncpg://u:p@h/d"
    
    # SQLite
    assert normalize_db_url("sqlite:///data.db") == "sqlite+aiosqlite:///data.db"
    assert normalize_db_url("sqlite+aiosqlite:///data.db") == "sqlite+aiosqlite:///data.db"

def test_unsupported_scheme():
    """Test that unsupported schemes raise ValueError."""
    with pytest.raises(ValueError, match="Unsupported DATABASE_URL scheme: mysql"):
        normalize_db_url("mysql://localhost/db")

def test_malformed_url():
    """Test malformed URLs."""
    with pytest.raises(ValueError):
        normalize_db_url("not-a-url")
