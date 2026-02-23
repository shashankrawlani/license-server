# Stage 1: Builder
FROM python:3.12-slim-bookworm AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies into a virtual environment using cache mounts
# --frozen: strict lockfile usage
# --no-dev: valid for production
# --no-install-project: we'll copy code in the next stage and use PYTHONPATH
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Stage 2: Final
FROM python:3.12-slim-bookworm

# Install curl for healthcheck and clean up
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user
RUN groupadd -r license-group && useradd -r -g license-group -m license-user

WORKDIR /app

# Ensure data directory exists with correct permissions
RUN mkdir -p /app/data && chown -R license-user:license-group /app/data

# Copy virtual environment from builder
COPY --from=builder --chown=license-user:license-group /app/.venv /app/.venv

# Add virtual env to PATH
ENV PATH="/app/.venv/bin:$PATH"
# Add src to PYTHONPATH so imports work correctly
ENV PYTHONPATH="/app/src"

# Copy application code
COPY --chown=license-user:license-group . .

# Environment variables (Safe defaults only)
ENV PUBLIC_KEY_PATH=/app/data/public.pem \
    PYTHONUNBUFFERED=1

EXPOSE 8321

# Switch to non-root user
USER license-user

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8321/docs || exit 1

# Run with uvicorn
CMD ["python", "-m", "uvicorn", "license_server.main:app", "--host", "0.0.0.0", "--port", "8321"]
