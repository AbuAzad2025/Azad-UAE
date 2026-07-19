<#
.SYNOPSIS
    Azad-UAE DevSecOps Audit Runner (Windows PowerShell)
.DESCRIPTION
    Stages: Auto-Fix -> Read-Only Diagnostics -> Vulnerability Scan
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

# --- Done ---
Write-Host ""
if ($Global:EXIT -eq 0) {
    pass "All stages completed - no blocking issues"
} else {
    fail "Some stages reported issues - review logs above"
}
exit $Global:EXIT
