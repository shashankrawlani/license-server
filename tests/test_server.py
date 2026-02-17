import pytest
import os
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool
from datetime import datetime, timezone, timedelta

# Mock environment BEFORE importing app or routes
os.environ["ADMIN_API_KEY"] = "test-admin-key"
os.environ["RATE_LIMIT_ENABLED"] = "false"

from license_server.main import app
from license_server.database import get_session
from license_server.crypto import verify_license_local, sign_license
from license_server.config import settings
import unittest.mock as mock
from unittest.mock import patch
from license_server.models import License, VerificationRequest

pytestmark = pytest.mark.asyncio

async def test_health_check(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

async def test_register_community(client, session):
    # Mocking email sending
    with patch("license_server.routes.send_email") as mock_send:
        payload = {
            "email": "test@example.com",
            "name": "Test User",
            "company": "Test Co",
            "use_case": "Evaluation"
        }
        response = await client.post("/register", json=payload)
        assert response.status_code == 200
        assert "Verification email sent" in response.json()["message"]
        
        # Verify it's in DB
        results = await session.execute(select(VerificationRequest).where(VerificationRequest.email == "test@example.com"))
        v_req = results.scalars().first()
        assert v_req is not None
        assert v_req.registration_data["name"] == "Test User"

async def test_register_existing_active_license(client, session):
    # Setup: Create an existing license
    existing_license = License(
        email="active@user.com",
        tier="community",
        license_key="already-active-key",
        expires_at=datetime.now(timezone.utc) + timedelta(days=1)
    )
    session.add(existing_license)
    await session.commit()
    
    payload = {"email": "active@user.com", "name": "Active User"}
    response = await client.post("/register", json=payload)
    assert response.status_code == 200
    assert "already exists" in response.json()["message"]

async def test_verify_email_success(client, session):
    # 1. Register first
    v_req = VerificationRequest(
        email="verify@me.com",
        token="valid-token",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        registration_data={"name": "Verify Me"}
    )
    session.add(v_req)
    await session.commit()
    
    # 2. Verify
    with patch("license_server.routes.send_email") as mock_send:
        response = await client.get("/verify-email?token=valid-token")
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "verify@me.com"
        assert "license_key" in data
        
        # Verify license created in DB
        results = await session.execute(select(License).where(License.email == "verify@me.com"))
        license_rec = results.scalars().first()
        assert license_rec is not None
        assert license_rec.tier == "community"

async def test_verify_email_invalid_token(client):
    response = await client.get("/verify-email?token=invalid-token")
    assert response.status_code == 404

async def test_verify_email_expired(client, session):
    v_req = VerificationRequest(
        email="expired@me.com",
        token="expired-token",
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        registration_data={}
    )
    session.add(v_req)
    await session.commit()
    
    response = await client.get("/verify-email?token=expired-token")
    assert response.status_code == 400
    assert "expired" in response.json()["detail"]

async def test_generate_license_admin(client):
    admin_key = "test-admin-key"
    payload = {
        "email": "enterprise@client.com",
        "tier": "enterprise",
        "days": 30,
        "features": ["feature1", "feature2"],
        "license_metadata": {"foo": "bar"}
    }

    # Test unauthorized
    response = await client.post("/generate-license", json=payload)
    assert response.status_code == 401

    # Test authorized
    response = await client.post(
        "/generate-license",
        json=payload,
        headers={"Authorization": f"Bearer {admin_key}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["tier"] == "enterprise"
    assert data["email"] == "enterprise@client.com"
    assert "license_key" in data

async def test_validate_license(client):
    # Create a license first
    admin_key = "test-admin-key"
    reg_payload = {
        "email": "valid@user.com",
        "tier": "community",
        "days": 10,
        "license_metadata": {}
    }
    resp = await client.post(
        "/generate-license",
        json=reg_payload,
        headers={"Authorization": f"Bearer {admin_key}"}
    )
    assert resp.status_code == 200
    license_key = resp.json()["license_key"]
    
    # Validate
    val_resp = await client.post(f"/validate-license?license_key={license_key}")
    assert val_resp.status_code == 200
    assert val_resp.json()["valid"] is True
    assert val_resp.json()["tier"] == "community"

async def test_validate_revoked_license(client, session):
    # Create and revoke manually
    new_lic = License(
        email="revoked@test.com",
        tier="enterprise",
        license_key="revoked-key",
        expires_at=datetime.now(timezone.utc) + timedelta(days=10),
        revoked_at=datetime.now(timezone.utc)
    )
    session.add(new_lic)
    await session.commit()
    
    val_resp = await client.post("/validate-license?license_key=revoked-key")
    assert val_resp.status_code == 404

async def test_revoke_license(client, session):
    admin_key = "test-admin-key"
    # Create two licenses for same email
    await client.post("/register", json={"email": "revoke@me.com", "name": "Revoke Me"})
    results = await session.execute(select(VerificationRequest))
    token = results.scalars().first().token
    await client.get(f"/verify-email?token={token}")

    await client.post(
        "/generate-license",
        json={"email": "revoke@me.com", "tier": "enterprise", "days": 365, "license_metadata": {}},
        headers={"Authorization": f"Bearer {admin_key}"}
    )

    # Revoke by email
    rev_resp = await client.post(
        "/revoke-license?email=revoke@me.com",
        headers={"Authorization": f"Bearer {admin_key}"}
    )
    assert rev_resp.status_code == 200
    assert "Revoked 2 licenses" in rev_resp.json()["message"]

async def test_list_licenses(client, session):
    admin_key = "test-admin-key"

    await client.post("/register", json={"email": "user1@test.com", "name": "User 1"})
    results1 = await session.execute(select(VerificationRequest).where(VerificationRequest.email == "user1@test.com"))
    token1 = results1.scalars().first().token
    await client.get(f"/verify-email?token={token1}")

    await client.post("/register", json={"email": "user2@test.com", "name": "User 2"})
    results2 = await session.execute(select(VerificationRequest).where(VerificationRequest.email == "user2@test.com"))
    token2 = results2.scalars().first().token
    await client.get(f"/verify-email?token={token2}")

    response = await client.get(
        "/licenses",
        headers={"Authorization": f"Bearer {admin_key}"}
    )
    assert response.status_code == 200
    assert len(response.json()) >= 2

async def test_revoke_error_cases(client):
    admin_key = "test-admin-key"
    # No params
    response = await client.post(
        "/revoke-license",
        headers={"Authorization": f"Bearer {admin_key}"}
    )
    assert response.status_code == 400
    
    # Not authorized
    response = await client.post("/revoke-license?email=foo@bar.com")
    assert response.status_code == 401

async def test_validate_expired_license(client, session):
    # Setup expired license
    expired_lic = License(
        email="expired@test.com",
        tier="community",
        license_key="expired-key",
        expires_at=datetime.now(timezone.utc) - timedelta(days=1)
    )
    session.add(expired_lic)
    await session.commit()
    
    val_resp = await client.post("/validate-license?license_key=expired-key")
    assert val_resp.status_code == 403
    assert "expired" in val_resp.json()["detail"].lower()

async def test_revoke_by_key(client, session):
    admin_key = "test-admin-key"
    resp_reg = await client.post("/register", json={"email": "keyrevoke@test.com", "name": "Key Revoke"})
    assert resp_reg.status_code == 200

    results = await session.execute(select(VerificationRequest).where(VerificationRequest.email == "keyrevoke@test.com"))
    verify_req = results.scalars().first()
    assert verify_req is not None
    token = verify_req.token

    resp_verify = await client.get(f"/verify-email?token={token}")
    assert resp_verify.status_code == 200
    key = resp_verify.json()["license_key"]

    rev_resp = await client.post(
        f"/revoke-license?license_key={key}",
        headers={"Authorization": f"Bearer {admin_key}"}
    )
    assert rev_resp.status_code == 200
    assert "Revoked 1 licenses" in rev_resp.json()["message"]

async def test_revoke_no_records_found(client):
    admin_key = "test-admin-key"
    response = await client.post(
        "/revoke-license?email=none@none.com",
        headers={"Authorization": f"Bearer {admin_key}"}
    )
    assert response.status_code == 404

async def test_verify_license_local_invalid_format():
    # Test line 85 in crypto.py
    assert verify_license_local("not-even-two-parts", b"public-key") is None
