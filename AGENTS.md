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

## Work State (2026-08-30)

### Completed
- `.gitleaks.toml`: `exclude_paths = ["tests/**"]` (prevents false positives on REDACTED placeholders)
- `.github/workflows/ci.yml:367-369`: gitleaks `with: config: .gitleaks.toml`
- `utils/auth_helpers.py:27`: `is_admin_surface_user` checks both `role.slug` AND `role.name` for `SUPER_ADMIN`
- `services/print_service.py:371`: `get_document()` requires `tenant_id` (raises `ValueError` if None) — H-1
- `utils/tenant_orm.py:1`: `TENANT SCOPING CONTRACT` docstring documenting relationship inheritance and bypass scenarios — H-2
- `tests/integration/test_print_idor_protection.py`: 5 IDOR tests covering service-layer, route-layer, cross-tenant, unauthenticated — R-3
- Schema audit: 110+ models, ~200 FKs reviewed. 14 flaws identified (F-01 through F-14)
- Schema remediations applied:
  - F-03: `models/warehouse.py`: `_validate_tenant_consistency` validator
  - F-04: `models/cheque.py`: `_validate_exactly_one_source` validator
  - F-05: `models/payment.py`: `_validate_payment_direction` validator
  - F-01: `models/receipt.py`: module docstring documenting polymorphic source pattern
  - F-02: `models/shipment.py`: class docstring with `VALID_SOURCE_TYPES`
  - F-06: `models/sale.py`: module docstring documenting seller_id/sales_rep_id semantics
- `templates/receipts/payment_voucher.html`: restored original 253-line standalone template (extends `layouts/base_print.html`, not `receipts/_base.html`)

### Commits
- `1633c9f8`: fix(security): implement zero-trust audit hardening H-1, H-2, R-3
- `8cd67f48`: fix(schema): document polymorphic patterns and add model-level invariants
- `a9a97cfa`: fix(templates): restore payment_voucher.html to original standalone template

### Pre-existing CI Failures (not introduced by hardening)
- `test_payment_voucher_renders` (integration): Jinja2 double-content error — pre-existing, was always failing
- `test_print_settings_rejects_cashier` (integration): expects 403, gets 200 — pre-existing permission check issue
- `test_print_branch_forbidden` (routes, expense/purchase/sale): TypeError on snapshot.dist_url with MagicMock
- `test_print_success` (routes, expense/purchase/sale): UndefinedError: 'dist_url' is undefined
- `test_events_registry_deep.py`: caplog + logger handler config issue — pre-existing
- `coverage-report`: COVERAGE_FAIL_UNDER=85 not met

### Files Modified
- `D:\recovers\data\karaj\azad-uae\.gitleaks.toml`
- `D:\recovers\data\karaj\azad-uae\.github\workflows\ci.yml`
- `D:\recovers\data\karaj\azad-uae\utils\auth_helpers.py`
- `D:\recovers\data\karaj\azad-uae\services\print_service.py`
- `D:\recovers\data\karaj\azad-uae\utils\tenant_orm.py`
- `D:\recovers\data\karaj\azad-uae\tests\integration\test_print_idor_protection.py`
- `D:\recovers\data\karaj\azad-uae\models\warehouse.py`
- `D:\recovers\data\karaj\azad-uae\models\cheque.py`
- `D:\recovers\data\karaj\azad-uae\models\payment.py`
- `D:\recovers\data\karaj\azad-uae\models\receipt.py`
- `D:\recovers\data\karaj\azad-uae\models\sale.py`
- `D:\recovers\data\karaj\azad-uae\models\shipment.py`
- `D:\recovers\data\karaj\azad-uae\templates\receipts\payment_voucher.html`

### CI Run Status
- Latest run: `33314617791` (commit `a9a97cfa`) — in progress
  - Static quality: ✅ PASS
  - repo-security: ✅ PASS (gitleaks ✅)
  - verify-boot: ✅ PASS
  - core/services/models/utils/e2e: ✅ PASS
  - routes (PG 15/16/17): ⏳ in progress
  - integration: ⏳ in progress

### Schema Flaws (pending Alembic migration)
- F-01: `Receipt.source_id` — polymorphic FK without DB constraint
- F-02: `Shipment.source_id` — polymorphic FK without DB constraint
- F-07: Receipt/Payment asymmetric accounting model
- F-09: Product cannot be deleted (all FKs use RESTRICT)
- F-10: Sale cannot be deleted (all FKs use RESTRICT)
