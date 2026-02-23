import pytest
from httpx import AsyncClient
from license_server.config import settings

pytestmark = pytest.mark.asyncio

async def test_admin_apps_crud(client: AsyncClient, session, target_app_id, auth_headers):
    """Test POST, GET, and DELETE /admin/apps."""
    # 1. POST /admin/apps
    create_resp = await client.post(
        f"/admin/apps?name=NewApp&slug=newapp",
        headers={"Authorization": f"Bearer {settings.ADMIN_API_KEY}", "X-App-Id": target_app_id}
    )
    assert create_resp.status_code == 200
    data = create_resp.json()
    assert data["slug"] == "newapp"
    assert data["name"] == "NewApp"
    assert "api_key" in data
    
    # 2. GET /admin/apps
    get_resp = await client.get(
        "/admin/apps",
        headers={"Authorization": f"Bearer {settings.ADMIN_API_KEY}", "X-App-Id": target_app_id}
    )
    assert get_resp.status_code == 200
    apps_list = get_resp.json()
    assert len(apps_list) >= 2 # Includes the test fixture app and 'newapp'
    slugs = [app["slug"] for app in apps_list]
    assert "newapp" in slugs
    
    # 3. DELETE /admin/apps/{slug}
    del_resp = await client.delete(
        "/admin/apps/newapp",
        headers={"Authorization": f"Bearer {settings.ADMIN_API_KEY}", "X-App-Id": target_app_id}
    )
    assert del_resp.status_code == 200
    assert "deleted successfully" in del_resp.json()["message"]
    
    # 4. Verify deletion
    get_resp2 = await client.get(
        "/admin/apps",
        headers={"Authorization": f"Bearer {settings.ADMIN_API_KEY}", "X-App-Id": target_app_id}
    )
    apps_list2 = get_resp2.json()
    slugs2 = [app["slug"] for app in apps_list2]
    assert "newapp" not in slugs2

async def test_admin_apps_delete_with_active_licenses(client: AsyncClient, session, target_app_id, auth_headers):
    """Test DELETE /admin/apps/{slug} fails if app has active licenses."""
    # The test fixture app (`target_app_id`) is created, let's generate a license for it
    license_resp = await client.post(
        "/generate-license",
        json={"email": "active@example.com", "tier": "pro"},
        headers={"Authorization": f"Bearer {settings.ADMIN_API_KEY}", "X-App-Id": target_app_id}
    )
    assert license_resp.status_code == 200
    
    # Attempt to delete the app
    del_resp = await client.delete(
        f"/admin/apps/{target_app_id}",
        headers={"Authorization": f"Bearer {settings.ADMIN_API_KEY}", "X-App-Id": target_app_id}
    )
    assert del_resp.status_code == 400
    assert "Cannot delete app with active licenses" in del_resp.json()["detail"]

async def test_admin_apps_delete_not_found(client: AsyncClient, target_app_id, auth_headers):
    """Test DELETE /admin/apps/{slug} fails if app doesn't exist."""
    del_resp = await client.delete(
        "/admin/apps/doesnotexist",
        headers={"Authorization": f"Bearer {settings.ADMIN_API_KEY}", "X-App-Id": target_app_id}
    )
    assert del_resp.status_code == 404
    assert "App not found" in del_resp.json()["detail"]
