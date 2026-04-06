import pytest
from datetime import date
from app.models.credit import UserCredit, CreditPack, TimePassTier, PromoCode, PromoType


@pytest.fixture
async def user_credit(db_session, test_user):
    uc = UserCredit(
        user_id=test_user.id,
        balance=10,
        daily_free_used=0,
        daily_free_reset_date=date.today(),
    )
    db_session.add(uc)
    await db_session.commit()
    return uc


@pytest.fixture
async def admin_credit(db_session, super_admin_user):
    uc = UserCredit(
        user_id=super_admin_user.id,
        balance=0,
        daily_free_used=0,
        daily_free_reset_date=date.today(),
    )
    db_session.add(uc)
    await db_session.commit()
    return uc


@pytest.fixture
async def sample_pack(db_session):
    pack = CreditPack(name="Starter", credits=10, price_paise=9900)
    db_session.add(pack)
    await db_session.commit()
    await db_session.refresh(pack)
    return pack


@pytest.fixture
async def sample_tier(db_session):
    tier = TimePassTier(name="Weekly", duration_days=7, price_paise=19900)
    db_session.add(tier)
    await db_session.commit()
    await db_session.refresh(tier)
    return tier


@pytest.fixture
async def sample_promo(db_session):
    promo = PromoCode(code="TEST10", type=PromoType.CREDITS, value=10)
    db_session.add(promo)
    await db_session.commit()
    await db_session.refresh(promo)
    return promo


# ── User-facing credit routes ──

@pytest.mark.asyncio
async def test_get_packs_public(client, sample_pack, sample_tier):
    resp = await client.get("/credits/packs")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["credit_packs"]) >= 1
    assert len(data["time_passes"]) >= 1


@pytest.mark.asyncio
async def test_get_balance(client, user_credit):
    resp = await client.get("/credits/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["balance"] == 10
    assert "daily_free_remaining" in data


@pytest.mark.asyncio
async def test_get_history_empty(client, user_credit):
    resp = await client.get("/credits/history")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_redeem_promo(client, user_credit, sample_promo):
    resp = await client.post("/credits/redeem-promo", json={"code": "TEST10"})
    assert resp.status_code == 200
    data = resp.json()
    assert "message" in data
    assert data["balance"]["balance"] == 20  # 10 existing + 10 promo


@pytest.mark.asyncio
async def test_redeem_promo_invalid(client, user_credit):
    resp = await client.post("/credits/redeem-promo", json={"code": "INVALID"})
    assert resp.status_code == 400


# ── Admin credit routes ──

@pytest.mark.asyncio
async def test_admin_create_credit_pack(admin_client):
    resp = await admin_client.post("/admin/credit-packs", json={
        "name": "Pro Pack", "credits": 50, "price_paise": 39900,
    })
    assert resp.status_code == 201
    assert resp.json()["name"] == "Pro Pack"


@pytest.mark.asyncio
async def test_admin_list_credit_packs(admin_client):
    await admin_client.post("/admin/credit-packs", json={
        "name": "Pack A", "credits": 5, "price_paise": 4900,
    })
    resp = await admin_client.get("/admin/credit-packs")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_admin_update_credit_pack(admin_client):
    resp = await admin_client.post("/admin/credit-packs", json={
        "name": "Old", "credits": 5, "price_paise": 4900,
    })
    pid = resp.json()["id"]
    resp = await admin_client.put(f"/admin/credit-packs/{pid}", json={"name": "New"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "New"


@pytest.mark.asyncio
async def test_admin_delete_credit_pack(admin_client):
    resp = await admin_client.post("/admin/credit-packs", json={
        "name": "Gone", "credits": 1, "price_paise": 100,
    })
    pid = resp.json()["id"]
    resp = await admin_client.delete(f"/admin/credit-packs/{pid}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_admin_create_time_pass_tier(admin_client):
    resp = await admin_client.post("/admin/time-pass-tiers", json={
        "name": "Monthly", "duration_days": 30, "price_paise": 49900,
    })
    assert resp.status_code == 201
    assert resp.json()["duration_days"] == 30


@pytest.mark.asyncio
async def test_admin_create_promo_code(admin_client):
    resp = await admin_client.post("/admin/promo-codes", json={
        "code": "ADMIN50", "type": "CREDITS", "value": 50,
    })
    assert resp.status_code == 201
    assert resp.json()["code"] == "ADMIN50"


@pytest.mark.asyncio
async def test_admin_grant_credits(admin_client, admin_credit, super_admin_user):
    resp = await admin_client.post("/admin/credits/grant", json={
        "user_id": super_admin_user.id, "amount": 25, "description": "Test grant",
    })
    assert resp.status_code == 200
    assert resp.json()["new_balance"] == 25


@pytest.mark.asyncio
async def test_admin_list_transactions(admin_client):
    resp = await admin_client.get("/admin/transactions")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data


# ── Pagination envelope on existing endpoints ──

@pytest.mark.asyncio
async def test_admin_tenants_pagination(admin_client):
    await admin_client.post("/admin/tenants", json={"name": "PagTenant"})
    resp = await admin_client.get("/admin/tenants?page=1&size=10")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert "pages" in data


@pytest.mark.asyncio
async def test_admin_users_pagination(admin_client):
    resp = await admin_client.get("/admin/users?page=1&size=10&search=admin")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_admin_domain_rules_pagination(admin_client):
    resp = await admin_client.get("/admin/domain-rules?page=1&size=10")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data


@pytest.mark.asyncio
async def test_regular_user_cannot_access_credit_admin(client):
    resp = await client.get("/admin/credit-packs")
    assert resp.status_code == 403

    resp = await client.post("/admin/credit-packs", json={
        "name": "Nope", "credits": 1, "price_paise": 100,
    })
    assert resp.status_code == 403
