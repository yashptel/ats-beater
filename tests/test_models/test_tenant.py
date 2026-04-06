import pytest
from sqlalchemy import select
from app.models.tenant import Tenant, TenantDomainRule


@pytest.mark.asyncio
async def test_create_tenant(db_session):
    t = Tenant(name="Acme Corp")
    db_session.add(t)
    await db_session.commit()
    await db_session.refresh(t)
    assert t.id is not None
    assert t.name == "Acme Corp"


@pytest.mark.asyncio
async def test_create_domain_rule(db_session):
    t = Tenant(name="Google")
    db_session.add(t)
    await db_session.commit()
    await db_session.refresh(t)

    rule = TenantDomainRule(domain="google.com", tenant_id=t.id)
    db_session.add(rule)
    await db_session.commit()
    await db_session.refresh(rule)

    assert rule.id is not None
    assert rule.domain == "google.com"
    assert rule.tenant_id == t.id


@pytest.mark.asyncio
async def test_domain_uniqueness(db_session):
    t = Tenant(name="Corp A")
    db_session.add(t)
    await db_session.commit()
    await db_session.refresh(t)

    r1 = TenantDomainRule(domain="unique.com", tenant_id=t.id)
    db_session.add(r1)
    await db_session.commit()

    r2 = TenantDomainRule(domain="unique.com", tenant_id=t.id)
    db_session.add(r2)
    with pytest.raises(Exception):  # IntegrityError
        await db_session.commit()


@pytest.mark.asyncio
async def test_cascade_delete(db_session):
    t = Tenant(name="Deletable")
    db_session.add(t)
    await db_session.commit()
    await db_session.refresh(t)

    rule = TenantDomainRule(domain="deletable.com", tenant_id=t.id)
    db_session.add(rule)
    await db_session.commit()

    await db_session.delete(t)
    await db_session.commit()

    result = await db_session.execute(select(TenantDomainRule).where(TenantDomainRule.domain == "deletable.com"))
    assert result.scalar_one_or_none() is None
