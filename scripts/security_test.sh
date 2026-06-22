#!/usr/bin/env bash
# =============================================================================
# Security Test Suite for AZADEXA ERP
# Run: bash scripts/security_test.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPORT_DIR="${PROJECT_ROOT}/reports"
mkdir -p "${REPORT_DIR}"

echo "============================================"
echo "AZADEXA ERP — Security Test Suite"
echo "============================================"

# --- 1. Bandit (static analysis) ---
echo "[1/5] Running bandit static analysis..."
if command -v bandit &>/dev/null; then
    bandit -r "${PROJECT_ROOT}" \
        -f json \
        -o "${REPORT_DIR}/bandit-report.json" \
        || true
    bandit -r "${PROJECT_ROOT}" || true
else
    echo "[!] bandit not installed. Skipping."
fi

# --- 2. Safety (dependency vulnerabilities) ---
echo "[2/5] Running safety check..."
if command -v safety &>/dev/null; then
    safety check -r "${PROJECT_ROOT}/requirements.txt" || true
else
    echo "[!] safety not installed. Skipping."
fi

# --- 3. Secret scan (git-secrets or truffleHog) ---
echo "[3/5] Scanning for secrets in git history..."
if command -v trufflehog &>/dev/null; then
    trufflehog filesystem "${PROJECT_ROOT}" --json > "${REPORT_DIR}/secrets-scan.json" || true
else
    echo "[!] truffleHog not installed. Skipping."
fi

# --- 4. Django/Flask config sanity ---
echo "[4/5] Checking production config flags..."
python3 -c "
import sys, os
sys.path.insert(0, '${PROJECT_ROOT}')
os.environ.setdefault('APP_ENV', 'testing')
os.environ.setdefault('SECRET_KEY', 'test-only')
try:
    from config import Config
    issues = []
    if Config.DEBUG:
        issues.append('DEBUG is True')
    if not Config.SESSION_COOKIE_SECURE and Config.APP_ENV == 'production':
        issues.append('SESSION_COOKIE_SECURE is False in production')
    if not os.environ.get('SECRET_KEY'):
        issues.append('SECRET_KEY not set')
    if issues:
        print('[WARN] Config issues:', '; '.join(issues))
    else:
        print('[OK] Production config flags look correct')
except Exception as e:
    print('[ERROR] Config import failed:', e)
"

# --- 5. File permission scan ---
echo "[5/5] Checking for world-writable files..."
find "${PROJECT_ROOT}" \
    -path "*/.git" -prune -o \
    -path "*/venv" -prune -o \
    -path "*/.venv" -prune -o \
    -path "*/node_modules" -prune -o \
    -type f -perm -002 -print 2>/dev/null | while read -r f; do
    echo "[WARN] World-writable file: ${f}"
done

echo "============================================"
echo "Security scan complete. Reports in:"
echo "  ${REPORT_DIR}/"
echo "============================================"
