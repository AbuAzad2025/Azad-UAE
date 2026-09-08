# verify_azad_finance.ps1 - health-check the running server.
#
# 1. Anonymous probes (/, /auth/login).
# 2. POST /auth/login with the dev owner credentials.
# 3. Authenticated probes on representative /owner/* routes plus /dashboard.

$ErrorActionPreference = "Stop"
$Base    = "http://127.0.0.1:5000"
$Owner   = "AlHazem-Finance-MasterKey-2026!"

function Step([string]$Label) { Write-Host "" ; Write-Host "== $Label ==" }
function ProbeAnon([string]$Label, [string]$Url) {
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -ErrorAction Stop
        Write-Host ("  {0,-40s} {1}" -f $Label, $r.StatusCode)
    } catch {
        Write-Host ("  {0,-40s} {1}" -f $Label, $_.Exception.Message.Split([char]10)[0])
    }
}

Step "Anonymous surfaces"
ProbeAnon "GET /"                 "$Base/"
ProbeAnon "GET /auth/login"        "$Base/auth/login"
ProbeAnon "GET /dashboard"         "$Base/dashboard"
ProbeAnon "GET /owner/dashboard"   "$Base/owner/dashboard"

Step "POST /auth/login (owner)"
try {
    $login = Invoke-WebRequest -Uri "$Base/auth/login" -Method POST -Body @{
        username   = "owner"
        password   = $Owner
        csrf_token = ""
    } -Headers @{ Referer = "$Base/auth/login" } -UseBasicParsing -MaximumRedirection 0 -ErrorAction Stop
    Write-Host ("  POST /auth/login {0,5} {1}" -f $login.StatusCode, $login.Headers.Location)
    if ($login.StatusCode -ne 302 -and $login.StatusCode -ne 200) {
        Write-Host "[!] login did not return 302 - cookie may not stick."
    }
    if (-not $login.Headers.ContainsKey("Set-Cookie")) {
        Write-Host "[!] login did not return Set-Cookie header."
    } else {
        Write-Host "    cookies received: $($login.Headers["Set-Cookie"])"
    }
} catch {
    Write-Host "  POST /auth/login ERROR: $($_.Exception.Message)"
    exit 1
}

Step "Authenticated /owner/* walk"
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
# Carry session cookies from login response.
foreach ($h in $login.Headers.GetEnumerator()) {
    if ($h.Key -ieq "Set-Cookie") {
        Write-Host "  carrying Set-Cookie: $($h.Value)"
    }
}
$jar = [System.Net.CookieContainer]::new()
$session.Cookies = $jar
foreach ($h in $login.Headers.GetEnumerator()) {
    if ($h.Key -ieq "Set-Cookie") {
        # Cookies from Invoke-WebRequest header are typically combined into a single string
        $cookies = $h.Value
    }
}

# Manual cookie handling since PowerShell does not auto-inject from Set-Cookie.
# Better: use the cookie from $login.BaseResponse.Headers directly via System.Net.CookieContainer.
$cookieStr = (($login.Headers | Where-Object { $_.Key -ieq "Set-Cookie" }).Value) -join "; "
if ($cookieStr) {
    Write-Host "  cookies: $cookieStr"
    foreach ($c in $cookieStr -split "; ?") {
        $pair = $c.Trim()
        if ($pair -match "^(?<name>[^=]+)=(?<val>.*)$") {
            $n = $matches["name"] ; $v = $matches["val"]
            try {
                $session.Cookies.Add([System.Net.Cookie]::new($n, $v))
            } catch {}
        }
    }
}

function ProbeAuthed([string]$Label, [string]$Url) {
    try {
        $r = Invoke-WebRequest -Uri $Url -WebSession $session -UseBasicParsing -ErrorAction Stop
        Write-Host ("  {0,-40s} {1}" -f $Label, $r.StatusCode)
    } catch {
        $msg = $_.Exception.Message.Split([char]10)[0]
        Write-Host ("  {0,-40s} {1}" -f $Label, $msg)
    }
}

ProbeAuthed "GET /owner/master-login-info"     "$Base/owner/master-login-info"
ProbeAuthed "GET /owner/dashboard"             "$Base/owner/dashboard"
ProbeAuthed "GET /owner/tenants"               "$Base/owner/tenants"
ProbeAuthed "GET /owner/users-list"            "$Base/owner/users-list"
ProbeAuthed "GET /owner/system-health"         "$Base/owner/system-health"
ProbeAuthed "GET /owner/api/recent-audit-logs" "$Base/owner/api/recent-audit-logs"
ProbeAuthed "GET /dashboard"                   "$Base/dashboard"
