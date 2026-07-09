# GRIMOIRE — Azadexa ERP Non-Negotiable Rules

## 1. ATOMICITY (Transaction Safety)

- **Every** DB write MUST be inside `with atomic_transaction(...)` at the route boundary.
- Services use `db.session.flush()` only — **never** `commit()` or `rollback()`.
- The single `commit()` lives in `utils/db_safety.py:26` (`atomic_transaction` context manager).
- The single `rollback()` lives in `utils/db_safety.py:29` (inside `atomic_transaction.__exit__` on exception).
- Never call `db.session.commit()` or `db.session.rollback()` anywhere else. Ever.

## 2. TENANT ISOLATION

- **Every** query in mutation endpoints **must** filter by `tenant_id`.
- Use `tenant_get_or_404(Model, id)` for single-record lookups.
- Use `tenant_query(Model)` for multi-record queries.
- For raw queries or non-ORM writes, use `get_active_tenant_id(current_user)` and append `tenant_id=<tid>`.
- The ORM auto-scoping covers SELECTs for blueprints NOT in `_SKIP_BLUEPRINTS`. For those (like `shop`), you must filter manually.

## 3. AUTHENTICATION & AUTHORIZATION

- Use `@login_required` for any route that needs a logged-in user.
- Use `@permission_required('permission_code')` for fine-grained access.
- Use `@role_required('owner', 'admin')` for role-gated routes.
- Owner panel routes use `@owner_required`.
- Never expose tenant-scoped data to unauthenticated requests.

## 4. INPUT VALIDATION

- **Every** `request.get_json()` call **must** use `silent=True`.
- Pattern: `data = request.get_json(silent=True)` then check `if data is None:`.
- Validate with schema functions (e.g., `validate_positive_amount`, `validate_required_string`).
- Guard `Decimal()` conversions with `str(data.get('field') or '0')` — never pass `None` to Decimal.

## 5. ERROR HANDLING

- No `except: pass` — always log errors explicitly.
- Use `current_app.logger.error(...)` or the `LoggingCore` for structured logging.
- In atomic_transaction blocks, exceptions are automatically caught and rolled back — do NOT add redundant try/except.
- Return `jsonify({'error': 'message'}, 400/500)` for API errors; flash + redirect for HTML endpoints.

## 6. TESTING DISCIPLINE

- Tests go in the correct subdirectory: `tests/unit/routes/`, `tests/unit/services/`, `tests/unit/utils/`, `tests/unit/models/`, `tests/unit/app/`.
- Cross-layer or integration tests stay flat in `tests/unit/`.
- Every new route module needs a corresponding test file.
- Mock at the route boundary, not inside services.

## 7. ARCHITECTURE LAYERS

- `routes/` — HTTP handlers only. NO business logic. NO direct DB queries (delegate to services).
- `services/` — Pure business logic. ZERO imports from `routes/`.
- `models/` — ORM models + scoped helpers. NO HTTP concepts.
- `utils/` — Pure utility functions. Stateless where possible.

## 8. FILE STRUCTURE

- Root directory: only `app.py`, `config.py`, `extensions.py`, `cli_commands.py`, `README.md`, `GRIMOIRE.md`, standard config files (`.env`, `.flake8`, `pytest.ini`, etc.).
- No dead monolithic files in `routes/` — split into subpackages (`routes/owner/`, `routes/ai_routes/`).
- `services/` can have subdirectories for large domains (e.g., `services/gl/`, `services/store/`).

---
*Last updated: 2026-07-09. These rules are non-negotiable. Violations must be fixed immediately.*
