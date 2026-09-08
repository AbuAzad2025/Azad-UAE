# start_azad_finance.ps1
#
# Single-command operator launcher for Azad-Finance dev server.
# - Locates the real Python interpreter (skipping the WindowsApps stub
#   redirector).
# - Forcibly frees port 5000 (kills anything bound to it).
# - Streams stdout/stderr into C:\Users\azad1\AppData\Local\Temp\opencode\app_run.log
#   so any Internal Server Error from /payment-vault/* is captured to file.
# - Sets every env var documented in docs/RUN.md.

$ErrorActionPreference = "Stop"
$ProjectRoot = "D:\recovers\data\karaj\azad-uae"
$DbUrl       = "postgresql+psycopg2://postgres:123@localhost:5432/Azad-Finance"
$OwnerKey    = "AlHazem-Finance-MasterKey-2026!"
$TmpDir      = "C:\Users\azad1\AppData\Local\Temp\opencode"
$Log         = Join-Path $TmpDir "app_run.log"
$PidFile     = Join-Path $TmpDir "app.pid"

# Resolve the real interpreter; the WindowsApps stub silently redirects.
$Py = (Get-Command python -ErrorAction SilentlyContinue).Source
if ($Py -and $Py -like "*WindowsApps*") {
    $real = & python -c "import sys; print(sys.executable)" 2>&1 | Out-String
    $real = $real.Trim()
    if ($real -and (Test-Path $real)) { $Py = $real }
}
if (-not $Py) { Write-Host "[!] no real python found"; exit 1 }
Write-Host "python: $Py  ($(& $Py --version 2>&1))"

# Free port 5000 by killing the listener (best-effort) and all python procs.
Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "Killing PID $($_.OwningProcess) on port 5000"
    Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
}
Get-Process python -ErrorAction SilentlyContinue | ForEach-Object {
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
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
`$env:SECRET_KEY                = 'dev-secret-key-not-for-production'
`$env:CACHE_TYPE                = 'null'
`$env:RATELIMIT_STORAGE_URI     = 'memory://'
`$env:OWNER_PASSWORD            = '$OwnerKey'
`$env:MASTER_LOGIN_IP_WHITELIST = '127.0.0.1,::1,localhost'
`$env:WTF_CSRF_ENABLED          = 'false'
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
    Write-Host "Owner user : username=owner  password=$OwnerKey"
    Write-Host "Stop       : powershell -File scripts/ops/stop_azad_finance.ps1"
    Write-Host "Tail log   : Get-Content '$Log' -Wait"
} else {
    Write-Host "[!] Server did not become ready in 60s."
    Write-Host "--- last 30 lines of $Log ---"
    Get-Content -Path $Log -Tail 30 -ErrorAction SilentlyContinue
}
