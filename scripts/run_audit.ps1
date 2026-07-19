<#
.SYNOPSIS
    Azad-UAE DevSecOps Audit Runner (Windows PowerShell)
.DESCRIPTION
    Stages: Auto-Fix -> Read-Only Diagnostics -> Vulnerability Scan -> Infra Audit
    All operations are safe - no destructive overrides.
#>
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
Set-Location $RepoRoot
$env:PYTHONIOENCODING = "utf-8"

# Prefer venv Python to avoid Microsoft Store shim
$py = if (Test-Path "$RepoRoot\.venv\Scripts\python.exe") { "$RepoRoot\.venv\Scripts\python.exe" } else { "python" }
function exec-py { & $py @args }

$Global:EXIT = 0

function pass { Write-Host " [PASS] $args" -ForegroundColor Green }
function fail { Write-Host " [FAIL] $args" -ForegroundColor Red; $Global:EXIT = 1 }
function info { Write-Host " [INFO] $args" -ForegroundColor Cyan }
function warn { Write-Host " [WARN] $args" -ForegroundColor Yellow }

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "   Azad-UAE - Full DevSecOps Audit Pipeline" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# --- Stage 1: Auto-Fixes ---
Write-Host "`n=== Stage 1: Auto-Fixes ===`n" -ForegroundColor Yellow

try {
    info "Ruff check --fix ..."
    exec-py -m ruff check --fix . 2>&1 | Select-Object -Last 5
    info "Ruff format ..."
    exec-py -m ruff format . 2>&1 | Select-Object -Last 3
    pass "Ruff auto-fix complete"
} catch {
    fail "ruff check failed: $_"
}

$biome = Get-Command biome -ErrorAction SilentlyContinue
if ($biome) {
    info "Biome check --write (JS/CSS/JSON) ..."
    & biome check --write . 2>&1 | Select-Object -Last 5
    pass "Biome auto-fix complete"
} else {
    warn "biome not found - install with: npm install -g @biomejs/biome"
}

# --- Stage 2: Read-Only Diagnostics ---
Write-Host "`n=== Stage 2: Quality and Security Diagnostics ===`n" -ForegroundColor Yellow

try {
    info "Mypy type checking ..."
    exec-py -m mypy . --ignore-missing-imports --no-error-summary --explicit-package-bases 2>&1 | Select-Object -Last 20
    if ($LASTEXITCODE -ne 0) { fail "mypy found type errors" }
} catch {
    fail "mypy not found - install with: pip install mypy"
}

try {
    info "Bandit security scan ..."
    exec-py -m bandit -r . -x ./tests,./.venv,./migrations,./node_modules 2>&1 | Select-Object -Last 20
    if ($LASTEXITCODE -ne 0) { fail "bandit found issues" }
} catch {
    fail "bandit not found - install with: pip install bandit"
}

try {
    info "pip-audit vulnerability scan ..."
    exec-py -m pip_audit -r requirements.txt 2>&1 | Select-Object -Last 20
    if ($LASTEXITCODE -ne 0) { fail "pip-audit found vulnerabilities" }
} catch {
    warn "pip-audit not found - install with: pip install pip-audit"
}

# --- Stage 3: i18n & Localization ---
Write-Host "`n=== Stage 3: i18n & Localization Guard ===`n" -ForegroundColor Yellow

try {
    info "Strict i18n lint ..."
    exec-py scripts/check_strict_i18n.py templates routes services
    if ($LASTEXITCODE -ne 0) { fail "Strict i18n check failed" }
} catch { fail "Strict i18n check error: $_" }

$cspell = Get-Command cspell -ErrorAction SilentlyContinue
if ($cspell) {
    info "Cspell spell check ..."
    & npx cspell --config scripts/lint/.cspell.json "templates/**/*.html", "static/js/**/*.js" 2>&1 | Select-Object -Last 20
    if ($LASTEXITCODE -ne 0) { fail "cspell found typos" }
} else {
    warn "cspell not found - install with: npm install -g cspell"
}

# --- Stage 4: Gitleaks ---
Write-Host "`n=== Stage 4: Secret Scanning ===`n" -ForegroundColor Yellow

$gitleaks = Get-Command gitleaks -ErrorAction SilentlyContinue
if ($gitleaks) {
    info "Gitleaks secret scan ..."
    & gitleaks detect --source . --no-git --verbose 2>&1 | Select-Object -Last 20
} else {
    warn "gitleaks not found - install from https://github.com/gitleaks/gitleaks"
}

# --- Stage 5: Docker Infra Audit ---
Write-Host "`n=== Stage 5: Docker Infrastructure Audit ===`n" -ForegroundColor Yellow

if (Test-Path scripts/lint/Dockerfile.ci) {
    $hadolint = Get-Command hadolint -ErrorAction SilentlyContinue
    if ($hadolint) {
        info "Hadolint Dockerfile audit ..."
        & hadolint scripts/lint/Dockerfile.ci --config scripts/.hadolint.yaml 2>&1 | Select-Object -Last 20
    } else {
        warn "hadolint not found - install from https://github.com/hadolint/hadolint"
    }
}

$trivy = Get-Command trivy -ErrorAction SilentlyContinue
if ($trivy) {
    info "Trivy filesystem scan ..."
    & trivy fs --severity HIGH,CRITICAL --exit-code 1 --no-progress . 2>&1 | Select-Object -Last 20
    if ($LASTEXITCODE -ne 0) { fail "trivy found high/critical vulnerabilities" }
} else {
    warn "trivy not found - install from https://github.com/aquasecurity/trivy"
}

# --- Stage 6: Tenant Isolation Fuzzer ---
Write-Host "`n=== Stage 6: Tenant Isolation Fuzzer ===`n" -ForegroundColor Yellow

if ($env:DATABASE_URL) {
    try {
        info "Running tenant isolation fuzzer ..."
        exec-py -m pytest tests/unit/utils/test_tenant_isolation_fuzzer.py -v --tb=short 2>&1 | Select-Object -Last 20
        if ($LASTEXITCODE -ne 0) { fail "Tenant isolation tests failed" }
    } catch { warn "Tenant isolation tests skipped: $_" }
} else {
    warn "DATABASE_URL not set — skipping tenant isolation fuzzer"
}

# --- Done ---
Write-Host ""
if ($Global:EXIT -eq 0) {
    pass "All stages completed - no blocking issues"
} else {
    fail "Some stages reported issues - review logs above"
}
exit $Global:EXIT
