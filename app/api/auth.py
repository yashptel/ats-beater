from datetime import datetime, date, timezone
from fastapi import APIRouter, Depends, Request, Header
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.session import get_db
from app.config import get_settings
from app.models.user import User
from app.models.ai_settings import UserAISettings
from app.models.tenant import Tenant, TenantDomainRule
from app.models.credit import UserCredit
from app.schemas.ai_settings import AISettingsResponse, AISettingsUpdateRequest
from app.services.auth import google_oauth
from app.services.ai.user_settings import AISettingsService
from typing import Optional
from app.services.auth.jwt_handler import create_access_token, decode_expired_token
from app.dependencies import get_current_user
from app.exceptions import AuthenticationError
from logging import getLogger

logger = getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])
ai_settings_service = AISettingsService()


def _get_redirect_uri() -> str:
    """Build OAuth redirect URI from FRONTEND_URL for consistency across Cloud Run URLs."""
    settings = get_settings()
    return f"{settings.FRONTEND_URL.rstrip('/')}/auth/google/callback"


@router.get("/google/login")
async def google_login():
    url = google_oauth.get_login_url(_get_redirect_uri())
    return {"url": url}


@router.get("/google/callback")
async def google_callback(
    code: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    redirect_uri = _get_redirect_uri()
    try:
        tokens = await google_oauth.exchange_code(code, redirect_uri)
        user_info = await google_oauth.get_user_info(tokens["access_token"])
    except Exception as e:
        logger.exception(f"Google OAuth exchange failed: {e}")
        raise AuthenticationError("Failed to authenticate with Google")

    google_id = user_info["id"]
    email = user_info["email"]
    name = user_info.get("name", "")
    picture = user_info.get("picture")

    result = await db.execute(select(User).where(User.google_id == google_id))
    user = result.scalar_one_or_none()

    if not user:
        # Check domain rules for auto-assignment
        email_domain = email.split("@")[-1].lower() if "@" in email else ""
        tenant_id = None
        if email_domain:
            rule_result = await db.execute(
                select(TenantDomainRule).where(TenantDomainRule.domain == email_domain)
            )
            rule = rule_result.scalar_one_or_none()
            if rule:
                tenant_id = rule.tenant_id

        user = User(
            google_id=google_id,
            email=email,
            name=name,
            picture_url=picture,
            consent_accepted=True,
            consent_accepted_at=datetime.now(timezone.utc),
            tenant_id=tenant_id,
        )
        db.add(user)
        await db.flush()  # flush to get user.id
        await db.refresh(user)

        # Create UserCredit row for new user (same transaction)
        user_credit = UserCredit(
            user_id=user.id,
            balance=0,
            daily_free_used=0,
            daily_free_reset_date=datetime.now(timezone.utc).date(),
        )
        db.add(user_credit)
        await db.commit()
    else:
        user.name = name
        user.picture_url = picture

        # Re-check domain rules for users with no tenant (rule may have been added after signup)
        if not user.tenant_id:
            email_domain = email.split("@")[-1].lower() if "@" in email else ""
            if email_domain:
                rule_result = await db.execute(
                    select(TenantDomainRule).where(TenantDomainRule.domain == email_domain)
                )
                rule = rule_result.scalar_one_or_none()
                if rule:
                    user.tenant_id = rule.tenant_id

        await db.commit()

    jwt_token = create_access_token(user.id, user.email)

    # Redirect to frontend with token as query param inside hash route
    # Hash routing uses /#/path?query format
    settings = get_settings()
    frontend_url = settings.FRONTEND_URL
    return RedirectResponse(url=f"{frontend_url}/#/login?access_token={jwt_token}")


@router.post("/refresh")
async def refresh_token(
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Issue a fresh JWT. Accepts expired tokens (signature must still be valid)."""
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationError("token_invalid")
    token = authorization[7:]
    payload = decode_expired_token(token)
    user = await db.get(User, payload["sub"])
    if not user:
        raise AuthenticationError("token_invalid")
    new_token = create_access_token(user.id, user.email)
    return {"access_token": new_token}


@router.get("/me")
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant_name = None
    if current_user.tenant_id:
        tenant = await db.get(Tenant, current_user.tenant_id)
        if tenant:
            tenant_name = tenant.name
    ai_settings = await db.get(UserAISettings, current_user.id)
    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "picture_url": current_user.picture_url,
        "consent_accepted": current_user.consent_accepted,
        "is_super_admin": current_user.is_super_admin,
        "tenant_id": current_user.tenant_id,
        "tenant_name": tenant_name,
        "has_ai_settings": ai_settings is not None,
        "selected_model": ai_settings.model_name if ai_settings else None,
    }


@router.get("/ai-settings", response_model=AISettingsResponse)
async def get_ai_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ai_settings = await ai_settings_service.get_settings(db, current_user.id)
    return ai_settings_service.serialize(ai_settings)


@router.put("/ai-settings", response_model=AISettingsResponse)
async def upsert_ai_settings(
    payload: AISettingsUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ai_settings = await ai_settings_service.upsert_settings(
        db,
        current_user.id,
        api_key=payload.api_key.strip() if payload.api_key else None,
        model_name=payload.model_name,
    )
    return ai_settings_service.serialize(ai_settings)


@router.delete("/ai-settings", response_model=AISettingsResponse)
async def delete_ai_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await ai_settings_service.delete_settings(db, current_user.id)
    return ai_settings_service.serialize(None)
