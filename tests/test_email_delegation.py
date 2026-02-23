import pytest
from unittest.mock import patch
from license_server.config import settings

pytestmark = pytest.mark.asyncio


async def test_email_delegation_disabled_by_default(client, auth_headers):
    """Verify that email is disabled by default and verification_url is returned."""
    # Force settings to have EMAIL_ENABLED = False for this test
    with patch.object(settings, 'EMAIL_ENABLED', False):
        payload = {
            "email": "test_delegation@example.com",
            "name": "Delegation Test",
            "company": "Test Corp",
            "use_case": "Testing"
        }
        response = await client.post("/register", json=payload, headers=auth_headers)
        assert response.status_code == 200, f"Response: {response.text}"
        data = response.json()
        
        # Verification URL should be present
        assert data.get("verification_url") is not None
        assert "token=" in data["verification_url"]

async def test_email_enabled_behavior(client, mock_send_email, auth_headers):
    """Verify behavior when email is enabled."""
    # Force EMAIL_ENABLED = True
    with patch.object(settings, 'EMAIL_ENABLED', True), \
         patch.object(settings, 'RESEND_API_KEY', "re_test_fake"):
         
        payload = {
            "email": "test_enabled@example.com",
            "name": "Enabled Test",
            "company": "Test Corp",
            "use_case": "Testing"
        }
        
        response = await client.post("/register", json=payload, headers=auth_headers)
        assert response.status_code == 200, f"Response: {response.text}"
        data = response.json()
        
        # Verification URL should be None when email is enabled
        assert data.get("verification_url") is None
        assert "Verification email sent" in data["message"]
