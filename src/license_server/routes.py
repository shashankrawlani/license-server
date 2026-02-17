from fastapi import APIRouter, Depends, HTTPException, Header, status, Request, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta, timezone
from typing import List
import os
import secrets

from .database import get_session
from .models import (
    License, LicenseCreate, LicenseResponse, 
    RegistrationCreate, RegistrationResponse, VerificationRequest
)
from .limiter import limiter
from .crypto import sign_license
from .config import settings
import resend

router = APIRouter()

def send_email(to_email: str, subject: str, html_content: str):
    """Helper function to send emails via Resend."""
    if not settings.RESEND_API_KEY:
        print(f"\n[DEV MODE] Email to {to_email} skipped (No API Key). Subject: {subject}\n")
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

async def verify_admin(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Security dependency to verify the Admin API Key.

    Args:
        credentials: The HTTP Bearer credentials from the request.

    Returns:
        str: The validated admin API key.

    Raises:
        HTTPException: If the key is missing or incorrect.
    """
    if not settings.ADMIN_API_KEY:
        raise HTTPException(status_code=500, detail="ADMIN_API_KEY not configured on server")
    if credentials.credentials != settings.ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Not authorized")
    return credentials.credentials

@router.post("/register", response_model=RegistrationResponse)
@limiter.limit("5/minute")
async def register_community(request: Request, data: RegistrationCreate, background_tasks: BackgroundTasks, session: AsyncSession = Depends(get_session)):
    """Initiates a self-service registration for a community license.

    Saves a verification request and queues a verification email.

    Args:
        request: The FastAPI request object (for rate limiting).
        data: Registration details (email, name, etc.).
        background_tasks: FastAPI background tasks handler.
        session: Asynchronous database session.

    Returns:
        RegistrationResponse: A message confirming the email was sent.
    """
    # 1. Check if an active license already exists
    statement = select(License).where(
        License.email == data.email, 
        License.tier == "community",
        License.revoked_at == None
    )
    results = await session.execute(statement)
    existing = results.scalars().first()
    
    if existing:
        return RegistrationResponse(
            email=data.email,
            message="An active community license already exists for this email. Please check your inbox or contact support."
        )
    
    # 2. Generate Verification Request
    token = secrets.token_hex(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    
    new_request = VerificationRequest(
        email=data.email,
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
 
    # 3. Send Verification Email
    verification_link = f"{settings.BASE_URL}/verify-email?token={token}"
    email_subject = "Verify your License Registration"
    email_html = f"""
    <h3>Welcome!</h3>
    <p>Please click the link below to verify your email and retrieve your license key:</p>
    <p><a href="{verification_link}">{verification_link}</a></p>
    <p>If you did not request this, please ignore this email.</p>
    """
    
    background_tasks.add_task(send_email, data.email, email_subject, email_html)
    
    return RegistrationResponse(
        email=data.email,
        message="Verification email sent. Please click the link in your inbox to retrieve your license key."
    )

@router.get("/verify-email", response_model=RegistrationResponse)
@limiter.limit("10/minute")
async def verify_email(request: Request, token: str, background_tasks: BackgroundTasks, session: AsyncSession = Depends(get_session)):
    """Verifies an email token and issues a community license.

    Args:
        request: The FastAPI request object.
        token: The unique verification token from the email.
        background_tasks: FastAPI background tasks handler.
        session: Asynchronous database session.

    Returns:
        RegistrationResponse: The issued license key and a success message.

    Raises:
        HTTPException: If the token is invalid or expired.
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
    
    # 2. Create the Community License (10 year expiry)
    expires_at = datetime.now(timezone.utc) + timedelta(days=3650)
    key = sign_license(verify_req.email, "community", expires_at)
    
    new_license = License(
        email=verify_req.email,
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
    
    # 4. Send License Email
    public_key = get_public_key()
    email_subject = "Your License Key"
    email_html = f"""
    <h3>Email Verified!</h3>
    <p>Your community license key is now active.</p>
    
    <h4>Setup Instructions:</h4>
    <ol>
        <li>Add the <code>LICENSE_KEY</code> to your <code>.env</code> file.</li>
        <li>Add the <code>LICENSE_PUBLIC_KEY</code> to your <code>.env</code> file (copy the block below).</li>
    </ol>
    <p><strong>LICENSE_KEY:</strong><br/>
    <code>{key}</code></p>
    <p><strong>LICENSE_PUBLIC_KEY:</strong> (Save this exactly as shown including headers)<br/>
    <pre>{public_key}</pre></p>
    """
    
    background_tasks.add_task(send_email, verify_req.email, email_subject, email_html)
    
    return {
        "email": verify_req.email,
        "license_key": key,
        "tier": "community",
        "message": "Email verified! Your community license key is active and has been sent to your inbox."
    }

@router.post("/generate-license", response_model=LicenseResponse, dependencies=[Depends(verify_admin)])
async def generate_license(data: LicenseCreate, session: AsyncSession = Depends(get_session)):
    """Manually generates a license (Admin only).

    Args:
        data: License configuration (tier, days, features, metadata).
        session: Asynchronous database session.

    Returns:
        LicenseResponse: The generated license details and key.
    """
    expires_at = datetime.now(timezone.utc) + timedelta(days=data.days)
    key = sign_license(data.email, data.tier, expires_at)
    
    new_license = License(
        email=data.email,
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
async def validate_license(request: Request, license_key: str, session: AsyncSession = Depends(get_session)):
    """Validates a license key against the database.

    Checks for existence, expiration, and revocation.

    Args:
        request: The FastAPI request object.
        license_key: The license key string to validate.
        session: Asynchronous database session.

    Returns:
        dict: Validation status and license metadata.

    Raises:
        HTTPException: If the license is not found, revoked, or expired.
    """
    # Find active license
    statement = select(License).where(
        License.license_key == license_key,
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

@router.post("/revoke-license", dependencies=[Depends(verify_admin)])
async def revoke_license(email: str = None, license_key: str = None, reason: str = "Revoked by admin", session: AsyncSession = Depends(get_session)):
    """Revokes one or more licenses (Admin only).

    Args:
        email: Optional email to revoke all licenses for.
        license_key: Optional specific license key to revoke.
        reason: Optional reason for revocation.
        session: Asynchronous database session.

    Returns:
        dict: A message confirming the number of revoked licenses.

    Raises:
        HTTPException: If no active license is found to revoke.
    """
    if not email and not license_key:
        raise HTTPException(status_code=400, detail="Email or license_key required")
    
    query = select(License).where(License.revoked_at == None)
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

@router.get("/licenses", response_model=List[License], dependencies=[Depends(verify_admin)])
async def list_licenses(session: AsyncSession = Depends(get_session)):
    """Lists all licenses in the database (Admin only).

    Returns:
        List[License]: A list of all license records.
    """
    results = await session.execute(select(License))
    return results.scalars().all()
