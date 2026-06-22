#!/bin/bash
set -e

STAGING_URL=${1:-http://localhost:5000}

echo "=== Security Tests ==="

# SQLMap
echo "[1/3] Running sqlmap..."
pip install sqlmap -q
sqlmap -u "$STAGING_URL/auth/login" \
  --data="username=test&password=test" \
  --batch --level=2 || true

# Headers check
echo "[2/3] Checking security headers..."
curl -I -s "$STAGING_URL/auth/login" | grep -E "X-Frame-Options|X-Content-Type-Options|Strict-Transport-Security" || true

# Nmap (if available)
echo "[3/3] Port scan..."
which nmap && nmap -p 22,80,443,5000 $(echo $STAGING_URL | sed 's|http://||;s|https://||;s|:.*||') || echo "nmap not installed"

echo "=== Done ==="
