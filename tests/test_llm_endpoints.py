import pytest
from httpx import AsyncClient
import os

@pytest.mark.asyncio
async def test_llms_txt_endpoint(client: AsyncClient):
    """Test that the /llms.txt endpoint returns the file content."""
    # Ensure file exists for test
    if not os.path.exists("llms.txt"):
        with open("llms.txt", "w") as f:
            f.write("test Roadmap")
            
    response = await client.get("/llms.txt")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert "License Server" in response.text

@pytest.mark.asyncio
async def test_llms_full_txt_endpoint(client: AsyncClient):
    """Test that the /llms-full.txt endpoint returns the file content."""
    # Ensure file exists for test
    if not os.path.exists("llms-full.txt"):
        with open("llms-full.txt", "w") as f:
            f.write("test Context")
            
    response = await client.get("/llms-full.txt")
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert "User Journey" in response.text
