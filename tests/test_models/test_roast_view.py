import pytest
from sqlalchemy import select
from app.models.roast import Roast, RoastStatus
from app.models.roast_view import RoastView


@pytest.mark.asyncio
async def test_create_roast_view(db_session, test_user):
    """RoastView CRUD round-trip."""
    roast = Roast(
        user_id=test_user.id,
        file_hash="a" * 64,
        share_id="view1234",
        status=RoastStatus.READY,
    )
    db_session.add(roast)
    await db_session.commit()
    await db_session.refresh(roast)

    view = RoastView(
        roast_id=roast.id,
        share_id=roast.share_id,
        ip_address="192.168.1.1",
        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)",
        referer="https://t.co/abc123",
        platform="Twitter",
        os="iOS",
        browser="Safari",
    )
    db_session.add(view)
    await db_session.commit()
    await db_session.refresh(view)

    assert view.id is not None
    assert view.roast_id == roast.id
    assert view.share_id == "view1234"
    assert view.ip_address == "192.168.1.1"
    assert view.platform == "Twitter"
    assert view.os == "iOS"
    assert view.browser == "Safari"
    assert view.created_at is not None


@pytest.mark.asyncio
async def test_roast_view_nullable_fields(db_session, test_user):
    """RoastView with only required fields."""
    roast = Roast(
        user_id=test_user.id,
        file_hash="b" * 64,
        share_id="view5678",
        status=RoastStatus.READY,
    )
    db_session.add(roast)
    await db_session.commit()
    await db_session.refresh(roast)

    view = RoastView(roast_id=roast.id, share_id=roast.share_id)
    db_session.add(view)
    await db_session.commit()
    await db_session.refresh(view)

    assert view.id is not None
    assert view.ip_address is None
    assert view.user_agent is None
    assert view.platform is None
    assert view.os is None
    assert view.browser is None


@pytest.mark.asyncio
async def test_roast_view_multiple_views(db_session, test_user):
    """Multiple views can be tracked for a single roast."""
    roast = Roast(
        user_id=test_user.id,
        file_hash="c" * 64,
        share_id="casc1234",
        status=RoastStatus.READY,
    )
    db_session.add(roast)
    await db_session.commit()
    await db_session.refresh(roast)

    for i in range(3):
        db_session.add(RoastView(
            roast_id=roast.id,
            share_id=roast.share_id,
            ip_address=f"10.0.0.{i}",
        ))
    await db_session.commit()

    result = await db_session.execute(
        select(RoastView).where(RoastView.roast_id == roast.id)
    )
    views = result.scalars().all()
    assert len(views) == 3
    ips = {v.ip_address for v in views}
    assert ips == {"10.0.0.0", "10.0.0.1", "10.0.0.2"}
