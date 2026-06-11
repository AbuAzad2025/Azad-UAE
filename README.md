# Azadexa

**Azadexa** / **أزاديكسا** is an intelligent **multi-tenant ERP and commerce platform** by **AZAD Intelligent Systems**.

It is designed to manage real business operations across tenants, branches, stores, warehouses, accounting, sales, purchases, customers, suppliers, payments, and platform-owner workflows.

> **Proprietary software.** This repository is public for project tracking and deployment continuity, but it does not grant any public license to copy, reuse, modify, redistribute, or commercialize the code. See [`LICENSE`](LICENSE).

---

## Quick Start

| Purpose | Command / Reference |
|--------|----------------------|
| Local setup | `cp env.example .env` → `python -m venv .venv` → activate venv → `pip install -r requirements.txt` |
| Database migrations | `python -m flask db upgrade` |
| Local smoke run | `python app.py` |
| Unit tests | `pytest tests/unit -v --tb=short` |
| Full deployment guide | [`DEPLOYMENT_PYTHONANYWHERE.md`](DEPLOYMENT_PYTHONANYWHERE.md) |
| Documentation index | [`docs/README.md`](docs/README.md) |
| Brand identity | [`docs/AZADEXA_BRAND.md`](docs/AZADEXA_BRAND.md) |
| AI/developer rules | [`AGENTS.md`](AGENTS.md) |

Production must run through WSGI on PythonAnywhere or an equivalent WSGI host. Do **not** run `python app.py` as a production process.

---

## العربية

**أزاديكسا** منصة ERP وتجـارة ذكية متعددة المستأجرين لإدارة العمليات التجارية الحقيقية، وتشمل:

- المبيعات والمشتريات والمخزون.
- المحاسبة، دفتر الأستاذ، القيود اليومية، والتقارير المالية.
- العملاء، الموردين، الصناديق، المدفوعات، والشيكات.
- المستودعات، الفروع، المستخدمين، والصلاحيات.
- المتاجر الخاصة بكل مستأجر عند تفعيلها.
- لوحة مالك المنصة لإدارة المنصة، الاشتراكات، الدفعات العامة، والإعدادات العليا.
- صفحات عامة للاندنج، التبرعات، وشراء الحزم، منفصلة عن بيانات المستأجرين.

الهدف من المشروع هو توفير منصة تشغيل أعمال قابلة للنشر، قابلة للتوسع، ومعزولة بين المستأجرين، وليست مجرد متجر إلكتروني منفرد.

---

## English

Azadexa is a business operating platform that combines ERP, commerce, accounting, inventory, payments, and tenant-specific store workflows in one multi-tenant SaaS system.

The project is built for controlled deployment, tenant isolation, and progressive hardening toward production use.

---

## Product Positioning

**Azadexa — Intelligent ERP & Commerce Platform**

Extended positioning:

**Azadexa — Multi-Tenant ERP Cloud for Commerce, Accounting & Operations**

System type:

```text
Multi-Tenant ERP SaaS / Commerce Platform
```

Company:

```text
AZAD Intelligent Systems
```

---

## Core Capabilities

| Area | Capabilities |
|------|--------------|
| Multi-tenancy | Tenant-aware data isolation, tenant-scoped business workflows, tenant-specific stores |
| Sales | invoices, sales lines, payments, customer balances, returns where enabled |
| Purchases | supplier workflows, purchase records, payable tracking, inventory effects |
| Inventory | products, categories, stock movements, warehouse-level control |
| Accounting | GL posting, ledger workflows, core accounts, reports, balances |
| Warehouses | warehouse records, stock updates, movement tracking |
| Customers & suppliers | profiles, balances, statements, related transactions |
| Payments | payment flows, platform payment vault, tenant/store payment separation |
| Branches & users | branch-aware access, roles, permissions, operational controls |
| Platform owner | owner-only operations, package purchases, public payments, platform-level settings |
| UI | RTL Arabic-first interface with modern ERP dashboard patterns |

---

## Repository Structure

| Path | Purpose |
|------|---------|
| `app.py` | Flask application factory and startup wiring |
| `routes/` | Web routes and API endpoints |
| `models/` | SQLAlchemy models |
| `services/` | Business logic and domain services |
| `templates/` | Jinja2 HTML templates |
| `static/` | CSS, JavaScript, images, and frontend assets |
| `migrations/` | Alembic database migrations |
| `utils/` | shared helpers, decorators, tenant helpers, security helpers |
| `runtime_core/` | startup/runtime integrity repairs |
| `tools/` | development, QA, audit, and maintenance utilities |
| `docs/` | product, architecture, security, operations, and brand documentation |
| `AGENTS.md` | mandatory instructions for AI coding assistants and internal automation |

---

## Required Runtime

| Item | Recommendation |
|------|---------------|
| Python | Python 3.11 for production deployment compatibility |
| Database | PostgreSQL for production |
| Web server | WSGI host, such as PythonAnywhere Web app configuration |
| Config | `.env` based on `env.example` / production example files |
| Secrets | environment variables only; never commit real secrets |

---

## Environment Variables

Use placeholders only in committed files. Production secrets must live only on the server.

```bash
SECRET_KEY=CHANGE_ME
CARD_ENCRYPTION_KEY=CHANGE_ME
OWNER_PASSWORD=CHANGE_ME
DATABASE_URL=postgresql+psycopg2://USER:PASS@HOST:5432/DBNAME
DEBUG=false
APP_ENV=production
FLASK_ENV=production
BASE_URL=https://YOUR-DOMAIN
PREFERRED_URL_SCHEME=https
AZAD_MASTER_DAILY_SEED=CHANGE_ME
# AZAD_MASTER_LOGIN_DISABLED=1
NOWPAYMENTS_IPN_SECRET=CHANGE_ME
```

Important production rules:

- `DEBUG=false` requires HTTPS because secure cookies should be enabled.
- Never use `SKIP_SYSTEM_INTEGRITY=1` in production.
- Keep `.env`, database dumps, backups, upload folders, and private keys outside Git.
- Register one canonical payment webhook URL per payment provider/environment.

---

## Tenant and Payment Policy

Azadexa is multi-tenant by design.

- Each tenant has its own operational data, users, branches, warehouse data, sales, purchases, inventory, accounting, and store scope.
- Tenant storefronts must remain tenant-scoped.
- Public pages such as landing pages, donations, and package purchases belong to platform-owner flows.
- Public payments and package purchases are platform revenue and must not be mixed into tenant accounting unless an explicit business process requires that.
- Platform-owner vault operations must remain owner-only.

See [`docs/SECURITY_AND_TENANCY.md`](docs/SECURITY_AND_TENANCY.md) and [`docs/ACCOUNTING_AND_INVENTORY_RULES.md`](docs/ACCOUNTING_AND_INVENTORY_RULES.md).

---

## Documentation

| Document | Purpose |
|----------|---------|
| [`docs/README.md`](docs/README.md) | Documentation index |
| [`docs/AZADEXA_BRAND.md`](docs/AZADEXA_BRAND.md) | Product name, positioning, and brand rules |
| [`docs/PROJECT_OVERVIEW.md`](docs/PROJECT_OVERVIEW.md) | Business and technical overview |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System architecture and module boundaries |
| [`docs/SECURITY_AND_TENANCY.md`](docs/SECURITY_AND_TENANCY.md) | Security, tenant isolation, owner-only flows |
| [`docs/ACCOUNTING_AND_INVENTORY_RULES.md`](docs/ACCOUNTING_AND_INVENTORY_RULES.md) | Accounting, ledger, stock, returns, and balance rules |
| [`docs/OPERATIONS_RUNBOOK.md`](docs/OPERATIONS_RUNBOOK.md) | Local, staging, production, backups, and incident runbook |
| [`AGENTS.md`](AGENTS.md) | Rules for AI coding assistants and internal automation |
| [`DEPLOYMENT_PYTHONANYWHERE.md`](DEPLOYMENT_PYTHONANYWHERE.md) | PythonAnywhere deployment guide |

---

## Development Workflow

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate    # Linux/macOS
pip install -r requirements.txt
python -m flask db upgrade
python app.py
```

Before committing changes:

```bash
python -m py_compile app.py
pytest tests/unit -v --tb=short
```

Run broader QA tools only against development or staging databases unless a tool is explicitly read-only and production-safe.

---

## Deployment Summary

Production deployment should follow this path:

1. Prepare production server and Python 3.11 virtual environment.
2. Clone the repository.
3. Install requirements.
4. Configure PostgreSQL.
5. Create server-side `.env` with secure permissions.
6. Run migrations with `python -m flask db upgrade`.
7. Configure WSGI to import `create_app()` from `app.py`.
8. Map static files.
9. Reload the web app.
10. Verify login, tenant isolation, store behavior, accounting flows, payments, and backups.

See [`docs/OPERATIONS_RUNBOOK.md`](docs/OPERATIONS_RUNBOOK.md) and [`DEPLOYMENT_PYTHONANYWHERE.md`](DEPLOYMENT_PYTHONANYWHERE.md).

---

## Security Principles

- No real secrets in Git.
- Tenant isolation is a core architecture requirement, not a UI preference.
- Owner-only routes must remain protected with owner-level checks.
- Payment vault and card-related workflows must be treated as sensitive platform-owner functionality.
- Public payment callbacks and webhooks must be validated and logged safely.
- Debug mode and bypass flags are forbidden in production.
- All production changes should be tested first on staging or a disposable clone of production data with sensitive data removed.

---

## Repository Topics

Recommended GitHub topics:

```text
azadexa
erp
multi-tenant
saas
commerce-platform
inventory-management
accounting
flask
python
business-platform
```

---

## Ownership

**Product:** Azadexa / أزاديكسا  
**Company:** AZAD Intelligent Systems  
**License model:** Proprietary / All Rights Reserved  
**Repository:** `AbuAzad2025/Azad-UAE`

© 2026 AZAD Intelligent Systems — All Rights Reserved.
