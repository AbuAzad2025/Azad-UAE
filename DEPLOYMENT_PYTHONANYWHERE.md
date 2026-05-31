# PythonAnywhere Deployment Plan — Azad-UAE

> **Purpose:** Save deployment steps for later execution.  
> **Target:** Paid PythonAnywhere account + PostgreSQL.  
> **Do not commit secrets.** Use placeholders below and fill on the server only.

---

## 1. Current Project Status

| Check | Status |
|---|---|
| Final Status | **PASS** |
| UAT | **59/59 PASS** |
| pip_audit | **Clean** |
| create_app | **OK** |
| Critical / High (proven) | **None** |
| Cross-tenant leak | **None proven** |

The codebase is ready for deployment and go-live testing after environment and infrastructure setup on PythonAnywhere.

---

## 2. Deployment Method

| Item | Choice |
|---|---|
| Platform | **PythonAnywhere Web App** |
| Config | **Manual configuration** |
| Python | **3.11** virtualenv |
| Database | **PostgreSQL** (PythonAnywhere Databases tab) |
| App server | **WSGI file** → `application = create_app()` |
| Static files | **Web tab static mapping** |
| Production entry | **Do not use** `python app.py` |
| Not used on PA | **Waitress**, **IIS**, **Gunicorn** (PA uses uWSGI via WSGI) |

### Files to deploy

Upload or `git clone`:

```
app.py, config.py, config_redis.py, extensions.py, requirements.txt
routes/, models/, services/, templates/, static/ (assets, not user uploads)
migrations/, utils/, forms/, ai_knowledge/
```

### Do not deploy

```
.venv/, __pycache__/, .env, instance/, logs/, *.db
static/uploads/* (user content — create empty dirs on server)
.codegraph/, tests/, tools/ (optional)
```

---

## 3. Bash Commands (PythonAnywhere console)

Replace `USERNAME` and paths as needed.

```bash
# Clone or upload project
cd ~
git clone https://github.com/AbuAzad2025/Azad-UAE.git
cd ~/Azad-UAE

# Virtualenv (Python 3.11)
mkvirtualenv --python=/usr/bin/python3.11 azad-uae
workon azad-uae

# Dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Runtime directories
mkdir -p ~/Azad-UAE/instance/backups
mkdir -p ~/Azad-UAE/static/uploads/products

# Create .env on server (see section 4 — never commit)
nano ~/Azad-UAE/.env

# Smoke test (after .env exists)
cd ~/Azad-UAE
workon azad-uae
set -a && source .env && set +a
python -c "from app import create_app; create_app(); print('create_app OK')"
```

---

## 4. Production `.env` Template (Placeholders Only)

Create `/home/USERNAME/Azad-UAE/.env` on the server (`chmod 600`).

```bash
# Core
DEBUG=false
APP_ENV=production
FLASK_ENV=production

# Required secrets (generate strong random values)
SECRET_KEY=CHANGE_ME
CARD_ENCRYPTION_KEY=CHANGE_ME
OWNER_PASSWORD=CHANGE_ME

# PostgreSQL (from PythonAnywhere Databases tab)
DATABASE_URL=postgresql+psycopg2://USER:PASS@HOST:5432/DBNAME

# Public HTTPS URL
BASE_URL=https://USERNAME.pythonanywhere.com
PREFERRED_URL_SCHEME=https

# Origins (must match BASE_URL host)
CORS_ORIGINS=https://USERNAME.pythonanywhere.com
PAYMENT_VAULT_TRUSTED_ORIGINS=https://USERNAME.pythonanywhere.com

# Payments (if using NOWPayments)
NOWPAYMENTS_IPN_SECRET=CHANGE_ME
# NOWPAYMENTS_API_KEY=CHANGE_ME

# Cache / rate limit (no Redis on PA unless external)
CACHE_TYPE=simple
RATELIMIT_STORAGE_URI=memory://

# Master login — choose ONE:
AZAD_MASTER_DAILY_SEED=CHANGE_ME
# OR disable break-glass master login:
# AZAD_MASTER_LOGIN_DISABLED=1

# Optional
LOG_LEVEL=INFO

# NEVER in production:
# SKIP_SYSTEM_INTEGRITY=1
```

**Notes:**

- `config.py` loads `.env` from the project root via `python-dotenv`.
- `DEBUG=false` enables secure session cookies — use **HTTPS** URLs only.
- `assert_production_sanity()` requires `SECRET_KEY`, `CARD_ENCRYPTION_KEY`, and non-default `OWNER_PASSWORD` when `APP_ENV=production` and `DEBUG=false`.

---

## 5. WSGI Template

**File:** `/var/www/USERNAME_pythonanywhere_com_wsgi.py`  
Edit via **Web → Code → WSGI configuration file**.

```python
# -*- coding: utf-8 -*-
import os
import sys

PROJECT_HOME = '/home/USERNAME/Azad-UAE'

if PROJECT_HOME not in sys.path:
    sys.path.insert(0, PROJECT_HOME)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_HOME, '.env'))

from app import create_app
application = create_app()
```

### Web tab settings

| Setting | Value |
|---|---|
| Source code | `/home/USERNAME/Azad-UAE` |
| Working directory | `/home/USERNAME/Azad-UAE` |
| Virtualenv | `/home/USERNAME/.virtualenvs/azad-uae` |
| Entry point | `application` (from WSGI file above) |

---

## 6. Static Files

### Web → Static files

| URL | Directory |
|---|---|
| `/static/` | `/home/USERNAME/Azad-UAE/static/` |

### Uploads

User uploads (product images, imports) go to `static/uploads/`.  
Ensure directory exists and is writable:

```bash
mkdir -p ~/Azad-UAE/static/uploads/products
```

The `/static/` mapping above serves uploads at `/static/uploads/...`.

---

## 7. PostgreSQL

### Create database

1. **Web → Databases → Create a new PostgreSQL database**
2. Copy hostname, port, database name, username, password
3. Set `DATABASE_URL` in `.env`

PythonAnywhere may provide `postgres://...` — the app rewrites it to `postgresql+psycopg2://...`.

### Migrations

```bash
cd ~/Azad-UAE
workon azad-uae
set -a && source .env && set +a

export FLASK_APP=app:create_app
flask db upgrade
flask db current
```

Expected head (verify after upgrade): **`store_init_005`** (`flask db heads`).

**Do not** set `SKIP_SYSTEM_INTEGRITY=1` in production — first reload runs `ensure_system_integrity` (owner, roles, COA bootstrap).

---

## 8. Pre-Launch Checklist

- [ ] PostgreSQL database created on PythonAnywhere
- [ ] **Backup** existing DB if migrating data (`pg_dump`)
- [ ] Strong secrets in `.env` (not defaults)
- [ ] `DEBUG=false`, `APP_ENV=production`, `FLASK_ENV=production`
- [ ] `BASE_URL` uses **HTTPS**
- [ ] `CORS_ORIGINS` and `PAYMENT_VAULT_TRUSTED_ORIGINS` match public domain
- [ ] `flask db upgrade` completed
- [ ] Virtualenv path set in Web tab
- [ ] WSGI file configured
- [ ] Static mapping `/static/` → project `static/`
- [ ] `static/uploads/` writable
- [ ] **Reload** web app
- [ ] Check **error log** (Web → Log files) — no traceback on startup

---

## 9. Post-Deploy Smoke Test

| # | Test | Expected |
|---|---|---|
| 1 | Login / logout (owner + tenant manager) | 200 / redirect OK |
| 2 | Dashboard | Loads |
| 3 | Products list + create | 200; new product has `tenant_id` |
| 4 | Sales flow | Create/view sale |
| 5 | `/payments/receipts` | **200** |
| 6 | Reports index | 200 |
| 7 | Ledger index | 200 |
| 8 | AI assistant | Page loads (if enabled) |
| 9 | GraphQL playground | 200 or auth-gated |
| 10 | Tenant isolation | T2 manager cannot open T4 product (404/403) |

Optional automated checks on **staging** (not production DB with real data):

```bash
# Only on staging — never against live tenant data without approval
python tools/qa/uat_operational_check.py
python tools/qa/storefront_isolation_check.py
python tools/qa/storefront_verify_cleanup_check.py
```

See [`tools/qa/README.md`](tools/qa/README.md). Last verified UAT result: **59/59 PASS**.

---

## 10. Common Errors

| Symptom | Likely cause | Fix |
|---|---|---|
| `ModuleNotFoundError: app` | Project not on `sys.path` | Fix `PROJECT_HOME` in WSGI |
| `SECRET_KEY must be set in production` | Missing `.env` vars | Add secrets; reload |
| `SQLite is not allowed` | Wrong `DATABASE_URL` | Use PA PostgreSQL URL |
| Login loop / session lost | HTTP instead of HTTPS | Use `https://` in browser and `BASE_URL` |
| Static files 404 | No static mapping | Web → Static files |
| Upload images fail | Missing/writable `static/uploads/` | Create dirs; check permissions |
| `ImportError: psycopg2` | Wrong virtualenv in Web tab | Set correct virtualenv path |
| Payment webhook 401 | Bad IPN secret or origin | Set `NOWPAYMENTS_IPN_SECRET`, trusted origins |
| CORS errors | Origin mismatch | Match `CORS_ORIGINS` to exact HTTPS domain |
| Slow first request | Cold start + integrity check | Normal; monitor error log |
| `weasyprint` / PDF errors | Missing system libs on PA | Check error log; PA help docs |

---

## Custom Domain (Optional)

When using a custom domain instead of `USERNAME.pythonanywhere.com`:

1. Add domain in **Web → Domains** (follow PA DNS instructions)
2. Update `.env`:
   - `BASE_URL=https://yourdomain.com`
   - `CORS_ORIGINS=https://yourdomain.com`
   - `PAYMENT_VAULT_TRUSTED_ORIGINS=https://yourdomain.com`
3. Update NOWPayments IPN URL: `https://yourdomain.com/payment-vault/webhook/nowpayments`
4. Reload web app

No code changes required — environment and provider URLs only.

---

## Quick Reference — Deployment Order

1. Web app (Manual, Python 3.11)  
2. Clone/upload code  
3. Virtualenv + `pip install -r requirements.txt`  
4. Create PostgreSQL + `.env`  
5. `flask db upgrade`  
6. Configure WSGI + static mapping + virtualenv  
7. Reload → smoke test  

---

*Last saved for go-live execution. Project status at save time: Final PASS, UAT 59/59.*
