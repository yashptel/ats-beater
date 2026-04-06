import math
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, func, or_, distinct

from app.database.session import get_db
from app.dependencies import get_super_admin
from app.models.user import User
from app.models.tenant import Tenant, TenantDomainRule
from app.models.job import Job, JobStatus
from app.models.profile import Profile
from app.models.roast import Roast, RoastStatus
from app.models.credit import (
    CreditPack, TimePassTier, PromoCode, CreditTransaction,
    UserCredit, UserTimePass, TransactionType,
)
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
from app.schemas.credit import (
    CreditPackCreate, CreditPackUpdate, CreditPackResponse,
    TimePassTierCreate, TimePassTierUpdate, TimePassTierResponse,
    PromoCodeCreate, PromoCodeUpdate, PromoCodeResponse,
    AdminGrantRequest, AdminTransactionResponse,
)
from app.services.credit.service import CreditService
from app.config import get_settings

router = APIRouter(prefix="/admin", tags=["admin"])
credit_service = CreditService()


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

    # ── Existing KPIs ──
    total_users = (await db.execute(select(func.count(User.id)))).scalar() or 0
    total_jobs = (await db.execute(select(func.count(Job.id)))).scalar() or 0
    completed_jobs = (await db.execute(
        select(func.count(Job.id)).where(Job.status == JobStatus.READY)
    )).scalar() or 0

    total_purchase_txns = (await db.execute(
        select(func.count(CreditTransaction.id)).where(
            CreditTransaction.type.in_([
                TransactionType.CREDIT_PURCHASE,
                TransactionType.TIME_PASS_PURCHASE,
            ])
        )
    )).scalar() or 0

    active_passes = (await db.execute(
        select(func.count(UserTimePass.id)).where(
            UserTimePass.starts_at <= now,
            UserTimePass.expires_at > now,
        )
    )).scalar() or 0

    consumed_today = (await db.execute(
        select(func.count(CreditTransaction.id)).where(
            CreditTransaction.type == TransactionType.CONSUMPTION,
            CreditTransaction.created_at >= today_start,
        )
    )).scalar() or 0

    # ── New KPIs ──
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
            LLMRequest.model_name,
            func.count(LLMRequest.id),
            func.coalesce(func.sum(LLMRequest.input_tokens), 0),
            func.coalesce(func.sum(LLMRequest.output_tokens), 0),
            func.coalesce(func.sum(LLMRequest.cached_tokens), 0),
            func.coalesce(func.avg(LLMRequest.response_time_ms), 0),
        ).group_by(LLMRequest.model_name)
    )).all()

    by_model = []
    total_estimated_cost = 0.0
    for model_name, req_count, inp, outp, cached, avg_ms in llm_by_model_rows:
        cost = _estimate_cost(model_name, inp, outp)
        total_estimated_cost += cost
        by_model.append({
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

    # ── Recent activity (unchanged) ──
    recent_result = await db.execute(
        select(CreditTransaction, User.email)
        .join(User, CreditTransaction.user_id == User.id)
        .order_by(CreditTransaction.created_at.desc())
        .limit(10)
    )
    recent = [
        {
            "id": txn.id, "user_email": email,
            "amount": txn.amount, "type": txn.type.value,
            "description": txn.description,
            "created_at": txn.created_at.isoformat(),
        }
        for txn, email in recent_result.all()
    ]

    return {
        "total_users": total_users,
        "total_jobs": total_jobs,
        "completed_jobs": completed_jobs,
        "total_purchase_txns": total_purchase_txns,
        "active_time_passes": active_passes,
        "consumed_today": consumed_today,
        "total_profiles": total_profiles,
        "total_roasts": total_roasts,
        "new_users_today": new_users_today,
        "new_users_7d": new_users_7d,
        "job_status_breakdown": job_status_breakdown,
        "roast_status_breakdown": roast_status_breakdown,
        "funnel": funnel,
        "llm_summary": llm_summary,
        "trends": trends,
        "recent_activity": recent,
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
    now = datetime.now(timezone.utc)
    settings = get_settings()

    base = (
        select(
            User,
            Tenant.name.label("tenant_name"),
            UserCredit.balance,
            UserCredit.daily_free_used,
            func.count(Job.id).label("job_count"),
        )
        .outerjoin(Tenant, User.tenant_id == Tenant.id)
        .outerjoin(UserCredit, UserCredit.user_id == User.id)
        .outerjoin(Job, Job.user_id == User.id)
        .group_by(User.id, Tenant.name, UserCredit.balance, UserCredit.daily_free_used)
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

    # Batch-fetch active time passes for users in this page
    user_ids = [row[0].id for row in rows]
    active_passes = {}
    if user_ids:
        tp_result = await db.execute(
            select(UserTimePass, TimePassTier.name)
            .join(TimePassTier, UserTimePass.tier_id == TimePassTier.id)
            .where(
                UserTimePass.user_id.in_(user_ids),
                UserTimePass.starts_at <= now,
                UserTimePass.expires_at > now,
            )
            .order_by(UserTimePass.expires_at.desc())
        )
        for utp, tier_name in tp_result.all():
            if utp.user_id not in active_passes:
                active_passes[utp.user_id] = {
                    "tier_name": tier_name,
                    "expires_at": utp.expires_at.isoformat(),
                }

    items = [
        {
            "id": u.id, "email": u.email, "name": u.name,
            "is_super_admin": u.is_super_admin,
            "tenant_id": u.tenant_id, "tenant_name": tname,
            "balance": balance or 0,
            "daily_free_remaining": max(0, settings.DAILY_FREE_CREDITS - (daily_used or 0)),
            "job_count": job_count,
            "active_time_pass": active_passes.get(u.id),
            "created_at": u.created_at.isoformat(),
        }
        for u, tname, balance, daily_used, job_count in rows
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


# ── Credit Packs ─────────────────────────────────────────────────

@router.get("/credit-packs")
async def list_credit_packs(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    search: str = Query("", max_length=100),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_super_admin),
):
    base = select(CreditPack)
    if search:
        base = base.where(CreditPack.name.ilike(f"%{search}%"))

    count_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = count_result.scalar() or 0

    offset = (page - 1) * size
    result = await db.execute(
        base.order_by(CreditPack.sort_order, CreditPack.id).offset(offset).limit(size)
    )
    items = [
        {
            "id": p.id, "name": p.name, "credits": p.credits,
            "price_paise": p.price_paise, "is_active": p.is_active,
            "sort_order": p.sort_order, "created_at": p.created_at.isoformat(),
        }
        for p in result.scalars().all()
    ]
    return _paginate(items, total, page, size)


@router.post("/credit-packs", status_code=201)
async def create_credit_pack(
    body: CreditPackCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_super_admin),
):
    pack = CreditPack(**body.model_dump())
    db.add(pack)
    await db.commit()
    await db.refresh(pack)
    return {
        "id": pack.id, "name": pack.name, "credits": pack.credits,
        "price_paise": pack.price_paise, "is_active": pack.is_active,
        "sort_order": pack.sort_order, "created_at": pack.created_at.isoformat(),
    }


@router.put("/credit-packs/{pack_id}")
async def update_credit_pack(
    pack_id: int,
    body: CreditPackUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_super_admin),
):
    pack = await db.get(CreditPack, pack_id)
    if not pack:
        raise NotFoundError(f"Credit pack {pack_id} not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(pack, field, value)
    await db.commit()
    await db.refresh(pack)
    return {
        "id": pack.id, "name": pack.name, "credits": pack.credits,
        "price_paise": pack.price_paise, "is_active": pack.is_active,
        "sort_order": pack.sort_order, "created_at": pack.created_at.isoformat(),
    }


@router.delete("/credit-packs/{pack_id}", status_code=204)
async def delete_credit_pack(
    pack_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_super_admin),
):
    pack = await db.get(CreditPack, pack_id)
    if not pack:
        raise NotFoundError(f"Credit pack {pack_id} not found")
    await db.delete(pack)
    await db.commit()


# ── Time Pass Tiers ──────────────────────────────────────────────

@router.get("/time-pass-tiers")
async def list_time_pass_tiers(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    search: str = Query("", max_length=100),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_super_admin),
):
    base = select(TimePassTier)
    if search:
        base = base.where(TimePassTier.name.ilike(f"%{search}%"))

    count_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = count_result.scalar() or 0

    offset = (page - 1) * size
    result = await db.execute(
        base.order_by(TimePassTier.sort_order, TimePassTier.id).offset(offset).limit(size)
    )
    items = [
        {
            "id": t.id, "name": t.name, "duration_days": t.duration_days,
            "price_paise": t.price_paise, "is_active": t.is_active,
            "sort_order": t.sort_order, "created_at": t.created_at.isoformat(),
        }
        for t in result.scalars().all()
    ]
    return _paginate(items, total, page, size)


@router.post("/time-pass-tiers", status_code=201)
async def create_time_pass_tier(
    body: TimePassTierCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_super_admin),
):
    tier = TimePassTier(**body.model_dump())
    db.add(tier)
    await db.commit()
    await db.refresh(tier)
    return {
        "id": tier.id, "name": tier.name, "duration_days": tier.duration_days,
        "price_paise": tier.price_paise, "is_active": tier.is_active,
        "sort_order": tier.sort_order, "created_at": tier.created_at.isoformat(),
    }


@router.put("/time-pass-tiers/{tier_id}")
async def update_time_pass_tier(
    tier_id: int,
    body: TimePassTierUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_super_admin),
):
    tier = await db.get(TimePassTier, tier_id)
    if not tier:
        raise NotFoundError(f"Time pass tier {tier_id} not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(tier, field, value)
    await db.commit()
    await db.refresh(tier)
    return {
        "id": tier.id, "name": tier.name, "duration_days": tier.duration_days,
        "price_paise": tier.price_paise, "is_active": tier.is_active,
        "sort_order": tier.sort_order, "created_at": tier.created_at.isoformat(),
    }


@router.delete("/time-pass-tiers/{tier_id}", status_code=204)
async def delete_time_pass_tier(
    tier_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_super_admin),
):
    tier = await db.get(TimePassTier, tier_id)
    if not tier:
        raise NotFoundError(f"Time pass tier {tier_id} not found")
    try:
        await db.delete(tier)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ValueError(
            f"Cannot delete tier '{tier.name}' — it has associated user time passes. "
            "Deactivate it instead."
        )


# ── Promo Codes ──────────────────────────────────────────────────

@router.get("/promo-codes")
async def list_promo_codes(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    search: str = Query("", max_length=100),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_super_admin),
):
    base = select(PromoCode)
    if search:
        base = base.where(PromoCode.code.ilike(f"%{search}%"))

    count_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = count_result.scalar() or 0

    offset = (page - 1) * size
    result = await db.execute(
        base.order_by(PromoCode.created_at.desc()).offset(offset).limit(size)
    )
    items = [
        {
            "id": p.id, "code": p.code, "type": p.type.value,
            "value": p.value, "max_redemptions": p.max_redemptions,
            "current_redemptions": p.current_redemptions,
            "is_active": p.is_active,
            "expires_at": p.expires_at.isoformat() if p.expires_at else None,
            "created_at": p.created_at.isoformat(),
        }
        for p in result.scalars().all()
    ]
    return _paginate(items, total, page, size)


@router.post("/promo-codes", status_code=201)
async def create_promo_code(
    body: PromoCodeCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_super_admin),
):
    # Check uniqueness
    existing = await db.execute(
        select(PromoCode).where(PromoCode.code == body.code)
    )
    if existing.scalar_one_or_none():
        raise ValueError(f"Promo code '{body.code}' already exists")

    promo = PromoCode(**body.model_dump())
    db.add(promo)
    await db.commit()
    await db.refresh(promo)
    return {
        "id": promo.id, "code": promo.code, "type": promo.type.value,
        "value": promo.value, "max_redemptions": promo.max_redemptions,
        "current_redemptions": promo.current_redemptions,
        "is_active": promo.is_active,
        "expires_at": promo.expires_at.isoformat() if promo.expires_at else None,
        "created_at": promo.created_at.isoformat(),
    }


@router.put("/promo-codes/{promo_id}")
async def update_promo_code(
    promo_id: int,
    body: PromoCodeUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_super_admin),
):
    promo = await db.get(PromoCode, promo_id)
    if not promo:
        raise NotFoundError(f"Promo code {promo_id} not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(promo, field, value)
    await db.commit()
    await db.refresh(promo)
    return {
        "id": promo.id, "code": promo.code, "type": promo.type.value,
        "value": promo.value, "max_redemptions": promo.max_redemptions,
        "current_redemptions": promo.current_redemptions,
        "is_active": promo.is_active,
        "expires_at": promo.expires_at.isoformat() if promo.expires_at else None,
        "created_at": promo.created_at.isoformat(),
    }


@router.delete("/promo-codes/{promo_id}", status_code=204)
async def delete_promo_code(
    promo_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_super_admin),
):
    promo = await db.get(PromoCode, promo_id)
    if not promo:
        raise NotFoundError(f"Promo code {promo_id} not found")
    await db.delete(promo)
    await db.commit()


# ── Admin Credit Management ──────────────────────────────────────

@router.post("/credits/grant")
async def admin_grant_credits(
    body: AdminGrantRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_super_admin),
):
    user = await db.get(User, body.user_id)
    if not user:
        raise NotFoundError(f"User {body.user_id} not found")
    uc = await credit_service.add_credits(
        db, body.user_id, body.amount, TransactionType.ADMIN_GRANT,
        description=body.description or f"Admin grant: {body.amount} credits",
    )
    await db.commit()
    return {"status": "ok", "user_id": body.user_id, "new_balance": uc.balance}


@router.get("/credits/user/{user_id}")
async def admin_get_user_credits(
    user_id: str,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_super_admin),
):
    user = await db.get(User, user_id)
    if not user:
        raise NotFoundError(f"User {user_id} not found")

    balance = await credit_service.get_balance(db, user_id)
    offset = (page - 1) * size
    txns, total = await credit_service.get_transactions(
        db, user_id, offset=offset, limit=size
    )
    return {
        "user_id": user_id,
        "email": user.email,
        "name": user.name,
        "balance": balance,
        "transactions": _paginate(
            [
                {
                    "id": t.id, "amount": t.amount, "type": t.type.value,
                    "reference_id": t.reference_id,
                    "razorpay_order_id": t.razorpay_order_id,
                    "description": t.description,
                    "created_at": t.created_at.isoformat(),
                }
                for t in txns
            ],
            total, page, size,
        ),
    }


@router.get("/transactions")
async def admin_list_transactions(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    search: str = Query("", max_length=100),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_super_admin),
):
    offset = (page - 1) * size
    rows, total = await credit_service.get_all_transactions(
        db, offset=offset, limit=size, search=search
    )
    items = [
        {
            "id": txn.id, "user_id": txn.user_id,
            "user_email": email, "user_name": name,
            "amount": txn.amount, "type": txn.type.value,
            "reference_id": txn.reference_id,
            "razorpay_order_id": txn.razorpay_order_id,
            "description": txn.description,
            "created_at": txn.created_at.isoformat(),
        }
        for txn, email, name in rows
    ]
    return _paginate(items, total, page, size)


# ── LLM Requests ────────────────────────────────────────────────

@router.get("/llm-requests")
async def list_llm_requests(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    purpose: str = Query("", max_length=50),
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
