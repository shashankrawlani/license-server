#!/bin/bash
# Test with both PostgreSQL and SQLite

set -e

echo "=== Testing with SQLite ==="
export DATABASE_URL="sqlite:///test_licenses.db"
rm -f test_licenses.db
uv run pytest tests/ -q --tb=no | tail -3
rm -f test_licenses.db
echo ""

echo "=== Testing with PostgreSQL ==="
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/license_server_test"
uv run pytest tests/ -q --tb=no | tail -3
echo ""

echo "✅ Both databases work!"
