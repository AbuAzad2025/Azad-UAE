# AZAD ERP — Comprehensive Architectural Blueprint

**Version:** 2026-11-13 (commit 14ab84db)
**Auditor posture:** Principal Enterprise ERP Architect · Senior Systems Analyst · Technical Auditor
**Scope:** Full codebase — 110 models, 156 services, 55 route modules, 92 utilities, 78 migrations, 400 templates.
**Verification:** CI green, ruff 0 errors, mypy clean, 98.49% coverage.

---

## 1. System Architecture & Tech Stack Foundation

### 1.1 Core Frameworks
- **Web framework:** Flask 3.1.3 (application factory in `app/factory.py`).
- **ORM:** SQLAlchemy 2.0.52 + Flask-SQLAlchemy 3.x. 170+ tenant-scoped models.
- **Migrations:** Alembic (Flask-Migrate). Single head `c2d3e4f5a6b7` (78 revisions). Every revision has `downgrade()`.
- **Templating:** Jinja2 (400 templates under `templates/`). Strict i18n lint enforced.
- **Frontend:** Custom modular CSS (29 stylesheets, utility classes), vanilla JS (57 source files), Biome 2.5.4 (lint+format), Chart.js, Tailwind (build-time only).
- **Async:** Celery (background tasks) + Redis (broker).
- **Database:** PostgreSQL 15/16/17 (production), SQLite (tests). Session isolation level `REPEATABLE READ`.
- **Auth:** Flask-Login, Flask-WTF (CSRF), bcrypt password hashing, TOTP 2FA, master-login break-glass.
- **i18n:** Flask-Babel (Arabic/English), 7329 keys in `utils/i18n.py` + `utils/shop_i18n.py`.
- **PDF/Print:** WeasyPrint.
- **Telemetry:** JSONL sink + in-memory metrics.

### 1.2 Multi-Tenant Isolation

**Three layers of defence:**

1. **ORM-level guard (`utils/tenant_orm.py`):**
   - `do_orm_execute` + `with_loader_criteria`: injects `WHERE tenant_id = <active>` on every ORM SELECT inside a scoped blueprint.
   - `Session.get` patched to return `None` for cross-tenant rows.
   - `before_flush` write guard raises `TenantIsolationError` on cross-tenant INSERT/UPDATE/DELETE.
   - `tenant_scope_enabled()` returns `False` without a request context (Celery/CLI) — background tasks MUST scope explicitly via `with tenant_scope(tenant_id)`.

2. **Bounded tenant context:** `utils/tenanting.py` exposes `tenant_query()`, `apply_tenant_scope()`, `without_tenant_scope()` (escape hatch for platform-only writes, e.g. system_init).

3. **Raw SQL / bulk DML audit:** Every `db.session.execute(text(...))` and bulk `update()/delete()` carries an explicit tenant predicate. `check_txn_boundaries.py` lint gate enforces this.

**Tenant scoping on exports/backups:** Owner-only platform backup (`/owner/backup`); tenant-level data export is scoped to the active tenant; no cross-tenant restore path exists.

### 1.3 Transaction Boundaries

- **Service layer purity:** Services use `db.session.flush()` only — NEVER `commit()` or `rollback()`. Enforced by `check_txn_boundaries.py`.
- **Route orchestration:** `atomic_transaction()` context manager (or `@atomic` decorator) in `utils/db_safety.py` wraps the entire request handler in a single DB transaction; commits on success, rolls back on exception.
- **SELECT FOR UPDATE:** Used on `document_sequence`, POS cart/checkout, stock batch/stock (with savepoint retry) to prevent races.
- **Idempotency:** `IdempotencyKey` table guards payment_vault, POS, stock-sync, azad_platform_fee against duplicate execution.

### 1.4 Configuration & Secrets
- Secrets via environment variables only (`SECRET_KEY`, `DATABASE_URL`, `OWNER_PASSWORD`, `REDIS_URL`). No hardcoded credentials.
- `config.assert_production_sanity` enforces 16+ char mixed-case owner password in production.
- `first_run_dev.py` / `first_run_prod.py` are idempotent, PG+SQLite compatible.
- Feature flags on `Tenant` (8 module flags: shipments, campaigns, partners, fixed_assets, donations, warranty_tracking, bank_reconciliation, azad_platform) — all `NOT NULL DEFAULT true`.

---

## 2. Financial & Accounting Core (General Ledger)

### 2.1 Precision Arithmetic
- **Zero float in postings:** All money uses `Decimal` with `ROUND_HALF_UP` quantization to 3 decimal places (15,3).
- **`utils/numeric_input.py`:** strict numeric parsing helper; guards `Decimal()` conversions with `str(data.get('field') or '0')`.
- **`utils/decimal_utils.py`:** shared quantization helpers.

### 2.2 Multi-Currency Engine
- **Tenant base currency:** stored on `Tenant.base_currency` (e.g. ILS, AED, USD). All GL postings are in base currency.
- **Historical exchange rates:** every document carries `exchange_rate` (Numeric 15,6) captured at transaction date.
- **Line-level base amounts:** `SaleLine.amount_aed`, `PurchaseLine.amount_aed`, `QuotationLine.amount_aed` (added migration `c2d3e4f5a6b7`) store `line_total * exchange_rate` for direct query-time aggregation.
- **Document-level base amounts:** `Sale.amount_aed`, `Purchase.amount_aed`, `Quotation.amount_aed` store the document total in base currency.
- **`gl_posting.py::post_or_fail`:** normalizes every journal line to base currency before persistence; rejects unbalanced entries.
- **Analytics/report sums:** all `func.sum(...)` over document-currency columns now use `amount_aed` (base currency) — fixed in this audit cycle.

### 2.3 Ledger Integrity
- **Double-entry:** every posting creates balanced Dr/Cr journal lines; `validate_entry` rejects imbalanced entries.
- **Chart of Accounts:** 118 base GL accounts + 49 industry-extension accounts across 13 industries (`utils/gl_account_registry.py`).
- **GL concepts:** `GL_CONCEPT_CODES` allow-list (rebuilt from model's own list via migration `c3d9e1f7a204`); dynamic GL mapping fail-fast under `ENABLE_DYNAMIC_GL_MAPPING=True`.
- **Trial balance, AR/AP control reconciliation:** verified by `tests/integration/test_period_close_reconciliation.py` (300 invoices, 878 entries).
- **FX revaluation:** `services/fx_revaluation_service.py` + route `POST /ledger/fx-revaluation` (idempotent per YYYY-MM).
- **Fiscal year close:** posts closing entry on first day of new fiscal year; all 12 periods of ending year closed first.
- **Statutory payroll:** `utils/country_tax.py` carries 2025 rates (NSSF PS, Bituach Leumi IL, GOSI SA, GPSSA AE, IL progressive income tax). Withholdings persisted on `payroll_transactions`.
- **E-invoice:** UBL 2.1 statutory document (`utils/einvoice_document.py`) for PS/IL/AE/SA; KSA gets ZATCA TLV QR. Created inside the same transaction as the sale.
- **Import levies:** customs duty + excise (tobacco/energy/soft drinks) posted to `EXCISE_DUTY` concept (account 5304).

### 2.4 Treasury & Cash
- **Payment vault:** encrypted card storage with idempotency keys.
- **Cheque lifecycle:** issuance, clearing, bounce (with idempotent bounce-fee posting).
- **Bank reconciliation:** `services/bank_reconciliation_service.py`.
- **Cash boxes / POS drawers:** shift-based cash movements, drawer reconciliation.

---

## 3. Operational & Functional Modules

### 3.1 Sales & Quotations
- **Quotation lifecycle:** draft → sent → accepted/rejected → converted to Sale. Line-level base currency tracking.
- **Sale lifecycle:** draft → confirmed → fulfilled → (return). Stock deduction + GL posting on confirm.
- **Fulfillment:** `services/fulfillment_service.py` handles picking/packing/shipping.
- **Returns:** `services/return_service.py` reverses revenue, tax, and COGS.
- **Serial tracking:** `SerialTrackingService` marks serials issued/restored.

### 3.2 Purchases & Inbound Shipments
- **Purchase order:** create → approve → receive (goods receipt) → invoice.
- **Supplier management:** `models/supplier.py`, credit terms, balance tracking.
- **Receiving:** `services/shipment_service.py` + `services/goods_receipt_service.py`; stock added at supplier cost, moving average rebuilt.
- **Import purchases:** `is_import=True` applies statutory customs default + excise computation.

### 3.3 Inventory & Stock Management
- **Stock movement:** `StockService.create_movement` with locked `ProductWarehouseStock`, negative-stock guard, `current_stock` sync.
- **Warehouse cost:** `ProductWarehouseCost` moving average; `ProductCostHistory` audit trail.
- **FEFO batch consumption:** when tenant has batches enabled.
- **Concurrency:** `SELECT FOR UPDATE` row locking on stock/batch.
- **Transfer stock:** moves valuation between warehouses.

### 3.4 HR & Payroll
- **Employee records:** `models/hr.py`, `models/employee_bank_wps.py`.
- **Salary structures:** basic + allowances + deductions.
- **Statutory payroll:** `utils/country_tax.py` computes NSSF/Bituach Leumi/GOSI/GPSSA + IL income tax. Employer share is extra expense. GL posts balanced (6220/6221 Dr, 2143/2144/2147 Cr, 2141 for manual deductions).
- **Advances:** 1170 account (corrected from 1160).
- **Payslip:** shows statutory breakdown.

### 3.5 Maintenance & Assets
- **Own sub-ledger:** MAINTENANCE_AR 1134, MAINTENANCE_REVENUE 4119, MAINTENANCE_COGS 5119, MAINTENANCE_DEPOSIT 2171, MAINTENANCE_CASH_DIFFERENCE 6560, MAINTENANCE_AP → 2110.
- **Maintenance orders:** receive → diagnose → work → close & collect (single transaction: parts consumption + invoice + receipt + 3 GL entries).
- **Device registry:** unique per tenant; warranty check (not cancelled = EXPIRED not VOID).
- **Warranty audit:** append-only (DB triggers refuse UPDATE/DELETE).
- **Maintenance purchase orders:** receive → stock at supplier cost → moving average rebuilt → GL posted (Dr INVENTORY_ASSET net / Cr MAINTENANCE_AP gross, tax on VAT_INPUT).
- **Serial tracking:** consistent across trade and maintenance ledgers.

### 3.6 POS & Cash Management
- **POS session:** open shift → sales → close shift → drawer reconciliation.
- **POS cart/checkout:** atomic with `SELECT FOR UPDATE`.
- **Payment vault:** encrypted card storage, idempotency keys.
- **Cash movements:** `pos_cash_movement.py` tracks in/out.
- **KDS (Kitchen Display System):** `pos_kds_order.py`.
- **Override tokens:** manager override for discounts/voids.

### 3.7 CRM, Projects, Marketing, Helpdesk, AI
- **CRM:** leads, opportunities, stages, activities.
- **Projects:** task tracking, time logging.
- **Marketing:** campaigns, email marketing, abandoned cart recovery.
- **Helpdesk:** ticket system.
- **AI:** sales assistant, training, knowledge base.

### 3.8 E-Commerce / Public Store
- **Public storefront:** catalog, product detail, cart, checkout with rate limits, CSRF, phone validation.
- **WhatsApp checkout:** provisional orders → tenant admin approval → real Sale + stock + GL.
- **Store analytics:** revenue by product/period (Chart.js).
- **Store reports:** sales by product/period.

### 3.9 Donations, Packages, Partners
- **Donations:** public donation flow with payment ownership.
- **Packages:** SaaS package management (owner panel).
- **Partners:** profit sharing, commissions, distributions.

### 3.10 Fixed Assets, Budgets, Advanced Accounting
- **Fixed assets:** depreciation, disposal (GL posted with bank account branch).
- **Budgets:** budget vs actual.
- **Advanced accounting:** FX revaluation, period close, fiscal year close, cost/profit centers.

---

## 4. Security, Input Validation & Configuration Hardening

### 4.1 Input Boundary Safety
- **500-to-400 hardening:** every `request.get_json()` uses `silent=True`; `ValueError`/`TypeError`/`InvalidOperation` caught and returned as 400 with structured error.
- **`utils/numeric_input.py`:** strict parsing, guards `Decimal()` conversions.
- **`utils/validators.py`:** email, phone, TRN validation.

### 4.2 Authentication & Authorization
- **`@login_required`** for logged-in routes.
- **`@permission_required('code')`** for fine-grained access.
- **`@owner_required`** for owner panel routes.
- **RBAC:** 54 permissions, 9 roles. Tenant Manager empowered with `manage_settings`/`manage_approvals`. Inventory & Viewer roles added. Strict SoD maintained.
- **2FA:** TOTP with recovery codes.
- **Master login:** break-glass with audit logging.

### 4.3 Audit & Compliance Logs
- **`services/logging_core.py`:** unified error tracking with `log_security_event`, `log_financial_event`, `log_database_event`, `log_migration_event`.
- **Append-only audit trails:** `journal_entry_audit`, `pos_fraud_log`, `security_alert`, `error_audit_log`.
- **Audit log retention:** configurable cleanup.

### 4.4 Tenant Isolation Enforcement
- See §1.2. Cross-tenant data exposure is P0 security defect.
- `check_utility_reachability.py`, `check_css_class_collisions.py`, `check_font_assets.py` — frontend gates.
- `check_strict_i18n.py`, `check_i18n_untranslated.py` — i18n gates.

---

## 5. Database Schema & Migrations

- **78 revisions**, single head `c2d3e4f5a6b7`.
- **Key migrations:** `5e2b8f4a6c13` (8 tenant module flags), `c3d9e1f7a204` (GL concept allow-list rebuilt), `d7e8f9a0b1c2` (fiscal-close concepts + INSURANCE_IN), `b1f4c7a92d60` (41 composite indexes, CONCURRENTLY), `c2d3e4f5a6b7` (line-level amount_aed).
- **Schema health:** `app/bootstrap.py` verifies manifest + storage paths + schema on boot.

---

## 6. Testing & CI Gates

- **Test layout:** `tests/unit/{routes,services,models,utils,forms,app}/`, `tests/integration/`, `tests/integration/business_scenarios/` (waves 7-16, all delivered).
- **Coverage floor:** global 95 (measured 98.49%); per-layer: routes 98, services 97, models 99, utils 96, app 90.
- **CI jobs:** 26 jobs (routes/services/utils/core/integration/models/scenarios-a/b/c/d/coverage-report). All green.
- **Lint gates:** ruff, mypy, 14 lint scripts, cspell, API docs comparison.
- **Lighthouse:** median of 3 runs per URL; floors 90/90/90/65.

---

## 7. Seed Data (Single Source of Truth)

- `utils/seed_manifest.py` indexes every seedable data set (scope, seeder, source, row-count probe).
- **Seeded:** 54 permissions, 9 roles, 3 currencies (ILS base, AED, USD), 74 industry field definitions, 118 base GL accounts + 49 industry-extension.
- **Deliberately NOT seeded:** SaaS packages (owner owns pricing), tenant business tables, accounting periods, exchange rates, units of measure, VAT rates (statutory rates are code master in `utils/country_tax.py`).
- Boot verifies manifest and logs `UNDER-SEEDED` for any below expected count.

---

## 8. File Inventory (Key Directories)

| Directory | Files | Purpose |
|---|---|---|
| `models/` | 110 | ORM models + scoped helpers |
| `services/` | 156 | Pure business logic |
| `routes/` | 55 | HTTP handlers |
| `utils/` | 92 | Pure utility functions |
| `templates/` | 400 | Jinja2 views |
| `static/` | 150+ | CSS/JS/assets |
| `migrations/versions/` | 78 | Alembic revisions |
| `tests/` | 200+ | Unit + integration + scenarios |

---

## 9. Known Open Items

- Israel mandatory pension fund: not implemented (no verified rate table).
- Zakat and stamp taxes: out of scope.
- Government e-invoice submission (ZATCA Phase-2, ITA, PMA/FTA): requires tenant credentials; not claimed.
- Fiscal-year period dating finding: closed (posts on first day of new fiscal year).

---

*End of blueprint.*