# License Server 🚀

[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com)
[![SQLModel](https://img.shields.io/badge/SQLModel-005571?style=for-the-badge&logo=sqlalchemy)](https://sqlmodel.tiangolo.com)
[![Test Coverage](https://img.shields.io/badge/Coverage-99%25-brightgreen?style=for-the-badge)](https://github.com/shashankrawlani/license-server)

A standalone, production-ready licensing service. Secure your premium features with RSA-signed licenses and a robust management API.

---

## 📚 Documentation
- **[User Journey](docs/user_journey.md)**: From registration to high-performance local validation.
- **[API Reference](docs/api_reference.md)**: Technical endpoint documentation and data schemas.
- **[Tier & Metadata Guide](docs/user_journey.md#5-generic-schema--extensibility)**: How to drive application logic using the generic schema.

---

## 🤖 AI Native
This project is optimized for LLMs. Access high-density context files directly from the server:
- `GET /llms.txt`: Concise project roadmap for AI reasoning engines.
- `GET /llms-full.txt`: Complete consolidated documentation and source code.
- **[llms.txt](llms.txt)**: Local copy of the roadmap.
- **[llms-full.txt](llms-full.txt)**: Local copy of the context.

---

## ✨ Key Features
- **Dual Deployment Modes**: Runs as a **sidecar** (single-app) or **central multi-tenant server**.
- **Standalone & Portable**: A "Lego brick" microservice.
- **Cryptographic Security**: RSA-2048 with PSS padding.
- **Generic Schema**: Extensible `tier`, `features`, and `metadata`.
- **Hot Reload**: Seamless development inside Docker with `uvicorn --reload`.
- **Self-Service flow**: Community registration with email verification.
- **Hardened Security**: Runs as a non-root user with minimal privileges.
- **Resource Efficient**: Optimized for predictable performance.
- **99% Test Coverage**: Full dual-mode parametrized test suite.

---

## 🔀 Deployment Modes

Control via the `MULTI_TENANT_MODE` environment variable:

### Mode 1: Single-App Sidecar (`MULTI_TENANT_MODE=False` — Default)
Deploy one instance alongside each application. No `X-App-Id` / `X-App-Key` headers required.
```
YourApp → LicenseServer 
```
- All licenses are automatically scoped to the single registered app.
- Simpler runtime: no app registration headers needed for public endpoints.
- Ideal for indie developers or single-product companies.

### Mode 2: Multi-App Central Server (`MULTI_TENANT_MODE=True`)
Deploy one central server for all your applications.
```
AppA ─┐
AppB ─┤─→ LicenseServer (multi-tenant)
AppC ─┘
```
- Each request must include `X-App-Id` and `X-App-Key` headers.
- Full tenant isolation: App A cannot see App B's licenses.
- Run the migration script to register new apps:
  ```bash
  uv run python scripts/app_migration.py
  ```

---

## ⬆️ Upgrading from v1.x

Version 2.x **removes the built-in "default" app**. The server requires at least one explicitly registered application to function.

If you are upgrading an existing deployment that used the "default" app:
1. Run the server normally.
2. Run the migration script: `uv run python scripts/app_migration.py`. If it warns about `NULL` app_ids, do **not** panic.
3. Create your app:
   ```bash
   curl -X POST http://localhost:8321/admin/apps \
     -H "Authorization: Bearer $ADMIN_API_KEY" \
     -d '{"slug":"myapp","name":"My App"}'
   ```
4. Map existing licenses to your new app via PostgreSQL:
   ```sql
   UPDATE licenses SET app_id = 'myapp' WHERE app_id IS NULL OR app_id = 'default';
   UPDATE verification_requests SET app_id = 'myapp' WHERE app_id IS NULL OR app_id = 'default';
   ```

---

## 🚀 Quick Start (UV)

```bash
# Install dependencies
uv sync

# Initialize DB and run (keys generated automatically on first start)
PYTHONPATH=src uv run uvicorn license_server.main:app --host 0.0.0.0 --port 8321

# Create your application (Required)
curl -X POST http://localhost:8321/admin/apps \
  -H "Authorization: Bearer $ADMIN_API_KEY" \
  -d '{"slug":"my-app","name":"My Application"}'

# Run the 99% covered test suite
PYTHONPATH=src uv run pytest tests/ --cov=src/license_server
```

### Deployment (Docker)

#### 🚀 Production Build
The server requires a **PostgreSQL** database.

**Requirements**:
- A PostgreSQL instance accessible via the network.

```bash
# Start the license server
docker-compose up -d
```

**Configuration**:
- Configure `DATABASE_URL` in your `.env` to point to your specific PostgreSQL instance.
- The `docker-compose.yml` provides a standard configuration for running the service as an isolated container.

### Email Configuration (Resend)
The server uses [Resend](https://resend.com) for emails. You can configure the API Key in one of two ways:
1. **Environment Variable**: Set `RESEND_API_KEY` in your `.env` file.
2. **Docker Secret**: Mount a secret file at `/run/secrets/resend_api_key`.

> [!TIP]
> Use the provided `mock_send_email` in tests to avoid hitting Resend limits during development.

---

## 🛠️ Development & Testing

### Full Development Environment
One-click setup for local development.
```bash
docker-compose -f docker-compose.dev.yml up -d
```

### 99% Test Coverage
The project maintains absolute test coverage. Run tests locally via `uv`:
```bash
# Set up test DB first if needed
# uv run python reset_db.py 

# Run the suite
uv run pytest tests/ --cov=src/license_server --cov-report=term-missing
```

---

## 🛡️ Security Architecture
The License Server follows a **Asymmetric Separation** model:
1. **Private Server**: Generates and signs keys with a **Private RSA Key** (never leaves this service).
2. **Public Client**: Verifies keys locally with a **Public RSA Key**. Even if the client source is public, licenses cannot be forged.

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
