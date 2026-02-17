from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
import os

class Settings(BaseSettings):
    # API Keys & Security
    ADMIN_API_KEY: str = Field(..., description="Admin API key for protecting sensitive endpoints")
    
    # Resend Configuration
    RESEND_API_KEY: str | None = Field(None, description="API key for Resend email service")
    RESEND_FROM_EMAIL: str = Field("routellm@automationtester.in", description="Email address to send from")
    
    # Base URL
    BASE_URL: str = Field("http://localhost:8080", description="Base URL of the license server")
    
    # Database
    DATABASE_URL: str = Field("postgresql://postgres:postgres@localhost:5432/license_server", description="PostgreSQL connection string")
    
    # Key Paths
    PRIVATE_KEY_PATH: str = Field("data/private.pem", description="Path to the RSA private key")
    PUBLIC_KEY_PATH: str = Field("data/public.pem", description="Path to the RSA public key")
    
    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = Field(True, description="Whether to enable rate limiting")

    # Environment
    ENVIRONMENT: str = Field("production", description="Environment (dev, staging, production)")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Docker Secrets support: default mount point (only if exists)
        secrets_dir="/run/secrets" if os.path.exists("/run/secrets") else None
    )

settings = Settings()
