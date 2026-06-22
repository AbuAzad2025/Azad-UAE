#!/usr/bin/env bash
# =============================================================================
# Run performance tests for AZADEXA ERP
# Usage: bash scripts/run_performance.sh [url] [requests] [concurrency]
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

URL="${1:-http://localhost:5000/auth/login}"
REQUESTS="${2:-100}"
CONCURRENCY="${3:-10}"

echo "============================================"
echo "AZADEXA ERP — Performance Test Runner"
echo "============================================"
echo "Target URL:    ${URL}"
echo "Requests:      ${REQUESTS}"
echo "Concurrency:   ${CONCURRENCY}"
echo ""

cd "${PROJECT_ROOT}"

# Ensure app is running before load test
echo "[CHECK] Verifying target is reachable..."
if curl -sf "${URL}" > /dev/null 2>&1; then
    echo "[OK] Target is reachable."
else
    echo "[WARN] Target not reachable. Make sure the app is running:"
    echo "       flask run  OR  docker-compose -f docker-compose.staging.yml up -d"
    echo ""
fi

# Run the Python performance test
echo "[RUN] Starting load test..."
python3 "${SCRIPT_DIR}/performance_test.py" "${URL}" "${REQUESTS}" "${CONCURRENCY}"

echo ""
echo "============================================"
echo "Performance test complete."
echo "============================================"
