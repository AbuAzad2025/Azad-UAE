# AGENTS.md — Rules for AI Coding Assistants

## Before You Start

1. Read [`docs/GRIMOIRE.md`](docs/GRIMOIRE.md) — the non-negotiable rules for this codebase.
2. Identify the scope of your change: `tenant-scoped` / `branch-scoped` / `tenant-store-scoped` / `platform-owner-scoped` / `public`.

## Critical Rules (Summary)

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

## Code Style
- Python: follow existing patterns. No `# type: ignore`, `# noqa`, or commented-out code.
- CSS: use `/* purgecss start/end ignore */` for vendor/dynamic selectors.
- HTML: use explicit `{% if %}` blocks for enumerated attributes (`dir`, `lang`).
- JavaScript: prefer `const`/`let`, no `var`.

## Testing
- Tests in `tests/unit/routes/`, `tests/unit/services/`, `tests/unit/utils/`, `tests/unit/models/`.
- Mock at the route boundary, not inside services.
- Every new route needs a test file.

## What NOT to Change
- Tenant filters and owner-only guards.
- Payment vault boundaries.
- Customer/supplier balance logic.
- GL debit/credit posting.
- Stock movement and warehouse cost logic.
- Public donation/package payment ownership.
