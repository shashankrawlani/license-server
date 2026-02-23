import pytest
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import patch
from license_server.models import VerificationRequest
from license_server.config import settings

pytestmark = pytest.mark.asyncio


async def test_full_user_journey_e2e(client, session, test_app, target_app_id, auth_headers):
    """
    E2E Test: Tests the complete lifecycle of a license.
    1. Community Registration -> Verification -> Activation
    2. Admin Generation -> Revocation
    """
    user_email = "e2e-user@example.com"
    admin_key = settings.ADMIN_API_KEY
    admin_headers = {
        "Authorization": f"Bearer {admin_key}",
        "X-App-Id": target_app_id
    }

    # --- 1. COMMUNITY JOURNEY ---

    # Step 1: Register
    with patch("license_server.routes.send_email") as mock_send:
        response = await client.post("/register", json={
            "email": user_email,
            "name": "E2E User",
            "company": "E2E Inc"
        }, headers=auth_headers)
        assert response.status_code == 200
        assert "Registration successful" in response.json()["message"] or "Verification email sent" in response.json()["message"]
        assert response.json()["verification_url"] is not None or settings.EMAIL_ENABLED

    # Step 2: Verification (Internal: find token)
    results = await session.execute(select(VerificationRequest).where(VerificationRequest.email == user_email))
    v_req = results.scalars().first()
    assert v_req is not None
    assert v_req.app_id == target_app_id
    token = v_req.token

    # Step 3: Call Verify Email
    with patch("license_server.routes.send_email") as mock_send_license:
        verify_resp = await client.get(f"/verify-email?token={token}")
        assert verify_resp.status_code == 200
        data = verify_resp.json()
        assert data["tier"] == "community"
        community_key = data["license_key"]

    # Step 4: Validate Community License
    val_resp = await client.post(
        f"/validate-license?license_key={community_key}", 
        headers=auth_headers
    )
    assert val_resp.status_code == 200
    assert val_resp.json()["valid"] is True

    # --- 2. ENTERPRISE JOURNEY (ADMIN) ---

    # Step 5: Admin generates Enterprise license
    ent_email = "enterprise-e2e@corp.com"
    gen_resp = await client.post(
        "/generate-license",
        json={
            "email": ent_email,
            "tier": "enterprise",
            "days": 30
        },
        headers=admin_headers
    )
    assert gen_resp.status_code == 200
    enterprise_key = gen_resp.json()["license_key"]

    # Step 6: Validate Enterprise License
    val_ent_resp = await client.post(
        f"/validate-license?license_key={enterprise_key}", 
        headers=auth_headers
    )
    assert val_ent_resp.status_code == 200
    assert val_ent_resp.json()["valid"] is True

    # --- 3. REVOCATION ---

    # Step 7: Revoke Enterprise License
    rev_resp = await client.post(
        f"/revoke-license?license_key={enterprise_key}",
        headers=admin_headers
    )
    assert rev_resp.status_code == 200
    assert "Revoked 1 licenses" in rev_resp.json()["message"]

    # Step 8: Verify Enterprise License is now invalid
    val_rev_resp = await client.post(
        f"/validate-license?license_key={enterprise_key}", 
        headers=auth_headers
    )
    assert val_rev_resp.status_code == 404

    # Step 9: List all licenses (Admin)
    list_resp = await client.get(
        "/licenses", 
        headers=admin_headers
    )
    assert list_resp.status_code == 200
    all_licenses = list_resp.json()
    assert len(all_licenses) >= 2

async def test_admin_unauthorized_access(client, target_app_id):
    """Verify admin endpoints are protected."""
    auth_header = {
        "Authorization": "Bearer invalid-key",
        "X-App-Id": target_app_id
    }
    
    # 1. Generate license
    resp1 = await client.post("/generate-license", json={}, headers=auth_header)
    assert resp1.status_code in (401, 403)
    
    # 2. Revoke license
    resp2 = await client.post("/revoke-license", headers=auth_header)
    assert resp2.status_code in (401, 403)
    
    # 3. List licenses
    resp3 = await client.get("/licenses", headers=auth_header)
    assert resp3.status_code in (401, 403)
