# License Server 🚀

[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com)
[![SQLModel](https://img.shields.io/badge/SQLModel-005571?style=for-the-badge&logo=sqlalchemy)](https://sqlmodel.tiangolo.com)
[![Test Coverage](https://img.shields.io/badge/Coverage-100%25-brightgreen?style=for-the-badge)](https://github.com/shashankrawlani/license-server)

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
- **Standalone & Portable**: A "Lego brick" microservice.
- **Cryptographic Security**: RSA-2048 with PSS padding.
- **Generic Schema**: Extensible `tier`, `features`, and `metadata`.
- **Hot Reload**: Seamless development with auto-reloading inside Docker.
- **Self-Service flow**: Community registration with Resend verification.
- **100% Tested**: Comprehensive test suite.

---

## 🚀 Quick Start (UV)

```bash
# Install dependencies
uv sync

# Initialize DB and run (keys generated automatically on first start)
PYTHONPATH=src uv run uvicorn license_server.main:app --host 0.0.0.0 --port 8321

# Run the 100% covered test suite
PYTHONPATH=src uv run pytest tests/ --cov=src/license_server
```

### Deployment (Docker)

#### 🚀 Production Build
Use this for the most stable, isolated version (requires an external PostgreSQL URL).
```bash
docker-compose up -d
```

#### 🛠️ Full Development Environment
One-click setup including a **PostgreSQL database** and **Hot Reloading**.
```bash
docker-compose -f docker-compose.dev.yml up -d
```
*The database is automatically configured and healthy before the server starts.*

---

## 🛡️ Security Architecture
The License Server follows a **Asymmetric Separation** model:
1. **Private Server**: Generates and signs keys with a **Private RSA Key** (never leaves this service).
2. **Public Client**: Verifies keys locally with a **Public RSA Key**. Even if the client source is public, licenses cannot be forged.

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
