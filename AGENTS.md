# AZAD Engineering Guidelines

Internal development standards for the Azadexa codebase. All engineers contributing to this repository must follow these conventions.

> Full engineering standards are defined in [`docs/GRIMOIRE.md`](docs/GRIMOIRE.md).

---

## Change Scope Classification

Every change must be classified before implementation:

```text
tenant-scoped / branch-scoped / tenant-store-scoped / platform-owner-scoped / public
```

---

## Critical Rules

### Transaction Safety
- Every DB write MUST use `atomic_transaction` from `utils/db_safety.py`.
- Services use `db.session.flush()` only — NEVER `commit()` or `rollback()`.

### Tenant Isolation
- Every DB read/write MUST use `tenant_query()` or `apply_tenant_scope()` from `utils/tenanting`.
- Cross-tenant data exposure is a P0 security defect.

### Architecture Layers
- `routes/` — HTTP handlers only. No business logic. No direct DB queries.
- `services/` — Pure business logic. Zero imports from `routes/`.
- `models/` — ORM models + scoped helpers. No HTTP concepts.
- `utils/` — Pure utility functions. Stateless where possible.

### Input Validation
- Every `request.get_json()` MUST use `silent=True`.
- Guard `Decimal()` conversions with `str(data.get('field') or '0')`.

### Authentication
- `@login_required` for logged-in routes.
- `@permission_required('code')` for fine-grained access.
- `@owner_required` for owner panel routes.

---

## Code Style

- Python: follow existing patterns. No `# type: ignore`, `# noqa`, or commented-out code.
- CSS: use `/* purgecss start/end ignore */` for vendor/dynamic selectors.
- HTML: use explicit `{% if %}` blocks for enumerated attributes (`dir`, `lang`).
- JavaScript: prefer `const`/`let`, no `var`.

---

## Testing

- Tests in `tests/unit/routes/`, `tests/unit/services/`, `tests/unit/utils/`, `tests/unit/models/`.
- Mock at the route boundary, not inside services.
- Every new route needs a test file.

---

## Protected Systems — Do NOT Modify Casually

- Tenant filters and owner-only guards.
- Payment vault boundaries.
- Customer/supplier balance logic.
- GL debit/credit posting.
- Stock movement and warehouse cost logic.
- Public donation/package payment ownership.

---

## Git Workflow

- Commits follow conventional-commit style.
- Commit in logical, reviewable units and push to `origin/main`.

---

## Work State (2026-09-02)

### CI — GREEN (fully passing)
- Latest CI run: `33559818256` (commit `3a35c6b3`) — ✅ **success** (all 20 jobs)
  - Static quality (ruff/mypy/jinja/biome/cspell/yamllint/actionlint) ✅
  - repo-security (gitleaks+Trivy), security-scan (bandit), verify-boot ✅
  - routes PG15/16/17, services, models, utils, core, ai_knowledge ✅
  - integration PG15, e2e, e2e-tours (Python+Playwright), api-fuzz, lighthouse ✅
  - tenant-isolation-fuzzer, docker-infra-audit, coverage-report ✅
- Alembic Round-Trip: `33559818099` — ✅ **success** (upgrade→downgrade→upgrade full chain)
- Kept only the latest 2 runs per workflow (CI, Alembic Round-Trip)

### Accounting & Schema Audit — COMPLETE (F-01…F-14 + 19 financial defects D-C1…D-C19)
- **Migration chain (single head):** `squash_001 → … → 5542ed4cd59f`
  - `e4506d215617` F-01/F-02: Receipt.sale_id, Shipment.sale_id + purchase_return_id (SET NULL)
  - `17fca8d581b2` F-06: sale.sales_rep_name; sales_rep_id SET NULL; effective_rep defaults to seller
  - `d9ce53ecac53` F-07: package_purchases.tenant_id (downgrade no-ops when owned by 313a)
  - `cdefc18af945` + `1c2195e00e66` F-08: gl_accounts.is_contra (1190/3300/5201 prime), 2122→asset/1100, +2999 Suspense
  - `5542ed4cd59f` D-L1-01: money precision 15,2→15,3 (card_payments/donations/payment_vault/wallets)
  - `dd28ea3aa6cc` D-C3: gl_journal_lines.explicit_account_allowed (honored by validate_entry)
- **GL integrity fixes:** fixed_asset disposal→gl_post_or_fail (D-C3), payroll advances 1160→1170 (D-C4), expense delete→archive (D-C7), transfer_stock moves PWC valuation (D-C8), FX revaluation per-voucher with branch_id (D-C13), tolerance/quantize unified 0.001 (D-C12/D-C18), dynamic GL mapping fail-fast (D-C14), bounce-fee idempotency (D-C16)
- **COA deliberately kept postable:** 1130/1140/2110/2120/4100/5100/5150 remain is_header=false (engine posts directly via concepts)

### Tenant Isolation & RBAC
- `request.get_json(silent=True)` — 100% compliant (0 bare calls)
- `@owner_only`/`@company_admin_required` on ownership surfaces; public routes (login/health/docs/language) intended-public + rate-limited
- `SELECT FOR UPDATE` locks: document_sequence, POS cart/checkout, stock batch/stock (savepoint retry)
- IdempotencyKeys: payment_vault, POS, stock-sync, azad_platform_fee

### Frontend (Layer 3)
- `static/js/ai-sales.js`: inline `onclick` replaced with addEventListener (nonce-CSP-safe, no `${}` XSS)
- JS reachability 100% via `templates/tests/js_reachability_boost.html` + `tests/unit/test_js_reachability.py`
- 0 `var` usage; global `unhandledrejection` handlers in base-helpers.js/app.js

### First-Run Scripts (clean, idempotent, PG+SQLite via batch_alter_table)
- `scripts/ops/first_run_dev.py` — drops+recreates DBs, `flask db upgrade`, system_init (37 perms/8 roles/owner/3 currencies/76 industry fields/GL base), `seed-packages`, optional `--with-demo`
- `scripts/ops/first_run_prod.py` — requires SECRET_KEY/DATABASE_URL/OWNER_PASSWORD, keeps data, no demo
- Both set CACHE_TYPE=null + RATELIMIT_STORAGE_URI=memory:// (no local Redis needed), cp1252-safe output
- Playwright auth state files now in `.gitignore` (generated by setup_test_users.py)

### Files Modified (this session, main@3a35c6b3)
- `models/{gl,receipt,shipment,sale,payment,cheque,warehouse,fixed_asset}.py`
- `models/gl_account_registry.py` (is_contra, 2122→asset, +2999)
- `services/{gl_tree_builder,gl_service,gl_posting,advanced_journal_manager,gl_account_resolver,stock_service,sale_service,payment_service,shipment_service,payroll_service,cheque_service,fx_revaluation_service,bank_reconciliation_service,print_service}.py`
- `routes/{public,printing,expenses}.py`
- `migrations/versions/` 8 new revisions (see chain above)
- `tests/unit/{routes,services,models,utils,forms,app}/` — coverage boosts + audit-adopted tests
- `scripts/ops/first_run_{dev,prod}.py`, `.gitignore`, `.bandit.yml`
