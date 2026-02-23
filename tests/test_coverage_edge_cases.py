import pytest
import os
import tempfile
import shutil
import asyncio
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import patch, MagicMock, AsyncMock

from license_server.config import settings, Settings
from license_server.routes import get_public_key, send_email
from license_server.models import App, License, VerificationRequest
from sqlmodel import delete, select
from argon2 import PasswordHasher

# --- routes.py Edge Cases ---

@pytest.mark.asyncio
async def test_resolve_single_app_zero(client: AsyncClient, session: AsyncSession):
    """Test single-tenant mode with zero apps registered."""
    settings.MULTI_TENANT_MODE = False
    from license_server.routes import _invalidate_app_cache
    _invalidate_app_cache()
    
    await session.execute(delete(App))
    await session.commit()
    
    resp = await client.post("/validate-license?license_key=fake")
    assert resp.status_code == 400
    assert "No app registered" in resp.json()["detail"]

@pytest.mark.asyncio
async def test_resolve_single_app_multiple(client: AsyncClient, session: AsyncSession):
    """Test single-tenant mode with multiple apps (should error)."""
    settings.MULTI_TENANT_MODE = False
    from license_server.routes import _invalidate_app_cache
    _invalidate_app_cache()
    
    ph = PasswordHasher()
    app1 = App(slug="app1", name="App 1", api_key_hash=ph.hash("key1"))
    app2 = App(slug="app2", name="App 2", api_key_hash=ph.hash("key2"))
    session.add(app1)
    session.add(app2)
    await session.commit()
    
    resp = await client.post("/validate-license?license_key=fake")
    assert resp.status_code == 400
    assert "Multiple apps exist" in resp.json()["detail"]

@pytest.mark.asyncio
async def test_verify_admin_missing_header_multi_tenant(client: AsyncClient):
    """Test admin endpoint requires X-App-Id in multi-tenant mode."""
    settings.MULTI_TENANT_MODE = True
    resp = await client.post(
        "/generate-license",
        json={"email": "a@ex.com", "tier": "pro"},
        headers={"Authorization": f"Bearer {settings.ADMIN_API_KEY}"}
    )
    assert resp.status_code == 400
    assert "X-App-Id header is required for admin operations in multi-tenant mode" in resp.json()["detail"]

@pytest.mark.asyncio
async def test_verify_admin_not_configured(client: AsyncClient, target_app_id):
    """Test admin endpoint fails when ADMIN_API_KEY not configured."""
    with patch("license_server.routes.settings.ADMIN_API_KEY", ""):
        resp = await client.post(
            "/generate-license",
            json={"email": "a@ex.com", "tier": "pro"},
            headers={"Authorization": "Bearer fake", "X-App-Id": target_app_id}
        )
        assert resp.status_code == 500
        assert "ADMIN_API_KEY not configured" in resp.json()["detail"]

@pytest.mark.asyncio
async def test_verify_app_missing_headers_multi_tenant(client: AsyncClient):
    """Test public endpoint requires headers in multi-tenant mode."""
    settings.MULTI_TENANT_MODE = True
    resp = await client.post("/validate-license?license_key=fake")
    assert resp.status_code == 401
    assert "X-App-Id and X-App-Key are required" in resp.json()["detail"]

@pytest.mark.asyncio
async def test_verify_app_invalid_slug(client: AsyncClient):
    """Test invalid app slug returns 401."""
    settings.MULTI_TENANT_MODE = True
    resp = await client.post(
        "/validate-license?license_key=fake",
        headers={"X-App-Id": "invalid", "X-App-Key": "fake"}
    )
    assert resp.status_code == 401
    assert "Invalid App ID or API Key" in resp.json()["detail"]

@pytest.mark.asyncio
async def test_verify_app_invalid_key(client: AsyncClient, target_app_id):
    """Test invalid app key returns 401."""
    settings.MULTI_TENANT_MODE = True
    resp = await client.post(
        "/validate-license?license_key=fake",
        headers={"X-App-Id": target_app_id, "X-App-Key": "wrongkey"}
    )
    assert resp.status_code == 401
    assert "Invalid App ID or API Key" in resp.json()["detail"]

@pytest.mark.asyncio
async def test_verify_email_early_return_existing_license(client: AsyncClient, session: AsyncSession, target_app_id):
    """Test verify_email returns existing license if already active."""
    email = "testearly@ex.com"
    license_rec = License(
        email=email,
        app_id=target_app_id,
        tier="community",
        license_key="fake-existing-key",
        expires_at=datetime.now(timezone.utc) + timedelta(days=365)
    )
    verify_req = VerificationRequest(
        email=email,
        app_id=target_app_id,
        token="faketok",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        registration_data={}
    )
    session.add(license_rec)
    session.add(verify_req)
    await session.commit()
    
    resp = await client.get(f"/verify-email?token=faketok&app_id={target_app_id}")
    assert resp.status_code == 200
    assert resp.json()["license_key"] == "fake-existing-key"

@pytest.mark.asyncio
async def test_revoke_license_not_found(client: AsyncClient, target_app_id):
    """Test revoking non-existent license returns 404."""
    resp = await client.post(
        "/revoke-license?email=notfound@ex.com",
        headers={"Authorization": f"Bearer {settings.ADMIN_API_KEY}", "X-App-Id": target_app_id}
    )
    assert resp.status_code == 404
    assert "Active license not found" in resp.json()["detail"]

@pytest.mark.asyncio
async def test_get_public_key_fallback():
    """Test get_public_key returns error when file missing."""
    old_pub = settings.PUBLIC_KEY_PATH
    settings.PUBLIC_KEY_PATH = "/tmp/does-not-exist.pem"
    val = get_public_key()
    assert "Error:" in val
    settings.PUBLIC_KEY_PATH = old_pub

@pytest.mark.asyncio
async def test_send_email_fallback(capsys):
    """Test send_email catches exceptions and prints error (lines 29-30)."""
    with patch("license_server.routes.settings.RESEND_API_KEY", "test-key"):
        with patch("resend.Emails.send", side_effect=Exception("API Down")):
            send_email("to@ex.com", "sub", "html")
            captured = capsys.readouterr()
            assert "Failed to send email" in captured.out

@pytest.mark.asyncio
async def test_send_email_no_api_key(capsys):
    """Test send_email skips when no API key configured."""
    with patch("license_server.routes.settings.RESEND_API_KEY", None):
        send_email("to@ex.com", "Subject", "Body")
        captured = capsys.readouterr()
        assert "DEV MODE" in captured.out
        assert "skipped" in captured.out

@pytest.mark.asyncio
async def test_missing_private_key_generation(temp_keys_dir):
    """Test that keys are generated on startup if missing."""
    from license_server.main import lifespan, app
    
    with patch("license_server.config.settings.PRIVATE_KEY_PATH", os.path.join(temp_keys_dir, "new_priv.pem")):
        with patch("license_server.config.settings.PUBLIC_KEY_PATH", os.path.join(temp_keys_dir, "new_pub.pem")):
            with patch("license_server.main.settings.ENVIRONMENT", "dev"):
                with patch("license_server.main.init_db", new_callable=AsyncMock):
                    async with lifespan(app):
                        pass
                    assert os.path.exists(os.path.join(temp_keys_dir, "new_priv.pem"))

# --- main.py Edge Cases ---

@pytest.mark.asyncio
async def test_docs_hidden_in_prod():
    """Test that docs are hidden in production environment."""
    import importlib
    import license_server.main
    
    with patch("license_server.main.settings.ENVIRONMENT", "production"):
        reloaded_app = importlib.reload(license_server.main).app
        assert reloaded_app.docs_url is None
        assert reloaded_app.openapi_url is None

# --- database.py Edge Cases ---

@pytest.mark.asyncio
async def test_db_pool_creation():
    """Test database engine creation."""
    import importlib
    import license_server.database
    
    with patch("license_server.database.settings.ENVIRONMENT", "production"):
        mod = importlib.reload(license_server.database)
        assert mod.engine is not None

@pytest.mark.asyncio
async def test_get_session_coverage():
    """Test get_session generator (lines 54-55)."""
    from license_server.database import get_session
    async for session in get_session():
        assert session is not None
        break

# --- config.py Edge Cases ---

def test_config_env_loaded():
    """Test config loads from env file."""
    s = Settings(_env_file=".env.test", _env_file_encoding="utf-8")
    assert s.ENVIRONMENT is not None

def test_config_secrets_dir():
    """Test config loads from secrets directory."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        # Create fake secrets
        with open(os.path.join(d, "resend_api_key"), "w") as f:
            f.write("resend-secret\n")
        with open(os.path.join(d, "admin_api_key"), "w") as f:
            f.write("admin-secret\n")
            
        from pydantic_settings import SettingsConfigDict
        
        class TestSettings(Settings):
            model_config = SettingsConfigDict(secrets_dir=d)
            
        s = TestSettings(ADMIN_API_KEY="", RESEND_API_KEY="")
        assert s.RESEND_API_KEY == "resend-secret"
        assert s.ADMIN_API_KEY == "admin-secret"

def test_config_secrets_dir_missing():
    """Test config handles missing secrets gracefully (lines 23->27, 29->exit)."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        # Empty secrets dir
        from pydantic_settings import SettingsConfigDict
        
        class TestSettings(Settings):
            model_config = SettingsConfigDict(secrets_dir=d)
            
        # Should not crash, just use defaults/env vars
        s = TestSettings(ADMIN_API_KEY="from-env", RESEND_API_KEY="from-env")
        assert s.ADMIN_API_KEY == "from-env"
        assert s.RESEND_API_KEY == "from-env"

@pytest.mark.asyncio
async def test_verify_admin_auto_resolve_single_tenant(client: AsyncClient, session: AsyncSession, target_app_id):
    """Test admin auto-resolves app in single-tenant when X-App-Id is missing."""
    settings.MULTI_TENANT_MODE = False
    from license_server.routes import _invalidate_app_cache
    _invalidate_app_cache()
    
    resp = await client.post(
        "/generate-license",
        json={"email": "autoresolve@ex.com", "tier": "community"},
        headers={"Authorization": f"Bearer {settings.ADMIN_API_KEY}"}
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == "autoresolve@ex.com"

@pytest.mark.asyncio
async def test_email_enabled_path(client: AsyncClient, session: AsyncSession, target_app_id):
    """Test email enabled path in verify_email."""
    old_email_enabled = settings.EMAIL_ENABLED
    settings.EMAIL_ENABLED = True
    settings.MULTI_TENANT_MODE = False
    from license_server.routes import _invalidate_app_cache
    _invalidate_app_cache()
    
    try:
        # Create registration
        resp = await client.post(
            "/register",
            json={"email": "emailtest@ex.com", "name": "Test", "company": "Test", "use_case": "Test"}
        )
        
        # Get token from DB
        stm = select(VerificationRequest).where(VerificationRequest.email == "emailtest@ex.com")
        res = await session.execute(stm)
        req = res.scalars().first()
        
        with patch("license_server.routes.send_email") as mock_send:
            resp_verify = await client.get(f"/verify-email?token={req.token}&app_id={target_app_id}")
            assert resp_verify.status_code == 200
            assert "sent to your inbox" in resp_verify.json()["message"]
            mock_send.assert_called()
    finally:
        settings.EMAIL_ENABLED = old_email_enabled

@pytest.mark.asyncio
async def test_validate_license_naive_datetime(client: AsyncClient, session: AsyncSession, target_app_id):
    """Test naive datetime handling in validate_license (line 355)."""
    settings.MULTI_TENANT_MODE = False
    from license_server.routes import _invalidate_app_cache
    _invalidate_app_cache()
    
    # Create license with naive datetime
    import datetime
    license_rec = License(
        email="naive@ex.com",
        app_id=target_app_id,
        tier="community",
        license_key="fake-naive-key",
        expires_at=datetime.datetime.now() + datetime.timedelta(days=365)
    )
    session.add(license_rec)
    await session.commit()
    
    # This hits the DB lookup path which handles naive datetimes
    resp = await client.post(
        f"/validate-license?license_key=fake-naive-key",
        headers={"X-App-Id": target_app_id, "X-App-Key": "test_api_key"}
    )
    # The license exists in DB, so it returns valid
    assert resp.status_code == 200
    assert resp.json()["valid"] is True
