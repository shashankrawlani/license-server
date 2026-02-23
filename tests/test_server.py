import pytest
import os
from sqlmodel import select
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from license_server.main import app
from license_server.database import get_session
from license_server.crypto import verify_license_local, sign_license
from license_server.config import settings
from license_server.models import License, VerificationRequest, App

pytestmark = pytest.mark.asyncio


async def test_health_check(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

async def test_register_community(client, session, test_app, target_app_id, auth_headers):
    # Mocking email sending
    payload = {
        "email": "test@user.com",
        "name": "Test User",
        "company": "Test Co",
        "use_case": "Development"
    }
    with patch("license_server.routes.send_email") as mock_send:
        response = await client.post("/register", json=payload, headers=auth_headers)
        assert response.status_code == 200
        assert "Verification email sent" in response.json()["message"] or "Registration successful" in response.json()["message"]
        
        # Verify DB state
        statement = select(VerificationRequest).where(VerificationRequest.email == "test@user.com")
        result = await session.execute(statement)
        v_req = result.scalars().first()
        assert v_req is not None
        assert v_req.app_id == target_app_id
        assert v_req.registration_data["name"] == "Test User"

async def test_register_existing_active_license(client, session, test_app, target_app_id, auth_headers):
    # Setup: Create an existing license for THIS app
    existing_license = License(
        email="active@user.com",
        app_id=target_app_id,
        tier="community",
        license_key="already-active-key",
        expires_at=datetime.now(timezone.utc) + timedelta(days=1)
    )
    session.add(existing_license)
    await session.commit()
    
    payload = {"email": "active@user.com", "name": "Active User"}
    response = await client.post("/register", json=payload, headers=auth_headers)
    assert response.status_code == 200
    assert "Verification email sent" in response.json()["message"] or "Registration successful" in response.json()["message"]

async def test_verify_email_success(client, session, test_app, target_app_id):
    # 1. Register first
    v_req = VerificationRequest(
        email="verify@me.com",
        app_id=target_app_id,
        token="valid-token",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        registration_data={"name": "Verify Me"}
    )
    session.add(v_req)
    await session.commit()
    
    with patch("license_server.routes.send_email") as mock_send:
        response = await client.get("/verify-email?token=valid-token")
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "verify@me.com"
        assert "license_key" in data
        assert "active" in data["message"]
        
        # Verify license created in DB
        results = await session.execute(select(License).where(License.email == "verify@me.com"))
        license_rec = results.scalars().first()
        assert license_rec is not None
        assert license_rec.tier == "community"
        assert license_rec.app_id == target_app_id

async def test_verify_email_invalid_token(client):
    response = await client.get("/verify-email?token=invalid-token")
    assert response.status_code == 404

async def test_verify_email_expired(client, session, target_app_id):
    v_req = VerificationRequest(
        email="expired@me.com",
        app_id=target_app_id,
        token="expired-token",
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        registration_data={}
    )
    session.add(v_req)
    await session.commit()
    
    response = await client.get("/verify-email?token=expired-token")
    assert response.status_code == 400
    assert "expired" in response.json()["detail"]

async def test_generate_license_admin(client, session, target_app_id):
    payload = {
        "email": "customer@enterprise.com",
        "tier": "enterprise",
        "days": 365,
        "features": ["max_users_100"],
        "license_metadata": {"invoice_id": "INV-001"}
    }
    admin_headers = {
        "Authorization": f"Bearer {settings.ADMIN_API_KEY}",
        "X-App-Id": target_app_id
    }
    response = await client.post("/generate-license", json=payload, headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["tier"] == "enterprise"
    
    # Verify DB
    stmt = select(License).where(License.email == "customer@enterprise.com")
    res = await session.execute(stmt)
    license_rec = res.scalars().first()
    assert license_rec.app_id == target_app_id
    assert license_rec.features == ["max_users_100"]

async def test_validate_license(client, session, target_app_id, auth_headers):
    # Create license directly in DB
    key = "valid-key-123"
    lic = License(
        email="user@test.com",
        app_id=target_app_id,
        tier="pro",
        license_key=key,
        expires_at=datetime.now(timezone.utc) + timedelta(days=10)
    )
    session.add(lic)
    await session.commit()
    
    response = await client.post(f"/validate-license?license_key={key}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["valid"] is True
    assert response.json()["tier"] == "pro"

async def test_validate_revoked_license(client, session, target_app_id, auth_headers):
    # Create and revoke manually
    new_lic = License(
        email="revoked@test.com",
        app_id=target_app_id,
        tier="enterprise",
        license_key="revoked-key",
        expires_at=datetime.now(timezone.utc) + timedelta(days=10),
        revoked_at=datetime.now(timezone.utc)
    )
    session.add(new_lic)
    await session.commit()
    
    response = await client.post("/validate-license?license_key=revoked-key", headers=auth_headers)
    assert response.status_code == 404

async def test_revoke_license(client, session, target_app_id, auth_headers):
    # 1. Register a license
    payload = {"email": "revoke@me.com", "name": "Revoke Me"}
    await client.post("/register", json=payload, headers=auth_headers)
    
    stmt = select(VerificationRequest).where(VerificationRequest.email == "revoke@me.com")
    res = await session.execute(stmt)
    token = res.scalars().first().token
    await client.get(f"/verify-email?token={token}")
    
    # 2. Revoke it
    admin_headers = {
        "Authorization": f"Bearer {settings.ADMIN_API_KEY}",
        "X-App-Id": target_app_id
    }
    rev_resp = await client.post("/revoke-license?email=revoke@me.com", headers=admin_headers)
    assert rev_resp.status_code == 200
    assert "Revoked 1 licenses" in rev_resp.json()["message"]
    
    # 3. Verify it's revoked in DB
    final_stmt = select(License).where(License.email == "revoke@me.com")
    final_res = await session.execute(final_stmt)
    license_rec = final_res.scalars().first()
    assert license_rec.revoked_at is not None

async def test_list_licenses(client, session, target_app_id, auth_headers):
    # Create two licenses
    for i in range(2):
        lic = License(
            email=f"user{i}@test.com",
            app_id=target_app_id,
            tier="community",
            license_key=f"key-{i}",
            expires_at=datetime.now(timezone.utc) + timedelta(days=1)
        )
        session.add(lic)
    await session.commit()

    admin_headers = {
        "Authorization": f"Bearer {settings.ADMIN_API_KEY}",
        "X-App-Id": target_app_id
    }
    response = await client.get("/licenses", headers=admin_headers)
    assert response.status_code == 200
    assert len(response.json()) >= 2

async def test_validate_expired_license(client, session, target_app_id, auth_headers):
    expired_lic = License(
        email="expired@test.com",
        app_id=target_app_id,
        tier="community",
        license_key="expired-key",
        expires_at=datetime.now(timezone.utc) - timedelta(days=1)
    )
    session.add(expired_lic)
    await session.commit()
    
    response = await client.post("/validate-license?license_key=expired-key", headers=auth_headers)
    assert response.status_code == 403
    assert "expired" in response.json()["detail"].lower()

async def test_multi_app_isolation(client, session, test_app):
    """Verify that licenses from App A cannot be validated by App B."""
    # Isolation only exists in Multi-Tenant mode
    if not settings.MULTI_TENANT_MODE:
        pytest.skip("Isolation not applicable in single-tenant mode")

    from argon2 import PasswordHasher
    import secrets
    ph = PasswordHasher()
    
    api_key_b = secrets.token_hex(32)
    app_b = App(slug="app-b", name="App B", api_key_hash=ph.hash(api_key_b))
    session.add(app_b)
    
    license_a = License(
        email="user@example.com",
        app_id="test-app",
        tier="community",
        license_key="key-for-app-a",
        expires_at=datetime.now(timezone.utc) + timedelta(days=1)
    )
    session.add(license_a)
    await session.commit()
    
    headers_b = {
        "X-App-Id": "app-b",
        "X-App-Key": api_key_b
    }
    response = await client.post("/validate-license?license_key=key-for-app-a", headers=headers_b)
    assert response.status_code == 404
