# Run Azad-UAE locally in production-like mode (loads .env.production.local).
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$EnvFile = Join-Path $Root '.env.production.local'
if (-not (Test-Path $EnvFile)) {
    Write-Host 'Missing .env.production.local — copy from .env.production.example and fill secrets.'
    exit 1
}

function Import-DotEnvFile {
    param([string]$Path)
    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if ($line -eq '' -or $line.StartsWith('#')) { return }
        $eq = $line.IndexOf('=')
        if ($eq -lt 1) { return }
        $name = $line.Substring(0, $eq).Trim()
        $value = $line.Substring($eq + 1).Trim()
        if ($value.StartsWith('"') -and $value.EndsWith('"')) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        Set-Item -Path "Env:$name" -Value $value
    }
}

Import-DotEnvFile $EnvFile

# Force local bind even if .env omitted HOST
if (-not $env:HOST) { $env:HOST = '127.0.0.1' }
if (-not $env:PORT) { $env:PORT = '5000' }

Write-Host 'Loaded .env.production.local (secrets not displayed).'
Write-Host "APP_ENV=$env:APP_ENV DEBUG=$env:DEBUG HOST=$env:HOST PORT=$env:PORT"

Write-Host 'Running create_app smoke test...'
$env:SKIP_SYSTEM_INTEGRITY = '1'
python -c "from app import create_app; create_app(); print('create_app OK')"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Remove-Item Env:SKIP_SYSTEM_INTEGRITY -ErrorAction SilentlyContinue

Write-Host ''
Write-Host 'Starting server (production-like)...'
Write-Host 'URL: http://127.0.0.1:' $env:PORT
Write-Host 'Note: DEBUG=false sets secure session cookies — login over plain HTTP may not persist.'
Write-Host ''

python app.py
