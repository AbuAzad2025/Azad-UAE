#!/usr/bin/env bash
# Azad-UAE DevSecOps Audit Runner (Linux / WSL / macOS)
# Stages: Auto-Fix -> Read-Only Diagnostics -> Vulnerability Scan -> Infra
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
pass() { echo -e " ${GREEN}[PASS]${NC} $1"; }
fail() { echo -e " ${RED}[FAIL]${NC} $1"; EXIT=1; }
info() { echo -e " ${CYAN}[INFO]${NC} $1"; }
warn() { echo -e " ${YELLOW}[WARN]${NC} $1"; }
EXIT=0

export PYTHONIOENCODING=utf-8

echo -e "\n${CYAN}==================================================${NC}"
echo -e "${CYAN}   Azad-UAE - Full DevSecOps Audit Pipeline${NC}"
echo -e "${CYAN}==================================================${NC}\n"

# --- Stage 1: Auto-Fixes ---
echo -e "\n${YELLOW}--- Stage 1: Auto-Fixes ---${NC}\n"

if python -m ruff --version &>/dev/null; then
  info "Ruff check --fix ..."
  python -m ruff check --fix . 2>&1 | tail -5 || warn "ruff check --fix had issues"
  info "Ruff format ..."
  python -m ruff format . 2>&1 | tail -3 || warn "ruff format had issues"
  pass "Ruff auto-fix complete"
else
  fail "ruff not found - install with: pip install ruff"
fi

if command -v biome &>/dev/null; then
  info "Biome check --write (JS/CSS/JSON) ..."
  biome check --write . 2>&1 | tail -5 || warn "biome had issues"
  pass "Biome auto-fix complete"
else
  warn "biome not found - install with: npm install -g @biomejs/biome"
fi

# --- Stage 2: Read-Only Diagnostics ---
echo -e "\n${YELLOW}--- Stage 2: Quality and Security Diagnostics ---${NC}\n"

if python -m mypy --version &>/dev/null; then
  info "Mypy type checking ..."
  python -m mypy . --ignore-missing-imports --no-error-summary --explicit-package-bases 2>&1 | tail -20 || fail "mypy found type errors"
else
  fail "mypy not found - install with: pip install mypy"
fi

if python -m bandit --version &>/dev/null; then
  info "Bandit security scan ..."
  python -m bandit -r . -x ./tests,./.venv,./migrations,./node_modules 2>&1 | tail -20 || fail "bandit found issues"
else
  fail "bandit not found - install with: pip install bandit"
fi

if python -m pip_audit --version &>/dev/null; then
  info "pip-audit vulnerability scan ..."
  python -m pip_audit -r requirements.txt 2>&1 | tail -20 || fail "pip-audit found vulnerabilities"
else
  warn "pip-audit not found - install with: pip install pip-audit"
fi

# --- Stage 3: i18n & Translation Guard ---
echo -e "\n${YELLOW}--- Stage 3: i18n & Localization Audit ---${NC}\n"

info "Strict i18n lint ..."
python scripts/check_strict_i18n.py templates routes services || fail "Strict i18n check failed"

if command -v cspell &>/dev/null; then
  info "Cspell spell check ..."
  npx cspell --config scripts/lint/.cspell.json "templates/**/*.html" "static/js/**/*.js" "docs/**/*.md" || fail "cspell found typos"
else
  warn "cspell not found - install with: npm install -g cspell"
fi

# --- Stage 4: Gitleaks (if available) ---
echo -e "\n${YELLOW}--- Stage 4: Secret Scanning ---${NC}\n"

if command -v gitleaks &>/dev/null; then
  info "Gitleaks secret scan ..."
  gitleaks detect --source . --no-git --verbose 2>&1 | tail -20 || warn "gitleaks found potential secrets"
else
  warn "gitleaks not found - install from https://github.com/gitleaks/gitleaks"
fi

# --- Stage 5: Docker audit (if Dockerfile present) ---
echo -e "\n${YELLOW}--- Stage 5: Docker Infrastructure Audit ---${NC}\n"

if [ -f scripts/lint/Dockerfile.ci ]; then
  if command -v hadolint &>/dev/null; then
    info "Hadolint Dockerfile audit ..."
    hadolint scripts/lint/Dockerfile.ci --config scripts/.hadolint.yaml || warn "hadolint found issues"
  else
    warn "hadolint not found - install from https://github.com/hadolint/hadolint"
  fi
fi

if command -v trivy &>/dev/null; then
  info "Trivy filesystem scan ..."
  trivy fs --severity HIGH,CRITICAL --exit-code 1 --no-progress . 2>&1 | tail -20 || fail "trivy found high/critical vulnerabilities"
else
  warn "trivy not found - install from https://github.com/aquasecurity/trivy"
fi

# --- Stage 6: Tenant isolation fuzzer ---
echo -e "\n${YELLOW}--- Stage 6: Tenant Isolation Fuzzer ---${NC}\n"

if python -m pytest --version &>/dev/null; then
  if [ -n "${DATABASE_URL:-}" ]; then
    info "Running tenant isolation fuzzer ..."
    python -m pytest tests/unit/utils/test_tenant_isolation_fuzzer.py -v --tb=short 2>&1 | tail -20 || fail "Tenant isolation tests failed"
  else
    warn "DATABASE_URL not set — skipping tenant isolation fuzzer (needs DB)"
  fi
else
  warn "pytest not found — skipping tenant isolation fuzzer"
fi

# --- Done ---
echo ""
if [ "$EXIT" -eq 0 ]; then
  pass "All stages completed - no blocking issues"
else
  fail "Some stages reported issues - review logs above"
fi
exit $EXIT
