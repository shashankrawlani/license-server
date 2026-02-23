# User Journey: License Server

This document outlines the full lifecycle of a license, from registration to validation and revocation.

## 1. Community License Journey

The community license is a self-service flow designed for individuals and open-source contributors.

### Step 1: Registration
The user provides their email and basic details.
- **Endpoint**: `POST /register`
- **Payload**:
  ```json
  {
    "email": "user@example.com",
    "name": "Jane Doe",
    "company": "Personal",
    "use_case": "Development"
  }
  ```
- **Action**: The server stores a `VerificationRequest`.
  - **Email Disabled (Default)**: Returns `verification_url` in the JSON response.
    ```json
    {
      "email": "user@example.com",
      "message": "Registration successful...",
      "verification_url": "http://localhost:8321/verify-email?token=..."
    }
    ```
  - **Email Enabled**: Sends a verification email via Resend.

### Step 2: Email Verification
The user clicks the link in their email.
- **Endpoint**: `GET /verify-email?token=xyz...`
- **Action**: The server validates the token, creates a `community` tier license (valid for 10 years), and sends a second email containing:
  - The **License Key**
  - The **Public Key** (used for local verification)

### Step 3: Activation
The user adds the `LICENSE_KEY` and `LICENSE_PUBLIC_KEY` to their application's `.env` file.

---

## 2. Enterprise License Journey

Enterprise licenses are managed by administrators for paid tiers.

### Step 1: Request
The user contacts the team or completes a purchase.

### Step 2: Generation (Admin)
An administrator generates the license using their `ADMIN_API_KEY`.
- **Endpoint**: `POST /generate-license`
- **Headers**: `Authorization: Bearer <ADMIN_API_KEY>`
- **Payload**:
  ```json
  {
    "email": "enterprise@corp.com",
    "tier": "enterprise",
    "days": 365,
    "features": ["unlimited_tokens", "priority_support"]
  }
  ```
- **Action**: The server generates a signed license key and returns it immediately to the admin, who then shares it with the customer.

---

## 3. License Validation Journey

The client application validates the license on startup or periodically.

### Remote Validation (Recommended)
The client calls the license server to check if the key is still valid and not revoked.
- **Endpoint**: `POST /validate-license?license_key=...`
- **Response**:
  ```json
  {
    "valid": true,
    "tier": "enterprise",
    "email": "enterprise@corp.com",
    "expires_at": "..."
  }
  ```

### Local Verification (Offline)
The client can verify the signature using the `PUBLIC_KEY` without calling the server. This confirms the key was indeed signed by this server and has not been tampered with.

---

## 4. Revocation Journey

If a subscription expires or a key is leaked, an admin can revoke it.

### Action (Admin)
- **Endpoint**: `POST /revoke-license`
- **Headers**: `Authorization: Bearer <ADMIN_API_KEY>`
- **Params**: `email=...` or `license_key=...`
- **Action**: The license is marked as `revoked_at` in the database. Future `validate-license` calls will return `false`.

---

## 5. Generic Schema & Extensibility

The server is designed to be a "Lego brick" for any application. It uses three key fields to drive business logic without requiring database migrations.

### A. Tier (`str`)
The coarse-grained access level.
- **Common values**: `community`, `pro`, `enterprise`, `trial`.
- **Application Logic**:
  ```python
  if license.tier == "enterprise":
      enable_sso()
  ```

### B. Features (`List[str]`)
Fine-grained capability flags.
- **Example**: `["advanced_analytics", "api_access", "white_labeling"]`
- **Application Logic**:
  ```python
  if "api_access" in license.features:
      allow_request()
  ```

### C. License Metadata (`dict`)
The "catch-all" JSON store for organizational or limit-based data.
- **Example**:
  ```json
  {
    "max_seats": 50,
    "org_id": "org_99",
    "region": "us-east-1"
  }
  ```
- **Application Logic**:
  ```python
  if current_active_users >= license.metadata.get("max_seats", 1):
      raise QuotaExceeded()
  ```
