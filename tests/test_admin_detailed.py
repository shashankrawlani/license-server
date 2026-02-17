import pytest
from unittest.mock import patch
from license_server.config import settings

@pytest.mark.asyncio
async def test_list_licenses_detailed(client, session):
    """Test full license listing."""
    # Seed a few licenses
    from license_server.models import License
    from datetime import datetime, timezone, timedelta
    
    expiry = datetime.now(timezone.utc) + timedelta(days=1)
    l1 = License(email="u1@ex.com", tier="community", license_key="k1", expires_at=expiry)
    l2 = License(email="u2@ex.com", tier="enterprise", license_key="k2", expires_at=expiry)
    session.add(l1)
    session.add(l2)
    await session.commit()
    
    resp = await client.get("/licenses", headers={"Authorization": f"Bearer {settings.ADMIN_API_KEY}"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    emails = [l["email"] for l in data]
    assert "u1@ex.com" in emails
    assert "u2@ex.com" in emails

@pytest.mark.asyncio
async def test_revoke_by_email_multi(client, session):
    """Test revoking multiple licenses for same email."""
    from license_server.models import License
    from datetime import datetime, timezone, timedelta
    
    expiry = datetime.now(timezone.utc) + timedelta(days=1)
    email = "target@ex.com"
    l1 = License(email=email, tier="community", license_key="key1", expires_at=expiry)
    l2 = License(email=email, tier="enterprise", license_key="key2", expires_at=expiry)
    session.add(l1)
    session.add(l2)
    await session.commit()
    
    # Revoke by email
    resp = await client.post(
        f"/revoke-license?email={email}", 
        headers={"Authorization": f"Bearer {settings.ADMIN_API_KEY}"}
    )
    assert resp.status_code == 200
    assert "Revoked 2 licenses" in resp.json()["message"]

@pytest.mark.asyncio
async def test_revoke_missing_params(client):
    """Test revoke without email or key."""
    resp = await client.post(
        "/revoke-license", 
        headers={"Authorization": f"Bearer {settings.ADMIN_API_KEY}"}
    )
    assert resp.status_code == 400
    assert "Email or license_key required" in resp.json()["detail"]

@pytest.mark.asyncio
async def test_verify_admin_missing_config(client):
    """Test 500 error when ADMIN_API_KEY is not configured."""
    with patch("license_server.routes.settings") as mock_settings:
        mock_settings.ADMIN_API_KEY = None
        resp = await client.post(
            "/generate-license", 
            json={"email": "test@ex.com"},
            headers={"Authorization": "Bearer some-key"}
        )
        assert resp.status_code == 500
        assert "ADMIN_API_KEY not configured" in resp.json()["detail"]

@pytest.mark.asyncio
async def test_register_existing_community_active(client, session):
    """Test register when an active community license already exists."""
    from license_server.models import License
    from datetime import datetime, timezone, timedelta
    
    email = "existing@ex.com"
    expiry = datetime.now(timezone.utc) + timedelta(days=365)
    l = License(email=email, tier="community", license_key="key1", expires_at=expiry)
    session.add(l)
    await session.commit()
    
    resp = await client.post("/register", json={"email": email, "name": "Test"})
    assert resp.status_code == 200
    assert "active community license already exists" in resp.json()["message"]
