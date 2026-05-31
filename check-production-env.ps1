# Quick production env check — SET/NOT SET only (never prints secret values).
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvFile = Join-Path $Root '.env.production.local'

function Import-DotEnvFile {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        Write-Host "Missing file: $Path"
        Write-Host 'Copy .env.production.example to .env.production.local first.'
        exit 1
    }
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

function Show-SetStatus {
    param([string]$Name)
    $val = [Environment]::GetEnvironmentVariable($Name, 'Process')
    if ($null -ne $val -and $val.Trim() -ne '') {
        Write-Host "${Name}: SET"
    } else {
        Write-Host "${Name}: NOT SET"
    }
}

Import-DotEnvFile $EnvFile

Write-Host '--- Production-like env status ---'
Show-SetStatus 'SECRET_KEY'
Show-SetStatus 'AZAD_MASTER_DAILY_SEED'
Show-SetStatus 'AZAD_MASTER_KEY_SHA256'
Show-SetStatus 'AZAD_MASTER_LOGIN_DISABLED'
Show-SetStatus 'APP_ENV'
Show-SetStatus 'DEBUG'
Show-SetStatus 'PAYMENT_VAULT_TRUSTED_ORIGINS'
Show-SetStatus 'CORS_ORIGINS'
Show-SetStatus 'NOWPAYMENTS_IPN_SECRET'
Write-Host '---'
Write-Host 'HOST:' ([Environment]::GetEnvironmentVariable('HOST', 'Process'))
Write-Host 'PORT:' ([Environment]::GetEnvironmentVariable('PORT', 'Process'))
Write-Host 'BASE_URL:' ([Environment]::GetEnvironmentVariable('BASE_URL', 'Process'))
Write-Host 'DATABASE_URL:' $(if ([Environment]::GetEnvironmentVariable('DATABASE_URL', 'Process')) { 'SET (value hidden)' } else { 'NOT SET (uses config default)' })
