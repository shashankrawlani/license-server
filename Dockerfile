# Stage 1: Builder
FROM python:3.12-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies into a virtual environment
# --frozen: strict lockfile usage
# --no-dev: valid for production
# --no-install-project: we'll copy code in the next stage and use PYTHONPATH
RUN uv sync --frozen --no-dev --no-install-project

# Stage 2: Final
FROM python:3.12-slim-bookworm

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Add virtual env to PATH
ENV PATH="/app/.venv/bin:$PATH"
# Add src to PYTHONPATH so imports work correctly
ENV PYTHONPATH="/app/src"

# Copy application code
COPY . .

# Environment variables (Safe defaults only)
ENV PUBLIC_KEY_PATH=/app/data/public.pem

EXPOSE 8001

# Run with uvicorn (now found in .venv/bin)
CMD ["python", "-m", "uvicorn", "license_server.main:app", "--host", "0.0.0.0", "--port", "8001"]
