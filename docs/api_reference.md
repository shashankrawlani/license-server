# API Reference: License Server

## Public Endpoints

### Health Check
- **Endpoint**: `GET /health`
- **Summary**: Returns the status of the server.
- **Response**: `{"status": "healthy"}`

### Community Registration
- **Endpoint**: `POST /register`
- **Payload**: `RegistrationCreate`
- **Rate Limit**: 5 requests per minute.
- **Summary**: Initiates the registration flow and sends a verification email.

### Email Verification
- **Endpoint**: `GET /verify-email`
- **Params**: `token` (string)
- **Rate Limit**: 10 requests per minute.
- **Summary**: Validates the email token and issues a community license.

### License Validation
- **Endpoint**: `POST /validate-license`
- **Params**: `license_key` (string)
- **Rate Limit**: 60 requests per minute.
- **Summary**: Checks if a license is active, not revoked, and not expired.

---

## Admin Endpoints
*Require `Authorization: Bearer <ADMIN_API_KEY>` header.*

### Generate License
- **Endpoint**: `POST /generate-license`
- **Payload**: `LicenseCreate` (email, tier, days, etc.)
- **Summary**: Manually generate an enterprise or community license.

### Revoke License
- **Endpoint**: `POST /revoke-license`
- **Params**: `email` (optional), `license_key` (optional), `reason` (optional)
- **Summary**: Marks one or more licenses as revoked.

### List Licenses
- **Endpoint**: `GET /licenses`
- **Response**: `List[License]`
- **Summary**: Returns all license records in the database.

---

## Data Schema

### License Request (`LicenseCreate`)
| Field | Type | Description |
| :--- | :--- | :--- |
| `email` | `EmailStr` | Owner's email address |
| `tier` | `str` | coarse access level (e.g., `community`, `enterprise`) |
| `days` | `int` | Expiry duration from today (default: 365) |
| `features` | `List[str]` | List of enabled feature flags |
| `license_metadata` | `dict` | Custom JSON data (seats, org_id, etc.) |

**Example Production Payload**:
```json
{
  "email": "customer@bigcorp.com",
  "tier": "enterprise",
  "days": 730,
  "features": ["audit_logs", "dedicated_db"],
  "license_metadata": {
    "max_seats": 500,
    "customer_id": "CUST-12345"
  }
}
```

---

## Local Verification
For high-performance or offline use cases, clients can verify licenses locally using the RSA Public Key.
- **Method**: RSA-PSS signature verification.
- **Hashing**: SHA-256.
- **Payload**: JSON claims (email, tier, expiry).
