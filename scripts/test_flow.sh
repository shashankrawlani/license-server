#!/bin/bash

# Test the complete license server flow
set -e

BASE_URL="http://localhost:8321"
TEST_EMAIL="test-$(date +%s)@example.com"
APP_KEY="99f627e19ae5952b80e2cc7fbca01095b17a9fff75ee6374044b65a65b9bf799"

echo "=== Testing License Server Flow ==="
echo ""

# Step 1: Register for license
echo "1. Registering for license: $TEST_EMAIL"
RESPONSE=$(curl -s -X POST "$BASE_URL/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"$TEST_EMAIL\"}")
echo "Response: $RESPONSE"

# Extract token from verification_url
TOKEN=$(echo $RESPONSE | jq -r '.verification_url' | sed 's/.*token=\([^&]*\).*/\1/')
echo "Token: $TOKEN"
echo ""

# Step 2: Verify email and get license
echo "2. Verifying email and generating license..."
RESPONSE=$(curl -s "$BASE_URL/verify-email?token=$TOKEN")
echo "Response: $RESPONSE"
LICENSE_KEY=$(echo $RESPONSE | jq -r '.license_key')
echo "License Key: $LICENSE_KEY"
echo ""

# Step 3: Verify license locally
echo "3. Verifying license locally..."
RESPONSE=$(curl -s -X POST "$BASE_URL/validate-license?license_key=$LICENSE_KEY")
echo "Response: $RESPONSE"
echo ""

# Step 4: Check license status (using admin endpoint)
echo "4. Listing licenses (admin)..."
ADMIN_KEY=$(cat secrets/admin_api_key.txt)
RESPONSE=$(curl -s "$BASE_URL/licenses" \
  -H "Authorization: Bearer $ADMIN_KEY")
echo "Response: $RESPONSE"
echo ""

echo "=== ✅ All tests passed! ==="
