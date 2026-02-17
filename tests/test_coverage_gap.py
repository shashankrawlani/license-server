import pytest
import os
import uuid
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
from license_server.routes import send_email
from license_server.config import settings
from license_server.database import get_session, init_db

@pytest.mark.asyncio
async def test_send_email_no_api_key(capsys):
    """Cover lines 25-26 in routes.py (Missing API Key)."""
    with patch("license_server.routes.settings") as mock_settings:
        mock_settings.RESEND_API_KEY = None
        send_email("test@ex.com", "Sub", "Body")
    
    captured = capsys.readouterr()
    assert "[DEV MODE] Email to test@ex.com skipped" in captured.out

@pytest.mark.asyncio
async def test_validate_license_naive_datetime(client, session):
    """Cover line 209 in routes.py (Naive datetime handling)."""
    # Mocking the database result to return a naive datetime
    mock_record = MagicMock()
    mock_record.expires_at = datetime(2099, 1, 1) # Naive
    mock_record.tzinfo = None
    mock_record.tier = "community"
    mock_record.email = "naive@ex.com"
    mock_record.license_key = "naive-key"
    mock_record.features = []
    mock_record.license_metadata = {}
    
    with patch("license_server.routes.select") as mock_select:
        mock_res = MagicMock()
        mock_res.scalars().first.return_value = mock_record
        with patch.object(session, "execute", return_value=mock_res):
            resp = await client.post("/validate-license?license_key=naive-key")
            assert resp.status_code == 200

@pytest.mark.asyncio
async def test_real_database_functions():
    """Cover lines in database.py."""
    await init_db()
    async for sess in get_session():
        assert sess is not None
        break

@pytest.mark.asyncio
async def test_main_lifespan_explicit():
    """Cover lines 16-18 in main.py."""
    from license_server.main import lifespan
    from fastapi import FastAPI
    
    mock_app = MagicMock(spec=FastAPI)
    with patch("license_server.main.init_db") as m_init, \
         patch("license_server.main.generate_keypair") as m_gen:
        
        ctx = lifespan(mock_app)
        async with ctx:
            m_init.assert_called_once()
            m_gen.assert_called_once()
