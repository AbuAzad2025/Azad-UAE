# stop_azad_finance.ps1 - stop ONLY the Azad-Finance server on port 5000.
#
# NEVER blanket-kill python: another system runs on port 8000 on this
# machine and must stay up.

$ErrorActionPreference = "Stop"
$TmpDir  = "C:\Users\azad1\AppData\Local\Temp\opencode"
$PidFile = Join-Path $TmpDir "app.pid"

# 1) Kill the listener actually bound to port 5000 (authoritative owner).
$listeners = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue
foreach ($l in $listeners) {
    $ownerPid = [int]$l.OwningProcess
    Write-Host "Stopping port-5000 listener PID=$ownerPid"
    Stop-Process -Id $ownerPid -Force -ErrorAction SilentlyContinue
}

# 2) Kill the PID recorded by the launcher, but ONLY if it is still the
#    port-5000 owner (never touch foreign PIDs like the :8000 system).
if (Test-Path $PidFile) {
    $rawPid = (Get-Content -Path $PidFile -Raw -ErrorAction SilentlyContinue).Trim()
    if ($rawPid -match '^\d+$') {
        $stillBound = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue |
            Where-Object { [int]$_.OwningProcess -eq [int]$rawPid }
        if ($stillBound) {
            Write-Host "Stopping recorded launcher PID=$rawPid"
            Stop-Process -Id ([int]$rawPid) -Force -ErrorAction SilentlyContinue
        }
    }
    Remove-Item -Path $PidFile -Force -ErrorAction SilentlyContinue
}

Start-Sleep -Seconds 2
$bound = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue
if ($bound) {
    Write-Host "still bound on port 5000:"
    $bound | Format-List LocalAddress, OwningProcess
} else {
    Write-Host "port 5000 is free (port 8000 untouched)"
}
