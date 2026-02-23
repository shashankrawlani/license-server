from datetime import datetime, timezone
from typing import Optional, List
from sqlmodel import SQLModel, Field, JSON, Column, DateTime, UniqueConstraint, String
from sqlalchemy import ForeignKey
import uuid
from pydantic import EmailStr

class App(SQLModel, table=True):
    """Database model for an application using the license server.
    
    Attributes:
        slug: Unique identifier for the app (e.g., 'myapp', 'api-v2').
        name: Human-readable name of the app.
        api_key_hash: Argon2 hash of the app's secret API key.
        created_at: Timestamp when the app was registered.
    """
    __tablename__ = "apps"
    
    slug: str = Field(primary_key=True)
    name: str = Field(nullable=False)
    api_key_hash: str = Field(index=True, nullable=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )

class LicenseBase(SQLModel):
    """Base schema for license data.

    Attributes:
        email: Owner's email address.
        tier: Licensing tier (default: community).
        expires_at: Expiration timestamp with timezone.
        features: List of enabled feature flags.
        license_metadata: Custom organizational/limit data.
    """
    email: EmailStr = Field(index=True)
    tier: str = Field(default="community")
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    features: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    license_metadata: dict = Field(default_factory=dict, sa_column=Column(JSON))

class License(LicenseBase, table=True):
    """Database model for a signed license key.
    
    Contains the cryptographic key and revocation status.
    """
    """Database model for a license.

    Attributes:
        id: Unique identifier for the license.
        license_key: The actual license key string.
        issued_at: Timestamp when the license was issued.
        revoked_at: Optional timestamp if the license was revoked.
        revoked_reason: Optional reason for revocation.
    """
    __tablename__ = "licenses"
    __table_args__ = (UniqueConstraint("email", "app_id"),)
    
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        nullable=False,
    )
    app_id: str = Field(sa_column=Column(String, ForeignKey("apps.slug", ondelete="RESTRICT"), index=True, nullable=False))
    license_key: str
    issued_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    revoked_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    revoked_reason: Optional[str] = None

class LicenseCreate(SQLModel):
    """Schema for creating a new license via admin.
    
    Attributes:
        email: Recipient email.
        tier: Desired tier.
        days: Validity period in days.
        features: List of feature flags.
        license_metadata: Custom JSON data.
    """
    """Schema for creating a new license.

    Attributes:
        email: Owner's email address.
        tier: Licensing tier (default: enterprise).
        days: Number of days until the license expires (default: 365).
        features: List of enabled feature flags.
        license_metadata: Custom organizational/limit data.
    """
    email: EmailStr
    tier: str = "enterprise"
    days: int = 365
    features: List[str] = []
    license_metadata: dict = {}

class RegistrationCreate(SQLModel):
    """Schema for creating a new registration request.

    Attributes:
        email: User's email address.
        name: Optional user's name.
        company: Optional user's company.
        use_case: Optional description of the user's use case.
    """
    email: EmailStr
    name: Optional[str] = None
    company: Optional[str] = None
    use_case: Optional[str] = None

class LicenseResponse(SQLModel):
    license_key: str
    tier: str
    expires_at: datetime
    email: str

class RegistrationResponse(SQLModel):
    email: EmailStr
    message: str
    license_key: Optional[str] = None
    tier: Optional[str] = None
    verification_url: Optional[str] = None

class VerificationRequest(SQLModel, table=True):
    """Database model for self-service registration requests.
    
    Stores a temporary verification token sent via email.
    """
    __tablename__ = "verification_requests"
    __table_args__ = (UniqueConstraint("email", "app_id"),)
    
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        nullable=False,
    )
    app_id: str = Field(sa_column=Column(String, ForeignKey("apps.slug", ondelete="CASCADE"), index=True, nullable=False))
    email: EmailStr = Field(index=True)
    token: str = Field(index=True)
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    
    # Store registration metadata as JSON
    registration_data: dict = Field(default_factory=dict, sa_column=Column(JSON))
    
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    verified_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True)
    )
