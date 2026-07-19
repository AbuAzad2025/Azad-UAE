#!/usr/bin/env bash
# Azad-UAE DevSecOps Audit Runner (Linux / WSL / macOS)
# Stages: Auto-Fix -> Read-Only Diagnostics -> Vulnerability Scan
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

# --- Done ---
echo ""
if [ "$EXIT" -eq 0 ]; then
  pass "All stages completed - no blocking issues"
else
  fail "Some stages reported issues - review logs above"
fi
exit $EXIT
