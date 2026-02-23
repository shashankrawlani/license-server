from fastapi import FastAPI, Response
from fastapi.responses import FileResponse
import os
import signal
import logging
from contextlib import asynccontextmanager
from .database import init_db
from .routes import router
from .crypto import generate_keypair
from .limiter import limiter
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from .config import settings

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.ENVIRONMENT == "dev" else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Graceful shutdown handler
def handle_sigterm(*args):
    """Handle SIGTERM signal for graceful shutdown."""
    logger.info("SIGTERM received, initiating graceful shutdown...")
    raise KeyboardInterrupt()

signal.signal(signal.SIGTERM, handle_sigterm)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB and generate keys on startup
    logger.info("Starting License Server...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Multi-tenant mode: {settings.MULTI_TENANT_MODE}")
    
    await init_db()
    logger.info("Database initialized")
    
    generate_keypair()
    logger.info("RSA keypair ready")
    
    logger.info("License Server started successfully")
    yield
    logger.info("License Server shutting down...")

app = FastAPI(
    title="License Server",
    description="Standalone service for generating and managing RSA-signed license keys.",
    version="1.0.0",
    lifespan=lifespan,
    # Security: Hide docs in non-dev environments
    docs_url="/docs" if settings.ENVIRONMENT == "dev" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT == "dev" else None,
    openapi_url="/openapi.json" if settings.ENVIRONMENT == "dev" else None
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(router, tags=["licensing"])

@app.get("/health")
def health_check():
    """Returns the health status of the server.

    Returns:
        dict: A simple status message indicating the server is healthy.
    """
    return {"status": "healthy"}

@app.get("/llms.txt", response_class=FileResponse)
async def get_llms_txt():
    """Serves the llms.txt file for AI discovery.

    Returns:
        FileResponse: The llms.txt file content.
    """
    return FileResponse("llms.txt", media_type="text/plain")

@app.get("/llms-full.txt", response_class=FileResponse)
async def get_llms_full_txt():
    """Serves the llms-full.txt file for full AI context.

    Returns:
        FileResponse: The llms-full.txt file content.
    """
    return FileResponse("llms-full.txt", media_type="text/plain")
