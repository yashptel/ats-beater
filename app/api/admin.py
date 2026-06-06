import math
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, distinct

from app.database.session import get_db
from app.dependencies import get_super_admin
from app.models.user import User
from app.models.tenant import Tenant, TenantDomainRule
from app.models.job import Job, JobStatus
from app.models.profile import Profile
from app.models.roast import Roast, RoastStatus
from app.models.token_usage import LLMRequest
from app.models.roast_view import RoastView
from app.exceptions import NotFoundError
from app.schemas.tenant import (
    TenantCreate,
    TenantUpdate,
    TenantResponse,
    DomainRuleCreate,
    DomainRuleResponse,
    AssignTenantRequest,
    UserAdminResponse,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def _paginate(items, total, page, size):
    """Standard pagination envelope."""
    return {
        "items": items,
        "total": total,
        "page": page,
        "pages": math.ceil(total / size) if total > 0 else 1,
        "limit": size,
    }


# ── Overview helpers ──────────────────────────────────────────────

def _estimate_cost(model_name: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost for a Gemini API call."""
    rates = {
        "gemini-3-flash-preview": {"input": 0.10, "output": 0.40},
        "gemini-3.1-pro-preview": {"input": 1.25, "output": 5.00},
    }
    r = rates.get(model_name, {"input": 0.50, "output": 1.50})
    return (input_tokens * r["input"] + output_tokens * r["output"]) / 1_000_000


async def _daily_counts(db: AsyncSession, model_class, now, days=7):
    """Return (labels, counts) for the last N days of created_at."""
    start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = (await db.execute(
        select(func.date(model_class.created_at), func.count(model_class.id))
        .where(model_class.created_at >= start)
        .group_by(func.date(model_class.created_at))
    )).all()
    by_date = {str(r[0]): r[1] for r in rows}
    labels, counts = [], []
    for i in range(days):
        d = start + timedelta(days=i)
        labels.append(d.strftime("%b %d"))
        counts.append(by_date.get(d.strftime("%Y-%m-%d"), 0))
    return labels, counts


# ── Overview ─────────────────────────────────────────────────────

@router.get("/overview")
async def admin_overview(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_super_admin),
):
    """Aggregate KPIs for the admin dashboard."""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    total_users = (await db.execute(select(func.count(User.id)))).scalar() or 0
    total_jobs = (await db.execute(select(func.count(Job.id)))).scalar() or 0
    completed_jobs = (await db.execute(
        select(func.count(Job.id)).where(Job.status == JobStatus.READY)
    )).scalar() or 0

    total_profiles = (await db.execute(
        select(func.count(Profile.id)).where(Profile.is_active.is_(True))
    )).scalar() or 0

    total_roasts = (await db.execute(
        select(func.count(Roast.id))
    )).scalar() or 0

    new_users_today = (await db.execute(
        select(func.count(User.id)).where(User.created_at >= today_start)
    )).scalar() or 0

    new_users_7d = (await db.execute(
        select(func.count(User.id)).where(User.created_at >= now - timedelta(days=7))
    )).scalar() or 0

    # ── Job status breakdown ──
    job_status_rows = (await db.execute(
        select(Job.status, func.count(Job.id)).group_by(Job.status)
    )).all()
    job_status_breakdown = {r[0].value if hasattr(r[0], 'value') else str(r[0]): r[1] for r in job_status_rows}

    # ── Roast status breakdown ──
    roast_status_rows = (await db.execute(
        select(Roast.status, func.count(Roast.id)).group_by(Roast.status)
    )).all()
    roast_status_breakdown = {r[0].value if hasattr(r[0], 'value') else str(r[0]): r[1] for r in roast_status_rows}

    # ── Conversion funnel (distinct users at each stage) ──
    users_with_profiles = (await db.execute(
        select(func.count(distinct(Profile.user_id))).where(Profile.is_active.is_(True))
    )).scalar() or 0
    users_with_jobs = (await db.execute(
        select(func.count(distinct(Job.user_id)))
    )).scalar() or 0
    users_with_ready = (await db.execute(
        select(func.count(distinct(Job.user_id))).where(Job.status == JobStatus.READY)
    )).scalar() or 0

    funnel = {
        "users": total_users,
        "profiles": users_with_profiles,
        "jobs": users_with_jobs,
        "ready_jobs": users_with_ready,
    }

    # ── LLM summary ──
    llm_totals = (await db.execute(
        select(
            func.count(LLMRequest.id),
            func.coalesce(func.sum(LLMRequest.input_tokens), 0),
            func.coalesce(func.sum(LLMRequest.output_tokens), 0),
            func.coalesce(func.sum(LLMRequest.cached_tokens), 0),
            func.coalesce(func.avg(LLMRequest.response_time_ms), 0),
        )
    )).one()
    total_llm = llm_totals[0] or 0
    success_count = (await db.execute(
        select(func.count(LLMRequest.id)).where(LLMRequest.success.is_(True))
    )).scalar() or 0

    llm_by_model_rows = (await db.execute(
        select(
            LLMRequest.provider,
            LLMRequest.model_name,
            func.count(LLMRequest.id),
            func.coalesce(func.sum(LLMRequest.input_tokens), 0),
            func.coalesce(func.sum(LLMRequest.output_tokens), 0),
            func.coalesce(func.sum(LLMRequest.cached_tokens), 0),
            func.coalesce(func.avg(LLMRequest.response_time_ms), 0),
        ).group_by(LLMRequest.provider, LLMRequest.model_name)
    )).all()

    by_model = []
    total_estimated_cost = 0.0
    for provider, model_name, req_count, inp, outp, cached, avg_ms in llm_by_model_rows:
        cost = _estimate_cost(model_name, inp, outp)
        total_estimated_cost += cost
        by_model.append({
            "provider": provider,
            "model_name": model_name,
            "request_count": req_count,
            "input_tokens": inp,
            "output_tokens": outp,
            "cached_tokens": cached,
            "avg_response_time_ms": round(avg_ms),
            "estimated_cost_usd": round(cost, 4),
        })

    llm_summary = {
        "total_requests": total_llm,
        "total_input_tokens": llm_totals[1],
        "total_output_tokens": llm_totals[2],
        "total_cached_tokens": llm_totals[3],
        "avg_response_time_ms": round(llm_totals[4]),
        "success_rate_pct": round((success_count / total_llm) * 100, 1) if total_llm > 0 else 100.0,
        "total_estimated_cost_usd": round(total_estimated_cost, 4),
        "by_model": by_model,
    }

    # ── 7-day trends ──
    user_labels, user_counts = await _daily_counts(db, User, now)
    _, profile_counts = await _daily_counts(db, Profile, now)
    _, job_counts = await _daily_counts(db, Job, now)
    _, roast_counts = await _daily_counts(db, Roast, now)

    trends = {
        "labels": user_labels,
        "users": user_counts,
        "profiles": profile_counts,
        "jobs": job_counts,
        "roasts": roast_counts,
    }

    return {
        "total_users": total_users,
        "total_jobs": total_jobs,
        "completed_jobs": completed_jobs,
        "total_profiles": total_profiles,
        "total_roasts": total_roasts,
        "new_users_today": new_users_today,
        "new_users_7d": new_users_7d,
        "job_status_breakdown": job_status_breakdown,
        "roast_status_breakdown": roast_status_breakdown,
        "funnel": funnel,
        "llm_summary": llm_summary,
        "trends": trends,
    }


# ── Tenants ──────────────────────────────────────────────────────

@router.post("/tenants", response_model=TenantResponse, status_code=201)
async def create_tenant(
    body: TenantCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_super_admin),
):
    tenant = Tenant(name=body.name)
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    return TenantResponse(
        id=tenant.id, name=tenant.name, user_count=0, created_at=tenant.created_at
    )


@router.get("/tenants")
async def list_tenants(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    search: str = Query("", max_length=100),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_super_admin),
):
    base = (
        select(Tenant, func.count(User.id).label("user_count"))
        .outerjoin(User, User.tenant_id == Tenant.id)
        .group_by(Tenant.id)
    )
    if search:
        base = base.where(Tenant.name.ilike(f"%{search}%"))

    # Total count
    count_q = select(func.count()).select_from(
        select(Tenant.id).where(Tenant.name.ilike(f"%{search}%") if search else True).subquery()
    )
    count_result = await db.execute(count_q)
    total = count_result.scalar() or 0

    offset = (page - 1) * size
    rows = (await db.execute(base.order_by(Tenant.name).offset(offset).limit(size))).all()
    items = [
        {
            "id": t.id, "name": t.name, "user_count": count,
            "created_at": t.created_at.isoformat(),
        }
        for t, count in rows
    ]
    return _paginate(items, total, page, size)


@router.put("/tenants/{tenant_id}", response_model=TenantResponse)
async def rename_tenant(
    tenant_id: str,
    body: TenantUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_super_admin),
):
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise NotFoundError(f"Tenant {tenant_id} not found")
    tenant.name = body.name
    await db.commit()
    await db.refresh(tenant)
    count_result = await db.execute(
        select(func.count(User.id)).where(User.tenant_id == tenant_id)
    )
    user_count = count_result.scalar() or 0
    return TenantResponse(
        id=tenant.id, name=tenant.name, user_count=user_count, created_at=tenant.created_at
    )


@router.delete("/tenants/{tenant_id}", status_code=204)
async def delete_tenant(
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_super_admin),
):
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise NotFoundError(f"Tenant {tenant_id} not found")
    await db.delete(tenant)
    await db.commit()


# ── Users ────────────────────────────────────────────────────────

@router.get("/users")
async def list_users(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    search: str = Query("", max_length=100),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_super_admin),
):
    base = (
        select(
            User,
            Tenant.name.label("tenant_name"),
            func.count(Job.id).label("job_count"),
        )
        .outerjoin(Tenant, User.tenant_id == Tenant.id)
        .outerjoin(Job, Job.user_id == User.id)
        .group_by(User.id, Tenant.name)
    )
    if search:
        pattern = f"%{search}%"
        base = base.where(or_(User.email.ilike(pattern), User.name.ilike(pattern)))

    # Total count
    count_base = select(func.count(User.id))
    if search:
        pattern = f"%{search}%"
        count_base = count_base.where(or_(User.email.ilike(pattern), User.name.ilike(pattern)))
    count_result = await db.execute(count_base)
    total = count_result.scalar() or 0

    offset = (page - 1) * size
    rows = (await db.execute(
        base.order_by(User.created_at.desc()).offset(offset).limit(size)
    )).all()

    items = [
        {
            "id": u.id, "email": u.email, "name": u.name,
            "is_super_admin": u.is_super_admin,
            "tenant_id": u.tenant_id, "tenant_name": tname,
            "job_count": job_count,
            "created_at": u.created_at.isoformat(),
        }
        for u, tname, job_count in rows
    ]
    return _paginate(items, total, page, size)


@router.put("/users/{user_id}/tenant")
async def assign_user_tenant(
    user_id: str,
    body: AssignTenantRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_super_admin),
):
    user = await db.get(User, user_id)
    if not user:
        raise NotFoundError(f"User {user_id} not found")
    if body.tenant_id:
        tenant = await db.get(Tenant, body.tenant_id)
        if not tenant:
            raise NotFoundError(f"Tenant {body.tenant_id} not found")
    user.tenant_id = body.tenant_id
    await db.commit()
    return {"status": "ok", "user_id": user_id, "tenant_id": body.tenant_id}


# ── Domain Rules ─────────────────────────────────────────────────

@router.get("/domain-rules")
async def list_domain_rules(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    search: str = Query("", max_length=100),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_super_admin),
):
    base = (
        select(TenantDomainRule, Tenant.name.label("tenant_name"))
        .join(Tenant, TenantDomainRule.tenant_id == Tenant.id)
    )
    if search:
        pattern = f"%{search}%"
        base = base.where(
            or_(TenantDomainRule.domain.ilike(pattern), Tenant.name.ilike(pattern))
        )

    count_base = select(func.count(TenantDomainRule.id))
    if search:
        pattern = f"%{search}%"
        count_base = count_base.join(Tenant, TenantDomainRule.tenant_id == Tenant.id).where(
            or_(TenantDomainRule.domain.ilike(pattern), Tenant.name.ilike(pattern))
        )
    count_result = await db.execute(count_base)
    total = count_result.scalar() or 0

    offset = (page - 1) * size
    rows = (await db.execute(
        base.order_by(TenantDomainRule.domain).offset(offset).limit(size)
    )).all()
    items = [
        {
            "id": rule.id, "domain": rule.domain,
            "tenant_id": rule.tenant_id, "tenant_name": tname,
            "created_at": rule.created_at.isoformat(),
        }
        for rule, tname in rows
    ]
    return _paginate(items, total, page, size)


@router.post("/domain-rules", response_model=DomainRuleResponse, status_code=201)
async def create_domain_rule(
    body: DomainRuleCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_super_admin),
):
    tenant = await db.get(Tenant, body.tenant_id)
    if not tenant:
        raise NotFoundError(f"Tenant {body.tenant_id} not found")
    existing = await db.execute(
        select(TenantDomainRule).where(TenantDomainRule.domain == body.domain)
    )
    if existing.scalar_one_or_none():
        raise ValueError(f"Domain rule for '{body.domain}' already exists")
    rule = TenantDomainRule(domain=body.domain, tenant_id=body.tenant_id)
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return DomainRuleResponse(
        id=rule.id,
        domain=rule.domain,
        tenant_id=rule.tenant_id,
        tenant_name=tenant.name,
        created_at=rule.created_at,
    )


@router.delete("/domain-rules/{rule_id}", status_code=204)
async def delete_domain_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_super_admin),
):
    rule = await db.get(TenantDomainRule, rule_id)
    if not rule:
        raise NotFoundError(f"Domain rule {rule_id} not found")
    await db.delete(rule)
    await db.commit()


# ── LLM Requests ────────────────────────────────────────────────

@router.get("/llm-requests")
async def list_llm_requests(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    purpose: str = Query("", max_length=50),
    provider: str = Query("", max_length=40),
    model_name: str = Query("", max_length=100),
    success: bool | None = Query(None),
    search: str = Query("", max_length=100),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_super_admin),
):
    """Paginated list of LLM API calls with filters."""
    base = (
        select(LLMRequest, User.email.label("user_email"))
        .outerjoin(User, LLMRequest.user_id == User.id)
    )
    count_base = select(func.count(LLMRequest.id))

    # Filters
    if purpose:
        base = base.where(LLMRequest.purpose == purpose)
        count_base = count_base.where(LLMRequest.purpose == purpose)
    if provider:
        base = base.where(LLMRequest.provider == provider)
        count_base = count_base.where(LLMRequest.provider == provider)
    if model_name:
        base = base.where(LLMRequest.model_name == model_name)
        count_base = count_base.where(LLMRequest.model_name == model_name)
    if success is not None:
        base = base.where(LLMRequest.success == success)
        count_base = count_base.where(LLMRequest.success == success)
    if search:
        pattern = f"%{search}%"
        base = base.where(User.email.ilike(pattern))
        count_base = count_base.join(User, LLMRequest.user_id == User.id).where(
            User.email.ilike(pattern)
        )

    count_result = await db.execute(count_base)
    total = count_result.scalar() or 0

    offset = (page - 1) * size
    rows = (await db.execute(
        base.order_by(LLMRequest.created_at.desc()).offset(offset).limit(size)
    )).all()

    items = [
        {
            "id": req.id,
            "user_email": email,
            "purpose": req.purpose,
            "reference_id": req.reference_id,
            "provider": req.provider,
            "model_name": req.model_name,
            "input_tokens": req.input_tokens,
            "output_tokens": req.output_tokens,
            "total_tokens": req.total_tokens,
            "cached_tokens": req.cached_tokens,
            "response_time_ms": req.response_time_ms,
            "success": req.success,
            "error_message": req.error_message,
            "created_at": req.created_at.isoformat(),
        }
        for req, email in rows
    ]
    return _paginate(items, total, page, size)


# ── Share Analytics ──────────────────────────────────────────────

@router.get("/share-analytics")
async def list_share_analytics(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    share_id: str = Query("", max_length=20),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_super_admin),
):
    """Paginated list of roast share link views."""
    base = select(RoastView)
    count_base = select(func.count(RoastView.id))

    if share_id:
        base = base.where(RoastView.share_id == share_id)
        count_base = count_base.where(RoastView.share_id == share_id)

    total = (await db.execute(count_base)).scalar() or 0

    offset = (page - 1) * size
    rows = (await db.execute(
        base.order_by(RoastView.created_at.desc()).offset(offset).limit(size)
    )).scalars().all()

    items = [
        {
            "id": v.id,
            "roast_id": v.roast_id,
            "share_id": v.share_id,
            "ip_address": v.ip_address,
            "user_agent": v.user_agent,
            "referer": v.referer,
            "platform": v.platform,
            "os": v.os,
            "browser": v.browser,
            "created_at": v.created_at.isoformat(),
        }
        for v in rows
    ]
    return _paginate(items, total, page, size)


@router.get("/share-analytics/summary")
async def share_analytics_summary(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_super_admin),
):
    """Aggregate stats for share link views."""
    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)

    total_views = (await db.execute(select(func.count(RoastView.id)))).scalar() or 0
    unique_ips = (await db.execute(
        select(func.count(distinct(RoastView.ip_address)))
    )).scalar() or 0

    # Top platforms
    platform_rows = (await db.execute(
        select(RoastView.platform, func.count(RoastView.id))
        .where(RoastView.platform.isnot(None))
        .group_by(RoastView.platform)
        .order_by(func.count(RoastView.id).desc())
        .limit(10)
    )).all()
    top_platforms = [{"name": r[0], "count": r[1]} for r in platform_rows]

    # Top browsers
    browser_rows = (await db.execute(
        select(RoastView.browser, func.count(RoastView.id))
        .where(RoastView.browser.isnot(None))
        .group_by(RoastView.browser)
        .order_by(func.count(RoastView.id).desc())
        .limit(10)
    )).all()
    top_browsers = [{"name": r[0], "count": r[1]} for r in browser_rows]

    # Top OS
    os_rows = (await db.execute(
        select(RoastView.os, func.count(RoastView.id))
        .where(RoastView.os.isnot(None))
        .group_by(RoastView.os)
        .order_by(func.count(RoastView.id).desc())
        .limit(10)
    )).all()
    top_os = [{"name": r[0], "count": r[1]} for r in os_rows]

    # Views by day (last 30 days)
    day_rows = (await db.execute(
        select(func.date(RoastView.created_at), func.count(RoastView.id))
        .where(RoastView.created_at >= thirty_days_ago)
        .group_by(func.date(RoastView.created_at))
        .order_by(func.date(RoastView.created_at))
    )).all()
    views_by_day = [{"date": str(r[0]), "count": r[1]} for r in day_rows]

    return {
        "total_views": total_views,
        "unique_ips": unique_ips,
        "top_platforms": top_platforms,
        "top_browsers": top_browsers,
        "top_os": top_os,
        "views_by_day": views_by_day,
    }
