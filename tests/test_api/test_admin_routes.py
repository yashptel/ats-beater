import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from app.models.roast import Roast, RoastStatus
from app.models.roast_view import RoastView


@pytest.mark.asyncio
async def test_create_tenant(admin_client):
    resp = await admin_client.post("/admin/tenants", json={"name": "Acme"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Acme"
    assert data["user_count"] == 0
    assert "id" in data


@pytest.mark.asyncio
async def test_list_tenants(admin_client):
    await admin_client.post("/admin/tenants", json={"name": "Tenant A"})
    await admin_client.post("/admin/tenants", json={"name": "Tenant B"})
    resp = await admin_client.get("/admin/tenants")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) >= 2


@pytest.mark.asyncio
async def test_rename_tenant(admin_client):
    resp = await admin_client.post("/admin/tenants", json={"name": "Old Name"})
    tid = resp.json()["id"]
    resp = await admin_client.put(f"/admin/tenants/{tid}", json={"name": "New Name"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"


@pytest.mark.asyncio
async def test_delete_tenant(admin_client):
    resp = await admin_client.post("/admin/tenants", json={"name": "ToDelete"})
    tid = resp.json()["id"]
    resp = await admin_client.delete(f"/admin/tenants/{tid}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_list_users(admin_client):
    resp = await admin_client.get("/admin/users")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_assign_user_tenant(admin_client):
    # Create tenant
    resp = await admin_client.post("/admin/tenants", json={"name": "AssignMe"})
    tid = resp.json()["id"]

    # List users to get a user id
    users_resp = await admin_client.get("/admin/users")
    users = users_resp.json()["items"]
    assert len(users) > 0
    uid = users[0]["id"]

    # Assign
    resp = await admin_client.put(f"/admin/users/{uid}/tenant", json={"tenant_id": tid})
    assert resp.status_code == 200
    assert resp.json()["tenant_id"] == tid

    # Unassign
    resp = await admin_client.put(f"/admin/users/{uid}/tenant", json={"tenant_id": None})
    assert resp.status_code == 200
    assert resp.json()["tenant_id"] is None


@pytest.mark.asyncio
async def test_crud_domain_rules(admin_client):
    # Create tenant first
    resp = await admin_client.post("/admin/tenants", json={"name": "DomainTenant"})
    tid = resp.json()["id"]

    # Create rule
    resp = await admin_client.post("/admin/domain-rules", json={"domain": "test.io", "tenant_id": tid})
    assert resp.status_code == 201
    data = resp.json()
    assert data["domain"] == "test.io"
    rid = data["id"]

    # List rules
    resp = await admin_client.get("/admin/domain-rules")
    assert resp.status_code == 200
    assert any(r["domain"] == "test.io" for r in resp.json()["items"])

    # Delete rule
    resp = await admin_client.delete(f"/admin/domain-rules/{rid}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_regular_user_gets_403(client):
    """Non-admin user should get 403 on admin endpoints."""
    resp = await client.get("/admin/tenants")
    assert resp.status_code == 403

    resp = await client.post("/admin/tenants", json={"name": "Nope"})
    assert resp.status_code == 403

    resp = await client.get("/admin/users")
    assert resp.status_code == 403

    resp = await client.get("/admin/domain-rules")
    assert resp.status_code == 403


# ── Share Analytics Tests ────────────────────────────────────────


@pytest.mark.asyncio
async def test_share_analytics_empty(admin_client):
    """Share analytics returns empty list when no views exist."""
    resp = await admin_client.get("/admin/share-analytics")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_share_analytics_summary_empty(admin_client):
    """Summary returns zeros when no views exist."""
    resp = await admin_client.get("/admin/share-analytics/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_views"] == 0
    assert data["unique_ips"] == 0
    assert data["top_platforms"] == []
    assert data["top_browsers"] == []
    assert data["top_os"] == []


@pytest.mark.asyncio
async def test_share_analytics_with_data(admin_client, async_engine, super_admin_user):
    """Share analytics returns data after inserting views."""
    session_factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as db:
        roast = Roast(
            user_id=super_admin_user.id,
            file_hash="d" * 64,
            share_id="anal1234",
            status=RoastStatus.READY,
        )
        db.add(roast)
        await db.commit()
        await db.refresh(roast)

        db.add(RoastView(
            roast_id=roast.id,
            share_id=roast.share_id,
            ip_address="1.2.3.4",
            platform="WhatsApp",
            os="iOS",
            browser="Safari",
        ))
        db.add(RoastView(
            roast_id=roast.id,
            share_id=roast.share_id,
            ip_address="5.6.7.8",
            platform="WhatsApp",
            os="Android",
            browser="Chrome",
        ))
        await db.commit()

    # List endpoint
    resp = await admin_client.get("/admin/share-analytics")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    assert data["items"][0]["share_id"] == "anal1234"

    # Filter by share_id
    resp = await admin_client.get("/admin/share-analytics?share_id=anal1234")
    assert resp.status_code == 200
    assert resp.json()["total"] == 2

    resp = await admin_client.get("/admin/share-analytics?share_id=nonexist")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0

    # Summary endpoint
    resp = await admin_client.get("/admin/share-analytics/summary")
    assert resp.status_code == 200
    summary = resp.json()
    assert summary["total_views"] == 2
    assert summary["unique_ips"] == 2


@pytest.mark.asyncio
async def test_share_analytics_requires_admin(client):
    """Non-admin user should get 403 on share-analytics."""
    resp = await client.get("/admin/share-analytics")
    assert resp.status_code == 403

    resp = await client.get("/admin/share-analytics/summary")
    assert resp.status_code == 403
