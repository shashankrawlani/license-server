from fastapi import APIRouter, Depends, HTTPException, Header, status, Request, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta, timezone
from typing import List
import os
import secrets
import logging

from .database import get_session
from .models import (
    App, License, LicenseCreate, LicenseResponse, 
    RegistrationCreate, RegistrationResponse, VerificationRequest
)
from .limiter import limiter
from .crypto import sign_license
from .config import settings
import resend
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

ph = PasswordHasher()
logger = logging.getLogger(__name__)

router = APIRouter()

def send_email(to_email: str, subject: str, html_content: str):
    """Helper function to send emails via Resend."""
    if not settings.RESEND_API_KEY:
        logger.debug(f"Email skipped (no API key): {to_email} - {subject}")
        return
        
    try:
        resend.api_key = settings.RESEND_API_KEY
        resend.Emails.send({
            "from": settings.RESEND_FROM_EMAIL,
            "to": to_email,
            "subject": subject,
            "html": html_content
        })
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

def get_public_key():
    """Retrieves the RSA public key in PEM format.

    Returns:
        str: The public key content or an error message if not found.
    """
    if os.path.exists(settings.PUBLIC_KEY_PATH):
        with open(settings.PUBLIC_KEY_PATH, "r") as f:
            return f.read()
    return "Error: Public key file not found."

security = HTTPBearer()

# Lazy cache for single-tenant mode — avoids DB query on every request
_cached_single_app: App | None = None

def _invalidate_app_cache():
    global _cached_single_app
    _cached_single_app = None

async def _resolve_single_app(session: AsyncSession) -> App:
    """Resolve the single registered app. Caches result for subsequent calls."""
    global _cached_single_app
    if _cached_single_app:
        return _cached_single_app
    result = await session.execute(select(App))
    apps = result.scalars().all()
    if len(apps) == 0:
        raise HTTPException(
            status_code=400,
            detail="No app registered. Create one: POST /admin/apps with Authorization: Bearer $ADMIN_API_KEY"
        )
    if len(apps) > 1:
        raise HTTPException(
            status_code=400,
            detail="Multiple apps exist. Enable MULTI_TENANT_MODE or delete extras via DELETE /admin/apps/{slug}"
        )
    _cached_single_app = apps[0]
    return apps[0]

async def verify_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    x_app_id: str | None = Header(None, alias="X-App-Id"),
    session: AsyncSession = Depends(get_session)
) -> str:
    """Verify admin key and scope the operation to an app.
    
    In single-tenant mode, auto-resolves to the only registered app.
    In multi-tenant mode, X-App-Id header is required.
    
    Returns:
        str: The validated app_id (slug).
    """
    if not settings.ADMIN_API_KEY:
        raise HTTPException(status_code=500, detail="ADMIN_API_KEY not configured on server")
    
    if credentials.credentials != settings.ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    if settings.MULTI_TENANT_MODE:
        if not x_app_id:
            raise HTTPException(status_code=400, detail="X-App-Id header is required for admin operations in multi-tenant mode")
        return x_app_id
    
    # Single-tenant: use provided header or auto-resolve
    if x_app_id:
        return x_app_id
    app = await _resolve_single_app(session)
    return app.slug

async def verify_admin_only(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Verify admin key only (no app resolution). Used for app creation."""
    if not settings.ADMIN_API_KEY:
        raise HTTPException(status_code=500, detail="ADMIN_API_KEY not configured on server")
    
    if credentials.credentials != settings.ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Not authorized")

async def verify_app(
    x_app_id: str | None = Header(None, alias="X-App-Id"), 
    x_app_key: str | None = Header(None, alias="X-App-Key"), 
    session: AsyncSession = Depends(get_session)
) -> App:
    """Security dependency to verify the App API Key.

    - In MULTI_TENANT_MODE=False (default): Auto-resolves to the single registered app. Headers ignored.
    - In MULTI_TENANT_MODE=True: Enforces X-App-Id and X-App-Key verification.
    """
    if not settings.MULTI_TENANT_MODE:
        return await _resolve_single_app(session)

    # Multi-Tenant Mode: Enforce headers
    if not x_app_id or not x_app_key:
        raise HTTPException(status_code=401, detail="X-App-Id and X-App-Key are required in multi-tenant mode")

    statement = select(App).where(App.slug == x_app_id)
    result = await session.execute(statement)
    app = result.scalars().first()

    if not app:
         raise HTTPException(status_code=401, detail="Invalid App ID or API Key")

    try:
        ph.verify(app.api_key_hash, x_app_key)
    except VerifyMismatchError:
        raise HTTPException(status_code=401, detail="Invalid App ID or API Key")

    return app

@router.post("/register", response_model=RegistrationResponse)
@limiter.limit("5/minute")
async def register_community(
    request: Request, 
    data: RegistrationCreate, 
    background_tasks: BackgroundTasks, 
    app: App = Depends(verify_app),
    session: AsyncSession = Depends(get_session)
):
    """Initiates a self-service registration for a community license."""
    app_id = app.slug
    # 1. Check if an active license already exists for THIS app
    statement = select(License).where(
        License.email == data.email, 
        License.app_id == app_id,
        License.tier == "community",
        License.revoked_at == None
    )
    results = await session.execute(statement)
    existing = results.scalars().first()
    
    # Removed early return for existing licenses to allow re-verification if needed
    # by the API gateway/router.
    
    # 2. Generate Verification Request
    token = secrets.token_hex(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    
    new_request = VerificationRequest(
        email=data.email,
        app_id=app_id,
        token=token,
        expires_at=expires_at,
        registration_data={
            "name": data.name,
            "company": data.company,
            "use_case": data.use_case
        }
    )
    session.add(new_request)
    await session.commit()
 
    # 3. Handle Notification (Email vs Delegation)
    verification_link = f"{settings.BASE_URL}/verify-email?token={token}"
    email_subject = "Verify your email for License Server"
    email_html = f"""
    <h2>Verify your email</h2>
    <p>Click the link below to verify your email and get your license key:</p>
    <a href="{verification_link}">{verification_link}</a>
    <p>If you did not request this, please ignore this email.</p>
    """

    if settings.EMAIL_ENABLED:
        background_tasks.add_task(send_email, data.email, email_subject, email_html)
        message = "Verification email sent. Please click the link in your inbox to retrieve your license key."
        verification_url_response = None
    else:
        message = "Registration successful. Please verify your email using the provided URL."
        verification_url_response = verification_link
    
    return RegistrationResponse(
        email=data.email,
        message=message,
        verification_url=verification_url_response
    )

@router.get("/verify-email", response_model=RegistrationResponse)
@limiter.limit("10/minute")
async def verify_email(request: Request, token: str, background_tasks: BackgroundTasks, session: AsyncSession = Depends(get_session)):
    """Verifies an email token and returns the generated license key.
    
    Caller handles sending the welcome email.
    """
    # 1. Find the request
    statement = select(VerificationRequest).where(
        VerificationRequest.token == token,
        VerificationRequest.verified_at == None
    )
    results = await session.execute(statement)
    verify_req = results.scalars().first()
    
    if not verify_req:
        raise HTTPException(status_code=404, detail="Invalid or expired verification token.")
    
    if verify_req.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Verification token has expired.")
    
    # 2. Check if an active community license already exists
    statement = select(License).where(
        License.email == verify_req.email,
        License.app_id == verify_req.app_id,
        License.tier == "community",
        License.revoked_at == None
    )
    results = await session.execute(statement)
    existing_license = results.scalars().first()
    
    if existing_license:
        # Mark as verified and return existing license
        verify_req.verified_at = datetime.now(timezone.utc)
        session.add(verify_req)
        await session.commit()
        
        message = "Email verified! Your existing community license key is active."
        return {
            "email": verify_req.email,
            "license_key": existing_license.license_key,
            "tier": "community",
            "message": message
        }
    
    # 2. Create the Community License (10 year expiry)
    expires_at = datetime.now(timezone.utc) + timedelta(days=3650)
    key = sign_license(verify_req.email, "community", expires_at)
    
    new_license = License(
        email=verify_req.email,
        app_id=verify_req.app_id,
        tier="community",
        license_key=key,
        expires_at=expires_at,
        license_metadata=verify_req.registration_data
    )
    
    # 3. Mark as verified and save license
    verify_req.verified_at = datetime.now(timezone.utc)
    session.add(new_license)
    session.add(verify_req)
    await session.commit()
    await session.refresh(new_license)
    
    logger.info(f"License issued: {verify_req.email} (app: {verify_req.app_id}, tier: community)")
    
    # 4. Handle Notification (Email vs Delegation)
    public_key = get_public_key()
    email_subject = "Your Community License Key"
    email_html = f"""
    <h2>Welcome!</h2>
    <p>Your email has been verified. Here is your community license key:</p>
    <pre>{key}</pre>
    <p><b>Public Key (for verification):</b></p>
    <pre>{public_key}</pre>
    """
    
    if settings.EMAIL_ENABLED:
        background_tasks.add_task(send_email, verify_req.email, email_subject, email_html)
        message = "Email verified! Your community license key is active and has been sent to your inbox."
    else:
        message = "Email verified! Your community license key is active."
    
    return {
        "email": verify_req.email,
        "license_key": key,
        "tier": "community",
        "message": message
    }

@router.post("/generate-license", response_model=LicenseResponse)
async def generate_license(
    data: LicenseCreate, 
    app_id: str = Depends(verify_admin),
    session: AsyncSession = Depends(get_session)
):
    """Manually generates a license (Admin only)."""
    expires_at = datetime.now(timezone.utc) + timedelta(days=data.days)
    key = sign_license(data.email, data.tier, expires_at)
    
    new_license = License(
        email=data.email,
        app_id=app_id,
        tier=data.tier,
        license_key=key,
        expires_at=expires_at,
        features=data.features,
        license_metadata=data.license_metadata
    )
    session.add(new_license)
    await session.commit()
    await session.refresh(new_license)
    
    return LicenseResponse(
        license_key=key,
        tier=data.tier,
        expires_at=expires_at,
        email=data.email
    )

@router.post("/validate-license")
@limiter.limit("60/minute")
async def validate_license(
    request: Request, 
    license_key: str, 
    app: App = Depends(verify_app),
    session: AsyncSession = Depends(get_session)
):
    """Validates a license key against the database.
    Checks for existence, expiration, and revocation. Scoped to app_id.
    """
    app_id = app.slug
    # Find active license for THIS app
    statement = select(License).where(
        License.license_key == license_key,
        License.app_id == app_id,
        License.revoked_at == None
    )
    results = await session.execute(statement)
    license_record = results.scalars().first()
    
    if not license_record:
        raise HTTPException(status_code=404, detail="License not found or revoked")
    
    expires_at = license_record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
        
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=403, detail="License expired")
    
    return {
        "valid": True,
        "tier": license_record.tier,
        "email": license_record.email,
        "expires_at": license_record.expires_at
    }

@router.post("/revoke-license")
async def revoke_license(
    email: str = None, 
    license_key: str = None, 
    app_id: str = Depends(verify_admin),
    reason: str = "Revoked by admin", 
    session: AsyncSession = Depends(get_session)
):
    """Revokes one or more licenses (Admin only)."""
    if not email and not license_key:
        raise HTTPException(status_code=400, detail="Email or license_key required")
    
    query = select(License).where(
        License.app_id == app_id,
        License.revoked_at == None
    )
    if email:
        query = query.where(License.email == email)
    if license_key:
        query = query.where(License.license_key == license_key)
        
    results = await session.execute(query)
    records = results.scalars().all()
    if not records:
        raise HTTPException(status_code=404, detail="Active license not found")
        
    for record in records:
        record.revoked_at = datetime.now(timezone.utc)
        record.revoked_reason = reason
        session.add(record)
        
    await session.commit()
    return {"message": f"Revoked {len(records)} licenses"}

@router.get("/licenses", response_model=List[License])
async def list_licenses(
    app_id: str = Depends(verify_admin), 
    session: AsyncSession = Depends(get_session)
):
    """Lists all licenses for an app (Admin only)."""
    results = await session.execute(select(License).where(License.app_id == app_id))
    return results.scalars().all()

# --- App Management Endpoints ---

@router.post("/admin/apps", dependencies=[Depends(verify_admin_only)])
async def create_app(name: str, slug: str, session: AsyncSession = Depends(get_session)):
    """Creates a new application (Admin only).
    
    Returns the generated API key (plaintext). This is ONLY shown once.
    """
    api_key = secrets.token_hex(32)
    api_key_hash = ph.hash(api_key)
    
    new_app = App(
        slug=slug,
        name=name,
        api_key_hash=api_key_hash
    )
    session.add(new_app)
    await session.commit()
    
    _invalidate_app_cache()
    
    logger.info(f"App created: {slug}")
    
    return {
        "slug": slug,
        "name": name,
        "api_key": api_key,
        "message": "Store this API key safely. It will not be shown again."
    }

@router.get("/admin/apps", response_model=List[App], dependencies=[Depends(verify_admin)])
async def list_apps(session: AsyncSession = Depends(get_session)):
    """Lists all registered applications (Admin only)."""
    results = await session.execute(select(App))
    return results.scalars().all()

@router.delete("/admin/apps/{slug}", dependencies=[Depends(verify_admin)])
async def delete_app(slug: str, session: AsyncSession = Depends(get_session)):
    """Deletes an application (Admin only).
    
    Restricted if any active licenses exist for this app.
    """
    # Check for active licenses
    stmt = select(License).where(License.app_id == slug)
    res = await session.execute(stmt)
    if res.scalars().first():
         raise HTTPException(status_code=400, detail="Cannot delete app with active licenses.")
    
    stmt = select(App).where(App.slug == slug)
    res = await session.execute(stmt)
    app = res.scalars().first()
    
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
        
    await session.delete(app)
    await session.commit()
    _invalidate_app_cache()
    return {"message": f"App '{slug}' deleted successfully."}
