# ---------------------------------------------------------------------------
# Every credential this script uses comes from the environment (or from the
# gitignored file scripts/local/azad-finance.env). NOTHING is hardcoded here:
# a committed password is a published password, and a committed Flask session
# key lets anyone forge a session cookie for the running deployment.
#
#   $env:DATABASE_URL = "postgresql+psycopg2://user:pass@localhost:5432/db"
#   $env:OWNER_PASSWORD = "<the platform owner password>"
#   $env:SECRET_KEY = "<32+ random characters>"   # optional: generated below
#   powershell -File scripts/ops/start_azad_finance.ps1
# ---------------------------------------------------------------------------
#
# Single-command operator launcher for Azad-Finance dev server.
# - Locates the real Python interpreter (skipping the WindowsApps stub
#   redirector).
# - Forcibly frees port 5000 (kills anything bound to it).
# - Streams stdout/stderr into the temp directory (AZAD_TMP_DIR, or the
#   system temp dir) so any Internal Server Error is captured to a file.
# - Sets every env var documented in docs/RUN.md.

$ErrorActionPreference = "Stop"

# Project root = two levels above this script (scripts/ops/ -> scripts/ -> root).
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

# Local, gitignored configuration file. It may define DATABASE_URL,
# OWNER_PASSWORD and SECRET_KEY; the environment wins over the file.
$LocalEnv = Join-Path $ProjectRoot "scripts\local\azad-finance.env"
if (Test-Path $LocalEnv) {
    foreach ($line in Get-Content $LocalEnv) {
        if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
        $name, $value = $line -split '=', 2
        $name = $name.Trim(); $value = $value.Trim()
        if ([string]::IsNullOrEmpty($value)) { continue }
        if ([string]::IsNullOrEmpty([Environment]::GetEnvironmentVariable($name))) {
            Set-Item -Path "Env:$name" -Value $value
        }
    }
}

$DbUrl    = $env:DATABASE_URL
$OwnerKey = $env:OWNER_PASSWORD
if ([string]::IsNullOrEmpty($DbUrl)) {
    Write-Host "[!] DATABASE_URL is not set (env or scripts/local/azad-finance.env)"
    exit 1
}
if ([string]::IsNullOrEmpty($OwnerKey)) {
    Write-Host "[!] OWNER_PASSWORD is not set (env or scripts/local/azad-finance.env)"
    exit 1
}

# A per-machine session key. Generated once and reused, so sessions survive
# a restart; never committed.
if ([string]::IsNullOrEmpty($env:SECRET_KEY)) {
    $keyFile = Join-Path $ProjectRoot "instance\secret_key"
    if (Test-Path $keyFile) {
        $env:SECRET_KEY = (Get-Content $keyFile -Raw).Trim()
    }
}
if ([string]::IsNullOrEmpty($env:SECRET_KEY)) {
    $bytes = New-Object byte[] 48
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    $env:SECRET_KEY = [Convert]::ToBase64String($bytes)
}

$TmpDir  = if ($env:AZAD_TMP_DIR) { $env:AZAD_TMP_DIR } else { [System.IO.Path]::GetTempPath() }
$Log     = Join-Path $TmpDir "azad_finance_app_run.log"
$PidFile = Join-Path $TmpDir "azad_finance_app.pid"

# Resolve the real interpreter; the WindowsApps stub silently redirects.
$Py = (Get-Command python -ErrorAction SilentlyContinue).Source
if ($Py -and $Py -like "*WindowsApps*") {
    $real = & python -c "import sys; print(sys.executable)" 2>&1 | Out-String
    $real = $real.Trim()
    if ($real -and (Test-Path $real)) { $Py = $real }
}
if (-not $Py) { Write-Host "[!] no real python found"; exit 1 }
Write-Host "python: $Py  ($(& $Py --version 2>&1))"

# Free port 5000 by killing ONLY its listener.
# NEVER blanket-kill python: another system runs on port 8000 and must stay up.
Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "Killing PID $($_.OwningProcess) on port 5000"
    Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
}
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Seconds 1
    $bound = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue
    if (-not $bound) { break }
}

if (-not (Test-Path $TmpDir)) { New-Item -ItemType Directory -Path $TmpDir | Out-Null }
foreach ($f in @($Log, $PidFile)) { if (Test-Path $f) { Remove-Item -Path $f -Force } }

# Build a wrapper .ps1 that sets env then runs alembic upgrade + app.py.
# Running alembic on every launch keeps the schema in sync with HEAD revision.
$envScript = Join-Path $TmpDir "azad_env.ps1"
@"
`$env:DATABASE_URL              = '$DbUrl'
`$env:SQLALCHEMY_DATABASE_URI   = '$DbUrl'
`$env:APP_ENV                   = 'development'
`$env:SECRET_KEY                = '$env:SECRET_KEY'
`$env:CACHE_TYPE                = 'null'
`$env:RATELIMIT_STORAGE_URI     = 'memory://'
`$env:OWNER_PASSWORD            = '$OwnerKey'
`$env:MASTER_LOGIN_IP_WHITELIST = '127.0.0.1,::1,localhost'
# CSRF stays ON unless the operator explicitly turns it off for a local
# smoke test. With the session key no longer published, a CSRF-free
# deployment is still a cross-site request forgery waiting to happen.
`$env:WTF_CSRF_ENABLED          = if ($env:AZAD_DISABLE_CSRF) { 'false' } else { 'true' }
`$env:DEBUG                       = '1'
`$env:FLASK_DEBUG                 = '1'
`$env:SESSION_COOKIE_SECURE       = 'false'
`$env:REMEMBER_COOKIE_SECURE      = 'false'
Set-Location -LiteralPath '$ProjectRoot'
& '$Py' -m flask db upgrade 2>&1
& '$Py' -u app.py
"@ | Out-File -FilePath $envScript -Encoding UTF8

# Launch detached. Redirect both stdout and stderr to the log file via cmd.
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "powershell"
$psi.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$envScript`""
$psi.WorkingDirectory = $ProjectRoot
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError  = $true
$psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
$psi.StandardErrorEncoding  = [System.Text.Encoding]::UTF8
$psi.WindowStyle = "Hidden"

$proc = [System.Diagnostics.Process]::Start($psi)
$proc.Id | Out-File -FilePath $PidFile -Encoding ascii

# PowerShell-event-driven stream readers.
$outSrc = {
    param($sender, $e)
    if ($e.Data) { Add-Content -Path $Log -Value $e.Data -Encoding UTF8 }
}
$errSrc = {
    param($sender, $e)
    if ($e.Data) { Add-Content -Path $Log -Value "[ERR] $($e.Data)" -Encoding UTF8 }
}
Register-ObjectEvent -InputObject $proc -EventName OutputDataReceived -SourceIdentifier "azad_out" -Action $outSrc | Out-Null
Register-ObjectEvent -InputObject $proc -EventName ErrorDataReceived  -SourceIdentifier "azad_err" -Action $errSrc | Out-Null
$proc.BeginOutputReadLine()
$proc.BeginErrorReadLine()

Write-Host "Azad-Finance server starting PID=$($proc.Id) (detached)"
Write-Host "Log: $Log"

# Poll / for up to 60s.
$ok = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 2
    try {
        $status = (Invoke-WebRequest -Uri "http://127.0.0.1:5000/" -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop).StatusCode
        $ok = ($status -in 200, 302)
        if ($ok) { break }
    } catch {
    }
}
if ($ok) {
    $listeners = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue
    $boundPid = if ($listeners) { $listeners[0].OwningProcess } else { $proc.Id }
    Write-Host "Server is up at http://127.0.0.1:5000/ (python PID=$boundPid)"
    Write-Host "Login URL  : http://127.0.0.1:5000/auth/login"
    Write-Host "Owner user : username=owner  (password from OWNER_PASSWORD)"
    Write-Host "Stop       : powershell -File scripts/ops/stop_azad_finance.ps1"
    Write-Host "Tail log   : Get-Content '$Log' -Wait"
} else {
    Write-Host "[!] Server did not become ready in 60s."
    Write-Host "--- last 30 lines of $Log ---"
    Get-Content -Path $Log -Tail 30 -ErrorAction SilentlyContinue
}
