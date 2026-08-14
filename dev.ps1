# =============================================================================
# Azadexa — Local Development Launcher (Windows / PowerShell)
#
# WHY THIS EXISTS:
#   config.py evaluates Config class attributes at import time, BEFORE
#   `_init_env()` calls load_dotenv(). Real environment variables must therefore
#   be set in the process BEFORE Python starts, otherwise the app boots in
#   "production" mode against the default database URL. This launcher loads
#   .env into the process environment and then starts the dev server.
#
# USAGE:
#   .\dev.ps1                Start the Flask dev server (http://127.0.0.1:5000)
#   .\dev.ps1 flask seed-demo    Run any flask CLI command with .env loaded
# =============================================================================

param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CommandArgs
)

# NOTE: do NOT set $ErrorActionPreference='Stop' here. On PowerShell 5.1 that
# treats any stderr line from a native command (Flask logs to stderr) as a
# terminating error and aborts the run. We use $LASTEXITCODE instead.
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

# --- Load .env into the process environment -------------------------------
$envFile = Join-Path $root '.env'
if (Test-Path -LiteralPath $envFile) {
    Get-Content -LiteralPath $envFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith('#') -and $line -match '^([^=]+)=(.*)$') {
            $key = $Matches[1].Trim()
            $val = $Matches[2].Trim()
            if ($val.Length -ge 2 -and $val[0] -eq $val[-1] -and ($val[0] -eq '"' -or $val[0] -eq "'")) {
                $val = $val.Substring(1, $val.Length - 2)
            }
            [Environment]::SetEnvironmentVariable($key, $val, 'Process')
        }
    }
    Write-Host "[dev.ps1] Environment loaded from $envFile"
} else {
    Write-Warning '.env not found. Copy/create one before starting (see .env in repo root).'
}

$env:FLASK_APP = 'app:create_app'
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw ".venv not found. Run: python -m venv .venv; .venv\Scripts\python.exe -m pip install -r requirements.txt"
}

# --- Ensure the portable GTK runtime (WeasyPrint native libs) is discoverable --
$gtkBin = Join-Path $env:LOCALAPPDATA 'GTK3-Runtime\bin'
if (Test-Path -LiteralPath $gtkBin) {
    if ([Environment]::GetEnvironmentVariable('WEASYPRINT_DLL_DIRECTORIES', 'Process') -notlike "*$gtkBin*") {
        [Environment]::SetEnvironmentVariable('WEASYPRINT_DLL_DIRECTORIES', $gtkBin, 'Process')
        $env:PATH = "$gtkBin;$env:PATH"
        Write-Host "[dev.ps1] GTK runtime added to DLL search path (WeasyPrint PDF)"
    }
} else {
    Write-Warning '[dev.ps1] GTK runtime not found — WeasyPrint PDF export will be unavailable.'
}

# --- Ensure the portable Redis instance is running (cache / Celery broker) ----
$redisExe = Join-Path $env:LOCALAPPDATA 'Redis\redis-server.exe'
if (Test-Path -LiteralPath $redisExe) {
    $redisListening = Get-NetTCPConnection -LocalPort 6379 -State Listen -ErrorAction SilentlyContinue
    if (-not $redisListening) {
        Start-Process -FilePath $redisExe -ArgumentList "--port 6379 --appendonly yes" -WorkingDirectory (Split-Path $redisExe) -WindowStyle Hidden
        Start-Sleep -Seconds 2
        if (Get-NetTCPConnection -LocalPort 6379 -State Listen -ErrorAction SilentlyContinue) {
            Write-Host "[dev.ps1] Portable Redis started on 127.0.0.1:6379"
        } else {
            Write-Warning '[dev.ps1] Redis failed to start — app will fall back to null cache.'
        }
    } else {
        Write-Host "[dev.ps1] Redis already running on 127.0.0.1:6379"
    }
}

# --- Dispatch --------------------------------------------------------------
if ($CommandArgs.Count -gt 0) {
    if ($CommandArgs[0] -eq 'flask') {
        $flaskExe = Join-Path $root '.venv\Scripts\flask.exe'
        $flaskArgs = $CommandArgs[1..($CommandArgs.Count - 1)]
        & $flaskExe @flaskArgs
        exit $LASTEXITCODE
    }
    if ($CommandArgs[0] -eq 'python') {
        $pyArgs = $CommandArgs[1..($CommandArgs.Count - 1)]
        & $python @pyArgs
        exit $LASTEXITCODE
    }
}

Write-Host '[dev.ps1] Starting Flask development server...'
& $python app.py
