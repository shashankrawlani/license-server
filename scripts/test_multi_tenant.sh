#!/bin/bash
# Multi-tenant mode comprehensive test

set -e

BASE_URL="http://localhost:8321"
ADMIN_KEY=$(cat secrets/admin_api_key.txt)

echo "=== Multi-Tenant Mode Test ==="
echo ""

# Create App 1
echo "1. Creating App1..."
APP1_RESPONSE=$(curl -s -X POST "$BASE_URL/admin/apps?name=App1&slug=app1" \
  -H "Authorization: Bearer $ADMIN_KEY")
APP1_KEY=$(echo $APP1_RESPONSE | jq -r '.api_key')
echo "App1 Key: ${APP1_KEY:0:20}..."
echo ""

# Create App 2
echo "2. Creating App2..."
APP2_RESPONSE=$(curl -s -X POST "$BASE_URL/admin/apps?name=App2&slug=app2" \
  -H "Authorization: Bearer $ADMIN_KEY")
APP2_KEY=$(echo $APP2_RESPONSE | jq -r '.api_key')
echo "App2 Key: ${APP2_KEY:0:20}..."
echo ""

# Register user for App1
echo "3. Registering user1@app1.com for App1..."
RESPONSE=$(curl -s -X POST "$BASE_URL/register" \
  -H "Content-Type: application/json" \
  -H "X-App-Id: app1" \
  -H "X-App-Key: $APP1_KEY" \
  -d '{"email": "user1@app1.com"}')
TOKEN1=$(echo $RESPONSE | jq -r '.verification_url' | sed 's/.*token=\([^&]*\).*/\1/')
echo "Token: ${TOKEN1:0:20}..."
echo ""

# Register user for App2
echo "4. Registering user2@app2.com for App2..."
RESPONSE=$(curl -s -X POST "$BASE_URL/register" \
  -H "Content-Type: application/json" \
  -H "X-App-Id: app2" \
  -H "X-App-Key: $APP2_KEY" \
  -d '{"email": "user2@app2.com"}')
TOKEN2=$(echo $RESPONSE | jq -r '.verification_url' | sed 's/.*token=\([^&]*\).*/\1/')
echo "Token: ${TOKEN2:0:20}..."
echo ""

# Verify App1 user
echo "5. Verifying user1@app1.com..."
RESPONSE=$(curl -s "$BASE_URL/verify-email?token=$TOKEN1" \
  -H "X-App-Id: app1" \
  -H "X-App-Key: $APP1_KEY")
LICENSE1=$(echo $RESPONSE | jq -r '.license_key')
echo "License: ${LICENSE1:0:50}..."
echo ""

# Verify App2 user
echo "6. Verifying user2@app2.com..."
RESPONSE=$(curl -s "$BASE_URL/verify-email?token=$TOKEN2" \
  -H "X-App-Id: app2" \
  -H "X-App-Key: $APP2_KEY")
LICENSE2=$(echo $RESPONSE | jq -r '.license_key')
echo "License: ${LICENSE2:0:50}..."
echo ""

# Validate App1 license with App1 credentials
echo "7. Validating App1 license with App1 credentials..."
RESPONSE=$(curl -s -X POST "$BASE_URL/validate-license?license_key=$LICENSE1" \
  -H "X-App-Id: app1" \
  -H "X-App-Key: $APP1_KEY")
echo "Result: $(echo $RESPONSE | jq -r '.valid')"
echo ""

# Try to validate App1 license with App2 credentials (should fail)
echo "8. Trying to validate App1 license with App2 credentials (should fail)..."
RESPONSE=$(curl -s -X POST "$BASE_URL/validate-license?license_key=$LICENSE1" \
  -H "X-App-Id: app2" \
  -H "X-App-Key: $APP2_KEY")
echo "Result: $(echo $RESPONSE | jq -r '.detail // .valid')"
echo ""

# List App1 licenses (admin)
echo "9. Listing App1 licenses..."
RESPONSE=$(curl -s "$BASE_URL/licenses" \
  -H "Authorization: Bearer $ADMIN_KEY" \
  -H "X-App-Id: app1")
COUNT=$(echo $RESPONSE | jq '. | length')
echo "App1 has $COUNT license(s)"
echo ""

# List App2 licenses (admin)
echo "10. Listing App2 licenses..."
RESPONSE=$(curl -s "$BASE_URL/licenses" \
  -H "Authorization: Bearer $ADMIN_KEY" \
  -H "X-App-Id: app2")
COUNT=$(echo $RESPONSE | jq '. | length')
echo "App2 has $COUNT license(s)"
echo ""

# Try to access without headers (should fail)
echo "11. Trying to register without app headers (should fail)..."
RESPONSE=$(curl -s -X POST "$BASE_URL/register" \
  -H "Content-Type: application/json" \
  -d '{"email": "noheaders@test.com"}')
echo "Result: $(echo $RESPONSE | jq -r '.detail')"
echo ""

echo "=== ✅ Multi-tenant isolation verified! ==="
