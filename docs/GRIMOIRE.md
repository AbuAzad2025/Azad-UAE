# GRIMOIRE — Azadexa Engineering Standards

## 1. Transaction Safety

1.1 `db.session.commit()` MUST exist only in `utils/db_safety.py`.

1.2 `db.session.rollback()` MUST exist only in `utils/db_safety.py` and in `services/gl_accounting_setup.py` for dry-run branches.

1.3 `services/` MUST use `db.session.flush()` exclusively. `commit()` and `rollback()` are forbidden in this layer.

1.4 Every write touching more than one model MUST be wrapped in `with atomic_transaction("description"):`.

1.5 `db.session.add()` and `db.session.delete()` MUST occur only inside an `atomic_transaction` boundary.

## 2. Tenant Isolation

2.1 All database reads and writes MUST use `tenant_query()`, `apply_tenant_scope()`, or `tenant_get_or_404()`.

2.2 Single-record lookups MUST use `tenant_get_or_404(Model, id)`. This aborts with 404 on cross-tenant access.

2.3 Multi-record queries MUST use `tenant_query(Model)`.

2.4 Raw SQL MUST append `tenant_id=<tid>` after resolving the active tenant via `get_active_tenant_id()`.

2.5 Cross-tenant data exposure is a P0 security defect and MUST be fixed immediately.

2.6 Celery tasks and background jobs MUST scope per iteration. Unscoped batch queries are forbidden.

## 3. Input Validation

3.1 Every `request.get_json()` call MUST pass `silent=True`.

3.2 After `data = request.get_json(silent=True)`, the handler MUST check `if data is None:` and return 400.

3.3 `Decimal()` conversions MUST guard against `None` using `Decimal(str(data.get('field') or '0'))`.

3.4 Domain validation MUST use dedicated helpers such as `validate_positive_amount` and `validate_required_string`.

## 4. Architecture Boundaries

4.1 `routes/` — HTTP handlers only. No business logic. No direct `db.session` queries. No model creation logic.

4.2 `services/` — Pure business logic only. No imports from `routes/`. No HTTP concepts (`request`, `jsonify`, `flash`).

4.3 `models/` — ORM definitions and scoped query helpers only. No HTTP concepts. No business logic. No service imports.

4.4 `utils/` — Pure stateless functions and context managers only. No imports from `routes/` or `services/` except `db_safety` and `tenanting`.

4.5 `forms/` — WTForms definitions and validation rules only. No business logic. No database queries.

## 5. Authentication & Authorization

5.1 Every route requiring a logged-in user MUST carry `@login_required`.

5.2 Fine-grained access control MUST use `@permission_required('code')`.

5.3 Owner-panel routes MUST carry `@owner_required`.

5.4 Tenant-scoped data MUST NOT be exposed to unauthenticated or unauthorized requests.

## 6. Error Handling

6.1 Bare `except:` clauses are forbidden. Every exception handler MUST log via `logger.error(...)` or `current_app.logger.error(...)`.

6.2 Do not wrap `atomic_transaction` in an outer `try/except` that performs rollback. `atomic_transaction` handles rollback automatically.

6.3 API error responses MUST return `jsonify({'error': 'message'}), <status>`.

6.4 HTML error responses MUST use `flash(...)` followed by `redirect(...)`.

## 7. Code Quality

7.1 `# type: ignore`, `# noqa`, and commented-out code are forbidden.

7.2 Duplicated helpers are forbidden. One function, one purpose, one location. If a similar helper already exists, refactor and extend it. Do not reinvent from scratch.

7.3 Functions exceeding 80 lines MUST be refactored by extracting helpers.

7.4 Python 3.12 idioms SHOULD be used: `str | None` instead of `Optional[str]`, `match/case` where appropriate, and `from __future__ import annotations`.

## 8. Testing

8.1 Unit tests MUST reside in `tests/unit/routes/`, `tests/unit/services/`, `tests/unit/utils/`, and `tests/unit/models/`.

8.2 Mocking MUST occur at the route boundary. Mocking inside services is forbidden.

8.3 Every route module MUST have a corresponding test file.

8.4 Integration tests MUST stay flat in `tests/integration/`.

## 9. File Organization

9.1 The repository root MUST contain only entrypoints, configuration files, and top-level documentation.

9.2 Scripts MUST live in `scripts/ops/`, `scripts/lint/`, or `scripts/backup/`. No orphaned scripts in the root.

9.3 Large modules MUST split into subpackages (e.g. `routes/owner/`, `routes/ai_routes/`).

9.4 Large service domains MAY use subdirectories (e.g. `services/gl/`, `services/store/`).

## 10. Testing Integrity & Enforcement

10.1 `scripts/ops/enforce_grimoire.py` enforces these rules via AST static analysis. Regex-based checks are forbidden.

10.2 Database test fixtures MUST use `session.begin_nested()` (savepoints) or explicit rollback teardown. Tests MUST NOT leak committed state to other tests.

10.3 Test database URIs MUST resolve from `app.config['SQLALCHEMY_DATABASE_URI']`. Hardcoded database names in fixtures are forbidden.

10.4 Tests MUST verify inputs and outputs at layer boundaries (route to service). Mock at the route boundary, never inside services.

10.5 Flaky patterns are forbidden: `time.sleep()`, unseeded `random`, order-dependent logic, and shared mutable state across tests.

10.6 `tests/unit/test_grimoire_compliance.py` runs the AST checker in CI. Zero errors are required. Warnings are tracked and must trend downward.
