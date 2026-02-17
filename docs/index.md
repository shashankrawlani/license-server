# License Server 🚀

[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com)
[![SQLModel](https://img.shields.io/badge/SQLModel-005571?style=for-the-badge&logo=sqlalchemy)](https://sqlmodel.tiangolo.com)
[![Test Coverage](https://img.shields.io/badge/Coverage-100%25-brightgreen?style=for-the-badge)](https://github.com/shashankrawlani/license-server)

A standalone, production-ready licensing service. Secure your premium features with RSA-signed licenses and a robust, multi-tenant-ready management API.

---

## 🤖 AI Native
This project is optimized for LLMs. Access high-density context files from the root:
- **[llms.txt](../llms.txt)**: Concise project roadmap for AI reasoning engines.
- **[llms-full.txt](../llms-full.txt)**: Complete consolidated documentation and source code.

## 📚 Documentation
- **[User Journey](user_journey.md)**: From registration to high-performance local validation.
- **[API Reference](api_reference.md)**: Technical endpoint documentation and data schemas.
- **[Tier & Metadata Guide](user_journey.md#5-generic-schema--extensibility)**: How to drive application logic using the generic schema.

---

## ✨ Key Features
- **Standalone & Portable**: A "Lego brick" microservice that living in your app's namespace.
- **Cryptographic Security**: RSA-2048 with PSS padding for non-forgeable, offline-verifiable keys.
- **Generic Schema**: Extensible `tier`, `features`, and `license_metadata` fields to support any business model.
- **Self-Service flow**: Built-in community registration with Resend email verification.
- **High Performance**: Asynchronous implementation with PostgreSQL and connection pooling.
- **100% Tested**: Comprehensive suite covering every line of code and failure mode.

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
```bash
docker-compose up -d
```

---

## 🛡️ Security Architecture
The License Server follows a **Asymmetric Separation** model:
1. **Private Server**: Generates and signs keys with a **Private RSA Key** (never leaves this service).
2. **Public Client**: Verifies keys locally with a **Public RSA Key**. Even if the client source is public, licenses cannot be forged.

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
