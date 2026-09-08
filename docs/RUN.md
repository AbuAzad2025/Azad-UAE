# RUN — Operator Runbook

A single cheat-sheet for spinning up the Azad-Finance dev server with the
minimum set of env vars that prevent the embarrassing regressions
(Internal Server Error on `/payment-vault/unlock`, 404 on `/owner/*`).

## Prerequisites

| Component | Required value on this machine |
|---|---|
| Postgres | running on `localhost:5432`, user `postgres`, password `123` |
| Python | `C:\Users\azad1\AppData\Local\Python\pythoncore-3.14-64\python.exe` (3.14.6) |
| DB      | Created: `Azad-Finance` (schema migrated to HEAD, system_init run) |
| Owner user | `username=owner`, password = `OWNER_PASSWORD` env (see below) |

## Quick start (one liner)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\ops\start_azad_finance.ps1
```

This:
1. Locates the real python interpreter (skips the WindowsApps stub).
2. Kills any orphan python + frees port 5000.
3. Runs `flask db upgrade head` so the schema matches the latest revision.
4. Starts `app.py` detached; logs go to
   `C:\Users\azad1\AppData\Local\Temp\opencode\app_run.log`.

## Endpoints to know

| Path | Auth | Notes |
|---|---|---|
| http://127.0.0.1:5000/auth/login | none | login form |
| http://127.0.0.1:5000/owner/dashboard | owner | platform-wide owner panel |
| http://127.0.0.1:5000/owner/tenants | owner | all tenants (including nullptr platform vault) |
| http://127.0.0.1:5000/payment-vault/ | owner | vault landing page (click "Unlock") |
| http://127.0.0.1:5000/payment-vault/unlock | owner | enter BTC-style password → unlocks vault |
| http://127.0.0.1:5000/payment-vault/settings | owner (vault unlocked) | edit BTC/ETH/USDT/API keys |

## Mandatory env vars (why each one matters)

| Var | Value | Why |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg2://postgres:123@localhost:5432/Azad-Finance` | pick DB |
| `APP_ENV` | `development` | runs `system_init` on boot; not a production parity check |
| `SECRET_KEY` | `dev-secret-key-not-for-production` | signs session cookies (must match across requests) |
| `CACHE_TYPE` | `null` | disables Redis dep for local dev |
| `RATELIMIT_STORAGE_URI` | `memory://` | disables Redis dep for rate-limiter |
| `OWNER_PASSWORD` | `AlHazem-Finance-MasterKey-2026!` | seed-time owner password (else `_ensure_owner_user` raises on first boot) |
| `MASTER_LOGIN_IP_WHITELIST` | `127.0.0.1,::1,localhost` | permits localhost traffic to owner's IP guard |
| `DEBUG` | `1` | drops `Secure` flag on session cookies (HTTP works) |
| `FLASK_DEBUG` | `1` | werkzeug auto-reload + verbose traceback |
| `SESSION_COOKIE_SECURE` | `false` | belt-and-braces — protects against `config.py:141` flipping it on |
| `WTF_CSRF_ENABLED` | `false` | keeps CLI smoke tests unblocked; browser flow works without it too |

## Failure modes we hit earlier

1. **500 on /payment-vault/unlock**: `payment_logs.tenant_id` was `NOT NULL`.
   The platform vault (`tenant_id IS NULL`) writes audit rows on every unlock
   attempt, which crashed with NotNullViolation. **Fixed by migration
   `7f4c5e2a9011`** (`payment_logs.tenant_id` nullable).
2. **404 on /owner/tenants (and every /owner/*)**: the session cookie carried
   `Secure; HttpOnly` because `SESSION_COOKIE_SECURE = not DEBUG` and `DEBUG=False`.
   Browsers and urllib both refused to re-send the cookie on plain HTTP, so
   `current_user.is_authenticated` returned False and the
   `login_manager.unauthorized` handler aborted with 404. **Fixed by forcing
   `DEBUG=1` + `SESSION_COOKIE_SECURE=false` in the launcher.**
3. **Lock Vault button does nothing / silent placeholder**: the route returned
   a 302 but the JS did `fetch().then(r => r.json())` which couldn't parse the
   HTML and silently swallowed the error. **Fixed by returning JSON when
   `request.is_json` is true; the JS reads `data.redirect` and navigates.**
4. **Stale vault row was never created**: the unlock POST only flushes
   `set_vault_password()` if no row exists. If the platform never committed
   a vault row, every POST tries to log a `vault_unlock_failed` event into a
   `tenant_id=NULL` row, which used to crash. Now that
   `payment_logs.tenant_id` is nullable, logs succeed and the user can retry.

## Seeded entities (post-first-run)

| Entity | ID/details |
|---|---|
| Owner user | `username=owner`, password = `OWNER_PASSWORD` env |
| Currencies | AED (base), ILS, USD |
| Roles | 9 (owner / super_admin / developer / manager / seller / branch_manager / accountant / kitchen / cashier) |
| Permissions | 36 |
| Industry fields | 74 |
| Platform vault | id=1, name="AZAD Platform Vault", password=`TestVaultPass2026!`, BTC=`bc1qtest2026platformvaultforazadowner` (test values; replace) |

## Smoke test

```powershell
powershell -ExecutionPolicy Bypass -File scripts\ops\verify_azad_finance.ps1
```

Walks `/`, `/auth/login`, `/owner/*`, `/payment-vault/*` and prints a
checkmark per status code. Anything ≥ 400 is labelled.

## Stop

```powershell
powershell -ExecutionPolicy Bypass -File scripts\ops\stop_azad_finance.ps1
```

Reads `app.pid`, kills the process, frees port 5000.
