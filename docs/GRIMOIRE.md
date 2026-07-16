# GRIMOIRE — Azadexa ERP Non-Negotiable Rules

## 1. ATOMICITY (Transaction Safety) — MANDATORY

- **Every database write MUST use `atomic_transaction`** (centralized at `utils/db_safety.py`). No exceptions for business modules.
- The single `commit()` lives in `utils/db_safety.py:26` (`atomic_transaction` context manager).
- The single `rollback()` lives in `utils/db_safety.py:29` (inside `atomic_transaction.__exit__` on exception). The ONLY other accepted `rollback()` is the intentional `gl_accounting_setup.py` `dry_run` branch.
- Services use `db.session.flush()` only — **never** `commit()` or `rollback()`.
- `db.session.add()` / `db.session.delete()` / `db.session.query()` are permitted inside an `atomic_transaction` boundary; the transaction is committed/rolled back exclusively by `atomic_transaction`.
- Never call `db.session.commit()` or `db.session.rollback()` anywhere else. Ever.

## 2. TENANT ISOLATION — MANDATORY

- **Every database read AND write MUST use `tenant_query()` or `apply_tenant_scope()`** from `utils/tenanting`. No exceptions for business modules.
- Use `tenant_get_or_404(Model, id)` for single-record lookups (auto-aborts 404 on cross-tenant access).
- Use `tenant_query(Model)` for multi-record queries.
- For raw queries or non-ORM writes, resolve the tenant with `get_active_tenant_id()` and append `tenant_id=<tid>`.
- Cross-tenant exposure (e.g. reading another tenant's `CardPayment`, `Customer`, `AuditLog`, or analytics) is a P0 security defect — fix immediately.
- The ORM auto-scoping covers SELECTs for blueprints NOT in `_SKIP_BLUEPRINTS`. For those (like `shop`), you must filter manually via the helpers above.
- Background/Celery jobs that iterate tenants MUST scope per tenant (set `g.active_tenant_id` per tenant) — never process all tenants' data in one unscoped query.

## 3. RESTORE SAFETY (dry-run) — MANDATORY

- **All restore operations MUST support `dry_run=True`** to simulate and validate row impact before any commit.
- The restore engine (`services/backup_scoped_engine.py` + `services/backup_scoped_restore.py`) executes the full restore inside a transaction and **rolls back** when `dry_run=True`, returning an affected-row summary instead of committing.
- Restore must be **schema-drift tolerant**: `normalize_row_to_target()` drops columns absent from the target table and fills missing NOT NULL columns (no DB default) with typed defaults — so stale backups restore cleanly.
- Always run a `dry_run` restore and confirm `ok=True` + `dry_run=True` with zero rows persisted before any real restore.
- If the default demo tenant backup drifts, run `python scripts/fix_default_tenant.py` to patch its NOT NULL metadata and regenerate a drift-free backup.

## 4. AUTHENTICATION & AUTHORIZATION

- Use `@login_required` for any route that needs a logged-in user.
- Use `@permission_required('permission_code')` for fine-grained access.
- Use `@role_required('owner', 'admin')` for role-gated routes.
- Owner panel routes use `@owner_required`.
- Never expose tenant-scoped data to unauthenticated requests.

## 5. INPUT VALIDATION

- **Every** `request.get_json()` call **must** use `silent=True`.
- Pattern: `data = request.get_json(silent=True)` then check `if data is None:`.
- Validate with schema functions (e.g., `validate_positive_amount`, `validate_required_string`).
- Guard `Decimal()` conversions with `str(data.get('field') or '0')` — never pass `None` to Decimal.

## 6. ERROR HANDLING

- No `except: pass` — always log errors explicitly.
- Use `current_app.logger.error(...)` or the `LoggingCore` for structured logging.
- In atomic_transaction blocks, exceptions are automatically caught and rolled back — do NOT add redundant try/except.
- Return `jsonify({'error': 'message'}, 400/500)` for API errors; flash + redirect for HTML endpoints.

## 7. TESTING DISCIPLINE

- Tests go in the correct subdirectory: `tests/unit/routes/`, `tests/unit/services/`, `tests/unit/utils/`, `tests/unit/models/`, `tests/unit/app/`.
- Cross-layer or integration tests stay flat in `tests/unit/`.
- Every new route module needs a corresponding test file.
- Mock at the route boundary, not inside services.

## 8. ARCHITECTURE LAYERS

- `routes/` — HTTP handlers only. NO business logic. NO direct DB queries (delegate to services).
- `services/` — Pure business logic. ZERO imports from `routes/`.
- `models/` — ORM models + scoped helpers. NO HTTP concepts.
- `utils/` — Pure utility functions. Stateless where possible.

## 9. FILE STRUCTURE

- Root directory: only `app.py`, `config.py`, `extensions.py`, `cli_commands.py`, `README.md`, `GRIMOIRE.md`, standard config files (`.env`, `.flake8`, `pytest.ini`, etc.).
- No dead monolithic files in `routes/` — split into subpackages (`routes/owner/`, `routes/ai_routes/`).
- `services/` can have subdirectories for large domains (e.g., `services/gl/`, `services/store/`).

---
*Last updated: 2026-07-09 (tenant-safe + dry-run + restore-safety pass). These rules are non-negotiable. Violations must be fixed immediately.*
